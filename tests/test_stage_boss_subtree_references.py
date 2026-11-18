"""Offline positive/negative controls for exact reference collection and closure."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import boss_metadata_jobs as metadata
import prepare_boss_subtree_references as references
import stage_boss_subtree_references as collector
from tests import test_boss_subtree_references as fixtures


class ReferenceCollectorTests(unittest.TestCase):
    def setUp(self):
        characters, audit, _ = fixtures.SubtreeReferenceTests().fixture()
        jobs, _, _ = references.plan(characters, [audit])
        self.manifest = dict(fingerprint='e' * 20, jobs=jobs, batches=[
            dict(fingerprint=letter * 20, jobs=[job['key']]) for letter, job in zip(('a', 'b'), jobs)])

    def events(self):
        lines = ['PBZ_FULL_CATALOG:START=' + self.manifest['fingerprint']]
        for child, job in zip(self.manifest['batches'], self.manifest['jobs']):
            lines += ['PBZ_ADAPTER_META:START=' + child['fingerprint'],
                f"PBZ_ADAPTER_META:OUTCOME={job['key']}|ability|{job['lookup_path']}|leaf",
                'PBZ_ADAPTER_META:END=' + child['fingerprint']]
        return lines + ['PBZ_FULL_CATALOG:END=' + self.manifest['fingerprint']]

    def test_complete_serial_metadata_has_no_grant_or_playability(self):
        result = collector.analyze(self.events(), self.manifest)
        self.assertEqual(len(result), 2)
        for row in result:
            self.assertTrue(row['metadata_verified'])
            for flag in ('live_grant_verified', 'activation_verified', 'playable'):
                self.assertFalse(row[flag])

    def test_rejection_closes_a_query_without_inventing_type(self):
        lines = self.events(); lines[2] = 'PBZ_ADAPTER_META:REJECTED=' + self.manifest['jobs'][0]['key'] + '|unavailable'
        result = collector.analyze(lines, self.manifest)
        self.assertFalse(result[0]['metadata_verified']); self.assertNotIn('ability_kind', result[0])
        self.assertTrue(result[1]['metadata_verified'])

    def test_orphan_duplicate_foreign_stopped_partial_and_reordered_events_rejected(self):
        original = self.events()
        cases = [[], original[:-1], original[1:], original + [original[2]],
            original[:4] + original[1:4] + original[4:],
            original[:4] + ['PBZ_FULL_CATALOG:STOP=timeout'],
            original[:2] + ['PBZ_ADAPTER_META:STOP=timeout'] + original[2:],
            original[:2] + [original[5]] + original[3:],
            original[:2] + [original[2], original[2]] + original[3:],
            [original[0], *original[4:7], *original[1:4], original[-1]],
            original[:3] + ['PBZ_ADAPTER_META:END=' + 'd' * 20] + original[4:],
            [original[0], original[0], *original[1:]],
            [original[0], 'PBZ_FULL_CATALOG:END=' + self.manifest['fingerprint']],
            original[:2] + [original[2].replace('|leaf', '|unknown')] + original[3:],
            original[:2] + [original[2].replace('.GA_Move_2_C', '.Wrong_C')] + original[3:]]
        for lines in cases:
            with self.subTest(lines=lines), self.assertRaises(AssertionError):
                collector.analyze(lines, self.manifest)

    def test_results_within_one_child_must_preserve_query_order(self):
        report = copy.deepcopy(self.manifest)
        report['batches'] = [dict(fingerprint='a' * 20, jobs=[j['key'] for j in report['jobs']])]
        lines = self.events()
        combined = [lines[0], lines[1], lines[2], lines[5], lines[3], lines[-1]]
        self.assertEqual(len(collector.analyze(combined, report)), 2)
        combined[2], combined[3] = combined[3], combined[2]
        with self.assertRaisesRegex(AssertionError, 'ordered'):
            collector.analyze(combined, report)

    def test_controller_restores_shared_module_after_failure(self):
        before = collector.core.verify, collector.core.QUERY_LABEL, collector.core.current
        with self.assertRaisesRegex(RuntimeError, 'fixture'):
            with collector.controller():
                self.assertIs(collector.core.verify, collector.verify)
                self.assertEqual(collector.core.QUERY_LABEL, collector.LABEL)
                raise RuntimeError('fixture')
        self.assertEqual(before, (collector.core.verify, collector.core.QUERY_LABEL, collector.core.current))

    def test_empty_query_and_insufficient_budget_never_stage(self):
        with patch.object(collector, 'verify', return_value=(dict(jobs=[], batches=[]), b'')), \
             patch.object(collector.core, 'current') as current, patch.object(collector.core, 'stage') as stage:
            with self.assertRaisesRegex(AssertionError, 'empty'):
                collector.stage(Path('empty'))
            current.assert_not_called(); stage.assert_not_called()
        with patch.object(collector.time, 'time', return_value=100):
            for deadline in (699, 700):
                with self.subTest(deadline=deadline), self.assertRaisesRegex(AssertionError, 'budget'):
                    collector.reserve(dict(budget_seconds=480, cleanup_seconds=120), dict(deadline_unix=deadline))

    def test_budget_rechecked_after_foreground_inspection_without_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            manifest = dict(self.manifest, budget_seconds=480, cleanup_seconds=120)
            state = dict(deadline_unix=1000, state_file='fixture')
            staged = dict(research_pid=123)
            with patch.object(collector, 'snapshot', return_value=(manifest, None, state, work, staged, '')), \
                 patch.object(collector.core, 'foreground_window', return_value=12) as foreground, \
                 patch.object(collector.time, 'time', side_effect=[100, 401]):
                with self.assertRaisesRegex(AssertionError, 'budget'):
                    collector.reload_gate(work)
                foreground.assert_called_once(); self.assertFalse(list(work.iterdir()))

    def test_no_reload_gate_after_any_collector_event(self):
        for event in ('PBZ_FULL_CATALOG:START=other', 'PBZ_ADAPTER_META:OUTCOME=orphan'):
            with self.subTest(event=event), patch.object(collector, 'snapshot', return_value=(
                self.manifest, None, {}, None, {}, event)), patch.object(collector.core, 'foreground_window') as foreground:
                with self.assertRaisesRegex(AssertionError, 'already has events'):
                    collector.reload_gate(Path('fixture'))
                foreground.assert_not_called()

    def make_frozen(self, root):
        for name in set(references.SOURCES):
            target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((references.ROOT / name).read_bytes())
        characters, audit, _ = fixtures.SubtreeReferenceTests().fixture()
        with patch.object(references, 'history', return_value=[audit]), \
             patch.object(references, 'inputs', return_value=(dict(characters=characters),)):
            return references.build(root)

    def closed_fixture(self, root):
        directory, manifest = self.make_frozen(root)
        session = '20261119-030000'
        state = root / ('runtime/official-validation-' + session) / 'state.json'
        work = root / 'evidence/official-validation' / session
        collector.write_json(state, dict(restored=True, work=str(work)))
        collector.write_json(work / 'postcheck.json', dict(validation_state=str(state), validation_restored=True,
            research_box_empty=True, research_loader_removed=True, host_registry_unchanged=True,
            formal_files_changed=[], host_config_files_changed=[]))
        collector.archive_sources(manifest, work, create=True, root=root)
        file = lambda suffix: collector.location(work, manifest, suffix)
        script = (directory / 'metadata-collector.lua').read_bytes()
        prefix = b'original log prefix\n'
        staged = dict(state_file=str(state), research_pid=123, batch=manifest['fingerprint'],
            script_sha256=manifest['script_sha256'], manifest_sha256=collector.sha(directory / 'manifest.json'),
            metadata_only=True, input_sent=False, log_byte_offset=len(prefix),
            log_prefix_sha256=hashlib.sha256(prefix).hexdigest())
        collector.write_json(file('staged.json'), staged); collector.write_json(file('intent.json'), staged)
        collector.write_json(file('manifest.json'), manifest); file('metadata.lua').write_bytes(script)
        jobs = {job['key']: job for job in manifest['jobs']}
        lines = ['PBZ_FULL_CATALOG:START=' + manifest['fingerprint']]
        for child in manifest['batches']:
            lines.append('PBZ_ADAPTER_META:START=' + child['fingerprint'])
            for key in child['jobs']:
                lines.append(f"PBZ_ADAPTER_META:OUTCOME={key}|ability|{jobs[key]['lookup_path']}|leaf")
            lines.append('PBZ_ADAPTER_META:END=' + child['fingerprint'])
        lines.append('PBZ_FULL_CATALOG:END=' + manifest['fingerprint'])
        (work / 'UE4SS.log').write_bytes(prefix + ('\n'.join(lines) + '\nshutdown log\n').encode())
        collector.write_json(file('results.json'), collector.capture_value(manifest, state, staged, lines))
        return directory, session, work, state, manifest, file

    def test_closed_receipt_replays_without_current_inputs_or_plan(self):
        with tempfile.TemporaryDirectory(dir=references.ROOT / 'runtime') as temporary:
            root = Path(temporary).resolve()
            directory, session, work, state, manifest, file = self.closed_fixture(root)
            with patch.object(references, 'inputs', side_effect=AssertionError('recursive inventory')), \
                 patch.object(references, 'expected', side_effect=AssertionError('replaced query')):
                result = collector.collect(directory, session, root)
                self.assertEqual(result['queries'], 2); self.assertEqual(result['verified'], 2)
                receipt = collector.verify_receipt(Path(result['receipt']), root)
                self.assertTrue(receipt['reference_only']); self.assertFalse(receipt['native_grant_verified'])
                self.assertEqual(collector.collect(directory, session, root), result)
                # Current developer sources may evolve; replay binds the exact original snapshot.
                (root / 'tools/prepare_boss_subtree_references.py').write_bytes(b'future version')
                self.assertEqual(collector.verify_receipt(Path(result['receipt']), root), receipt)

    def test_inventory_imports_only_verified_closed_type_without_grant(self):
        import boss_offline_inventory as inventory
        with tempfile.TemporaryDirectory(dir=references.ROOT / 'runtime') as temporary:
            root = Path(temporary).resolve()
            directory, session, work, state, manifest, file = self.closed_fixture(root)
            collector.collect(directory, session, root)
            with patch.object(references, 'inputs', side_effect=AssertionError('recursive inventory')):
                sources = {}; indexed = inventory.observations(root, sources)
            self.assertEqual(len(indexed), 2); self.assertEqual(len(sources), 1)
            for rows in indexed.values():
                self.assertEqual(inventory.observation_state(rows, ('ability_kind',)),
                                 ('verified', dict(ability_kind='leaf')))
                self.assertFalse(rows[0]['live_grant_verified']); self.assertFalse(rows[0]['playable'])
            # This import supplies a type fact, not a compatible Actor grant.
            characters, audit, _ = fixtures.SubtreeReferenceTests().fixture()
            path = manifest['jobs'][0]['lookup_path']
            catalog = dict(candidates=[dict(id='fixture', resource_folder='Fixture', reference_only=False,
                assets=[dict(package=path.split('.', 1)[0], role='ability_clue')])])
            rows, _ = inventory.plan(catalog, indexed, [], {})
            ability = next(a for a in rows[0]['abilities'] if a['path'] == path)
            self.assertEqual(ability['route'], 'needs_variant_grant'); self.assertEqual(ability['grants'], [])

    def test_closed_replay_rejects_tampered_sources_scripts_logs_capture_and_cleanup(self):
        with tempfile.TemporaryDirectory(dir=references.ROOT / 'runtime') as temporary:
            root = Path(temporary).resolve()
            directory, session, work, state, manifest, file = self.closed_fixture(root)
            cases = [(work / 'postcheck.json', lambda raw: raw.replace(b'"research_box_empty": true', b'"research_box_empty": false')),
                (work / 'UE4SS.log', lambda raw: b'changed prefix' + raw),
                (work / 'UE4SS.log', lambda raw: raw + b'PBZ_ADAPTER_META:OUTCOME=orphan\n'),
                (file('results.json'), lambda raw: raw.replace(b'"playable": false', b'"playable": true')),
                (file('metadata.lua'), lambda raw: raw + b'changed'),
                (file('intent.json'), lambda raw: raw.replace(b'"research_pid": 123', b'"research_pid": 456')),
                (directory / manifest['batches'][0]['script'], lambda raw: raw + b'changed'),
                (work / collector.SNAPSHOT / 'tools/boss_metadata_jobs.py', lambda raw: raw + b'changed')]
            for path, mutate in cases:
                original = path.read_bytes(); path.write_bytes(mutate(original))
                try:
                    with self.subTest(path=path), self.assertRaises(AssertionError):
                        collector.replay(directory, session, root)
                finally:
                    path.write_bytes(original)

    def test_generated_collector_runs_all_real_child_scripts_offline(self):
        with tempfile.TemporaryDirectory(dir=references.ROOT / 'runtime') as temporary:
            root = Path(temporary).resolve()
            # 70 exact references exercise both the 64-request split and serial continuation.
            for name in set(references.SOURCES):
                target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((references.ROOT / name).read_bytes())
            characters, audit, _ = fixtures.SubtreeReferenceTests().fixture()
            audit['outcomes'][0]['referenced_ability_classes'] = [
                f'/PBZCombatAsset/ActorData/Mobs/Fixture/Ability/GA_Test_{i}.GA_Test_{i}_C' for i in range(70)]
            with patch.object(references, 'history', return_value=[audit]), \
                 patch.object(references, 'inputs', return_value=(dict(characters=characters),)):
                directory, manifest = references.build(root)
            self.assertEqual(len(manifest['batches']), 2)
            from build_boss_profile_candidate import lua
            data = root / 'jobs.lua'; data.write_text('return ' + lua(manifest['jobs']), encoding='utf-8')
            for mode in ('ok', 'subtree', 'unavailable', 'wrong_identity', 'expired', 'frozen_clock'):
                result = subprocess.run([str(references.ROOT.parent / 'build/lua-harness/Release/lua-lab.exe'),
                    'tests/test_boss_subtree_reference_collector.lua', str(directory / 'metadata-collector.lua'),
                    str(data), mode], cwd=references.ROOT, capture_output=True, encoding='utf-8', timeout=15)
                with self.subTest(mode=mode):
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    if mode in ('expired', 'frozen_clock'):
                        with self.assertRaises(AssertionError):
                            collector.analyze(collector.lines_for(result.stdout), manifest)
                    else:
                        outcomes = collector.analyze(collector.lines_for(result.stdout), manifest)
                        self.assertEqual(len(outcomes), 70)
                        self.assertEqual(sum(r['metadata_verified'] for r in outcomes),
                                         0 if mode in ('wrong_identity', 'unavailable') else 70)


if __name__ == '__main__':
    unittest.main()
