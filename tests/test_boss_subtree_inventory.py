import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import boss_subtree_inventory as subtree
import stage_boss_subtrees as stage


class SubtreeTests(unittest.TestCase):
    def fixture(self):
        path = '/PBZCombatAsset/ActorData/Mobs/Fixture/Ability/GA_Fixture.GA_Fixture_C'
        characters = [dict(id='fixture', folder='Fixture', abilities=[dict(path=path,
            metadata='verified', kind='subtree', receipts=['metadata.json'])])]
        jobs = subtree.jobs_for(characters, {'metadata.json': 'a' * 64})
        manifest = dict(fingerprint='b' * 20, jobs=jobs, max_seconds=480)
        key = jobs[0]['key']
        tree = '/PBZCombatAsset/ActorData/Mobs/Fixture/BT_Fixture.BT_Fixture'
        root, leaf = 'BTComposite_Sequence ' + tree + ':Root', 'BTTask_Ability ' + tree + ':Leaf'
        reference = 'BlueprintGeneratedClass ' + path.replace('GA_Fixture', 'GA_Fixture_Leaf')
        events = [('START', manifest['fingerprint']), ('JOB_BEGIN', key + '|fixture|' + path),
            ('TREE', key + '|1|' + tree + '|1'), ('NODE', key + '|1|' + root),
            ('EDGE', key + '|1|' + root + '|' + leaf + '|ChildTask|1'), ('NODE', key + '|1|' + leaf),
            ('REF', key + '|1|' + leaf + '|AbilityToActivate|' + reference),
            ('TREE_END', key + '|1|2|1|1'), ('JOB_END', key + '|1'), ('END', manifest['fingerprint'])]
        return characters, manifest, [subtree.PREFIX + k + '=' + v for k, v in events]

    def test_only_exact_receipted_subtrees_become_jobs(self):
        characters, manifest, _ = self.fixture()
        self.assertEqual(len(manifest['jobs']), 1)
        for change in (dict(kind='leaf'), dict(metadata='conflict'), dict(metadata='rejected')):
            c = copy.deepcopy(characters); c[0]['abilities'][0].update(change)
            self.assertFalse(subtree.jobs_for(c, {}))
        for change in (dict(path='/Other.GA_Other_C'), dict(receipts=[]), dict(receipts=['missing'])):
            c = copy.deepcopy(characters); c[0]['abilities'][0].update(change)
            with self.assertRaises(AssertionError): subtree.jobs_for(c, {'metadata.json': 'a' * 64})
        with self.assertRaises(AssertionError): subtree.jobs_for(characters * 2, {'metadata.json': 'a' * 64})

    def test_graph_preserves_edges_without_promoting_execution_or_grants(self):
        _, manifest, lines = self.fixture()
        row, = subtree.analyze(lines, manifest)
        self.assertTrue(row['mapping_observed'])
        self.assertEqual(len(row['trees'][0]['edges']), 1)
        self.assertEqual(len(row['referenced_ability_classes']), 1)
        for flag in ('playable', 'execution_order_proven', 'activation_verified', 'native_grant_verified'):
            self.assertFalse(row[flag])

    def test_partial_rejection_never_exports_completed_or_partial_trees(self):
        _, manifest, lines = self.fixture(); key = manifest['jobs'][0]['key']
        for offset in (2, 4, 8):
            events = lines[:offset] + [subtree.PREFIX + 'REJECTED=' + key + '|inspection refused', lines[-1]]
            row, = subtree.analyze(events, manifest)
            self.assertFalse(row['mapping_observed']); self.assertEqual(row['trees'], [])
            self.assertNotIn('referenced_ability_classes', row)

    def test_missing_duplicate_foreign_or_trailing_events_are_rejected(self):
        _, manifest, lines = self.fixture()
        variants = [lines[:-1], lines[1:], lines + [lines[-1]], lines[:2] + [lines[1]] + lines[2:],
                    lines[:6] + [lines[5]] + lines[6:], lines[:7] + [lines[6]] + lines[7:],
                    [line.replace('|fixture|', '|other|') for line in lines],
                    [line.replace(':Leaf', ':Foreign') if ':Leaf' in line and ':Root' not in line else line for line in lines],
                    [line.replace('TREE_END=', 'UNKNOWN=') for line in lines],
                    [line.replace('|1|2|1|1', '|1|2|0|1') for line in lines],
                    [line.rsplit('|', 1)[0] + '|nan' if 'TREE=' in line else line for line in lines]]
        for index, events in enumerate(variants):
            with self.subTest(index=index), self.assertRaises((AssertionError, ValueError)):
                subtree.analyze(events, manifest)

    def test_foreign_node_and_disconnected_declarations_are_rejected(self):
        _, manifest, lines = self.fixture()
        for events in (
            [line.replace('BT_Fixture.BT_Fixture:Root', 'BT_Other.BT_Other:Root') for line in lines],
            [line for line in lines if 'EDGE=' not in line],
            [line.replace('|ChildTask|1', '|Unknown|1') for line in lines],
            [line.replace('|ChildTask|1', '|ChildTask|129') for line in lines],
        ):
            with self.assertRaises(AssertionError): subtree.analyze(events, manifest)

    def test_immutable_build_reconstructs_source_and_inventory(self):
        characters, _, _ = self.fixture()
        snapshot = dict(characters=characters, sources={'metadata.json': 'a' * 64})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for name in subtree.SOURCES:
                target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((subtree.ROOT / name).read_bytes())
            with patch.object(subtree, 'inputs', return_value=(snapshot,)):
                batch, manifest = subtree.build(root)
                self.assertFalse(manifest['activation_allowed'])
                raw = (batch / 'subtree-probe.lua').read_bytes()
                (batch / 'subtree-probe.lua').write_bytes(raw + b'--changed')
                with self.assertRaises(AssertionError): subtree.verify(batch, root)
                self.assertEqual((batch / 'subtree-probe.lua').read_bytes(), raw + b'--changed')

    def test_selected_queue_reconstructs_only_observed_jobs_in_original_order(self):
        characters, _, _ = self.fixture()
        extra = copy.deepcopy(characters[0]['abilities'][0])
        extra['path'] = extra['path'].replace('GA_Fixture', 'GA_Second')
        characters[0]['abilities'].append(extra)
        snapshot = dict(characters=characters, sources={'metadata.json': 'a' * 64})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for name in subtree.SOURCES:
                target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((subtree.ROOT / name).read_bytes())
            with patch.object(subtree, 'inputs', return_value=(snapshot,)):
                jobs = subtree.jobs_for(characters, snapshot['sources'])
                batch, manifest = subtree.build(root, job_keys=[jobs[1]['key']])
                self.assertEqual(manifest['jobs'], jobs[1:])
                self.assertEqual(subtree.verify(batch, root)[0], manifest)
                for keys in ([], ['f' * 20], [jobs[0]['key']] * 2):
                    with self.assertRaises(AssertionError): subtree.build(root, job_keys=keys)
                full, _ = subtree.build(root, job_keys=[j['key'] for j in reversed(jobs)])
                self.assertEqual(subtree.verify(full, root)[0]['jobs'], jobs)
                saved = json.loads((full / 'manifest.json').read_bytes()); saved['jobs'].reverse()
                (full / 'manifest.json').write_text(json.dumps(saved), encoding='utf-8')
                with self.assertRaises(AssertionError): subtree.verify(full, root)

    def test_actual_lua_probe_roundtrip_and_serial_timeout_boundaries(self):
        _, manifest, _ = self.fixture()
        with tempfile.TemporaryDirectory(dir=subtree.ROOT / 'runtime') as directory:
            script = Path(directory) / 'subtree.lua'
            script.write_bytes(subtree.payload(manifest['jobs'], manifest['fingerprint']))
            for mode in ('ok', 'empty', 'wrong_identity', 'wrong_cdo', 'foreign_node',
                         'node_bound', 'nonfinite_weight', 'property_timeout', 'busy_timeout', 'poll_budget',
                         'lego_class', 'nonclass_reference', 'map_unavailable'):
                result = subprocess.run([str(subtree.ROOT.parent / 'build/lua-harness/Release/lua-lab.exe'),
                    'tests/test_boss_subtree_probe.lua', script.relative_to(subtree.ROOT).as_posix(), mode, 'emit'],
                    cwd=subtree.ROOT, capture_output=True, encoding='utf-8', timeout=10)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                lines = result.stdout.splitlines()
                if mode in ('busy_timeout', 'poll_budget'):
                    with self.assertRaises(AssertionError): subtree.analyze(lines, manifest)
                else:
                    row, = subtree.analyze(lines, manifest)
                    self.assertEqual(row['mapping_observed'], mode in ('ok', 'empty', 'lego_class'))
                    if mode == 'empty': self.assertEqual(row['trees'], [])

    def fake_stage(self, root):
        _, manifest, lines = self.fixture()
        script = b'-- fake frozen read-only query\n'
        manifest['script_sha256'] = hashlib.sha256(script).hexdigest()
        manifest['source_sha256'] = {}
        for name in subtree.SOURCES:
            source = root / name; source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes((subtree.ROOT / name).read_bytes())
            manifest['source_sha256'][name] = subtree.sha(source)
        batch = root / 'batch'; batch.mkdir()
        (batch / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        work = root / 'evidence/official-validation/20261119-000000'; work.mkdir(parents=True)
        state_path = root / 'runtime/official-validation-20261119-000000/state.json'
        state_path.parent.mkdir(parents=True)
        carrier = root / 'runtime/carrier.lua'; carrier.write_bytes(b'-- original')
        log = work / 'UE4SS.log'; log.write_bytes(b'original prefix\n')
        state = dict(state_file=str(state_path), work=str(work), deadline_unix=10**12,
                     ue4ss_loader_manifest=[dict(physical_path=str(carrier))])
        state_path.write_text(json.dumps(state), encoding='utf-8')
        practice = SimpleNamespace(log_path=lambda _: log)
        validation = SimpleNamespace(save=Mock(), state_path=lambda: state_path, verify_build=Mock())
        return manifest, script, batch, work, state_path, carrier, log, state, practice, validation, lines

    def test_stage_gate_capture_and_closed_replay_are_input_free(self):
        with tempfile.TemporaryDirectory(dir=subtree.ROOT / 'runtime') as directory:
            root = Path(directory).resolve()
            m, raw, batch, work, state_path, carrier, log, state, practice, validation, lines = self.fake_stage(root)
            with patch.object(subtree, 'verify', return_value=(m, raw)), \
                 patch.object(stage, 'ROOT', root), \
                 patch.object(stage, 'current', return_value=(practice, validation, state, work, carrier, 77)), \
                 patch.object(stage, 'foreground_window', return_value=123):
                stage.stage(batch)
                self.assertEqual(carrier.read_bytes(), raw)
                stage.archive_sources(m, work)
                gate = stage.reload_gate(batch)
                self.assertEqual(gate['key'], 'Control_L+r'); self.assertFalse(gate['input_sent'])
                with self.assertRaises(AssertionError): stage.stage(batch)
                log.write_bytes(log.read_bytes() + ('\n'.join(lines) + '\n').encode())
                with self.assertRaises(AssertionError): stage.reload_gate(batch)
                self.assertEqual(stage.capture(batch)['mappings'], 1)
                with self.assertRaises(FileExistsError): stage.capture(batch)
                state['restored'] = True; state_path.write_text(json.dumps(state), encoding='utf-8')
                post = dict(validation_state=str(state_path), validation_restored=True, research_box_empty=True,
                    research_loader_removed=True, host_registry_unchanged=True,
                    formal_files_changed=[], host_config_files_changed=[])
                (work / 'postcheck.json').write_text(json.dumps(post), encoding='utf-8')
                result = stage.collect(batch.relative_to(subtree.ROOT), '20261119-000000', root)
                self.assertFalse(result['playable']); self.assertEqual(result['mappings'], 1)
                captured = stage.location(work, m, 'capture.json')
                value = json.loads(captured.read_bytes()); value['outcomes'][0]['playable'] = True
                captured.write_text(json.dumps(value), encoding='utf-8')
                with self.assertRaises(AssertionError): stage.collect(batch, '20261119-000000', root)

    def test_stage_rejects_idle_failure_short_lease_and_changed_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            m, raw, batch, work, _, carrier, log, state, practice, validation, _ = self.fake_stage(root)
            with patch.object(subtree, 'verify', return_value=(m, raw)), \
                 patch.object(stage, 'current', side_effect=AssertionError('not idle')):
                with self.assertRaises(AssertionError): stage.stage(batch)
                self.assertEqual(carrier.read_bytes(), b'-- original')
            with patch.object(subtree, 'verify', return_value=(m, raw)), \
                 patch.object(stage, 'ROOT', root), \
                 patch.object(stage, 'current', return_value=(practice, validation, state, work, carrier, 77)):
                state['deadline_unix'] = 0
                with self.assertRaises(AssertionError): stage.stage(batch)
                self.assertEqual(carrier.read_bytes(), b'-- original')
                state['deadline_unix'] = 10**12; stage.stage(batch)
                log.write_bytes(b'changed original prefix\n')
                with self.assertRaises(AssertionError): stage.snapshot(batch)

    def test_source_snapshot_is_required_and_never_overwrites_a_prior_source(self):
        for mutation in ('before_stage', 'after_stage'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                m, raw, batch, work, _, carrier, _, state, practice, validation, _ = self.fake_stage(root)
                with patch.object(subtree, 'verify', return_value=(m, raw)), \
                     patch.object(stage, 'ROOT', root), \
                     patch.object(stage, 'current', return_value=(practice, validation, state, work, carrier, 77)):
                    name = 'tools/boss_subtree_probe.lua'
                    if mutation == 'before_stage':
                        (root / name).write_bytes(b'changed')
                        with self.assertRaises(AssertionError): stage.stage(batch)
                        self.assertEqual(carrier.read_bytes(), b'-- original')
                    else:
                        stage.stage(batch)
                        original = (work / 'subtree-source-snapshot' / name).read_bytes()
                        with self.assertRaises(FileExistsError): stage.archive_sources(m, work, create=True)
                        self.assertEqual((work / 'subtree-source-snapshot' / name).read_bytes(), original)
                        (work / 'subtree-source-snapshot' / name).write_bytes(b'changed')
                        with self.assertRaises(AssertionError): stage.snapshot(batch)

    def test_oversized_inventory_is_rejected_before_live_carrier_access(self):
        _, manifest, _ = self.fixture()
        self.assertEqual(subtree.MAX_STAGE_JOBS, 96)
        manifest['jobs'] *= subtree.MAX_STAGE_JOBS + 1
        with patch.object(subtree, 'verify', return_value=(manifest, b'fixture')), \
             patch.object(stage, 'current') as current:
            with self.assertRaises(AssertionError): stage.stage(Path('fixture'))
            current.assert_not_called()


if __name__ == '__main__':
    unittest.main()
