import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from tests import test_boss_subtree_inventory as fixtures
import boss_subtree_inventory as subtree
import collect_boss_subtree_progress as collector
from boss_metadata_jobs import canonical
from stage_boss_subtrees import location
import stage_boss_subtrees as stage


class SubtreeProgressTests(unittest.TestCase):
    def test_interruption_retains_only_closed_jobs_and_never_invents_end_events(self):
        _, manifest, lines = fixtures.SubtreeTests().fixture()
        original = copy.deepcopy(manifest['jobs'][0])
        second = dict(original, key='c' * 20, path=original['path'].replace('GA_Fixture', 'GA_Second'))
        manifest['jobs'].append(second)
        manifest['jobs'].append(dict(original, key='d' * 20))
        segment = lines[:-1] + [subtree.PREFIX + 'JOB_BEGIN=' + second['key'] + '|fixture|' + second['path'],
                               subtree.PREFIX + 'TREE=' + second['key'] + '|1|/Game/Tree.Tree|1']
        saved = list(segment)
        with self.assertRaises(AssertionError): subtree.analyze(segment, manifest)
        result = subtree.analyze(segment, manifest, allow_incomplete=True)
        self.assertFalse(result['batch_complete']); self.assertEqual(len(result['outcomes']), 1)
        self.assertEqual(result['interrupted_job'], second['key'])
        self.assertEqual(result['discarded_open_tree_count'], 1)
        self.assertEqual(result['unstarted_job_keys'], ['d' * 20])
        self.assertEqual(segment, saved)

    def test_partial_mode_still_rejects_foreign_duplicate_out_of_order_and_stopped_events(self):
        _, manifest, lines = fixtures.SubtreeTests().fixture()
        for events in (lines[1:-1], lines[:2] + [lines[1]], lines[:6] + [lines[5]],
                       lines + [lines[-1]], lines[:4] + [subtree.PREFIX + 'STOP=deadline'],
                       lines[:1] + [lines[-1]],
                       [line.replace('|fixture|', '|other|') for line in lines[:-1]]):
            with self.subTest(events=events), self.assertRaises(AssertionError):
                subtree.analyze(events, manifest, allow_incomplete=True)
        complete = subtree.analyze(lines, manifest, allow_incomplete=True)
        self.assertTrue(complete['batch_complete']); self.assertEqual(len(complete['outcomes']), 1)
        self.assertEqual(complete['unstarted_job_keys'], [])

    def test_interrupted_job_discards_even_its_closed_trees(self):
        _, manifest, lines = fixtures.SubtreeTests().fixture()
        result = subtree.analyze(lines[:-2], manifest, allow_incomplete=True)
        self.assertEqual(result['outcomes'], [])
        self.assertEqual(result['discarded_open_tree_count'], 1)
        self.assertEqual(result['interrupted_job'], manifest['jobs'][0]['key'])

    def test_native_generated_class_subtypes_are_preserved_as_unactivated_references(self):
        _, manifest, lines = fixtures.SubtreeTests().fixture()
        lines = [line.replace('BlueprintGeneratedClass ', 'LegoAbilityBlueprintGeneratedClass ') for line in lines]
        row, = subtree.analyze(lines, manifest)
        self.assertTrue(row['mapping_observed']); self.assertFalse(row['activation_verified'])

    def test_continuation_skips_complete_rejected_and_interrupted_history_without_reordering(self):
        progress = dict(unstarted_job_keys=list('abcdef'))
        prior = [dict(outcomes=[dict(key='b', mapping_observed=True), dict(key='d', mapping_observed=False)],
                      interrupted_job='e')]
        self.assertEqual(collector.unstarted_keys(progress, prior), list('acf'))
        self.assertEqual(progress['unstarted_job_keys'], list('abcdef'))

    def test_pending_selection_skips_exact_attempted_classes_after_receipt_key_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            key = 'e' * 20
            original = [dict(key=str(i) * 20, id='fixture', path=f'/Game/GA_{i}.GA_{i}_C') for i in range(4)]
            manifest = root / subtree.OUTPUT / key / 'manifest.json'
            collector.write_json(manifest, dict(jobs=original))
            audit = dict(metadata_only=True, playable=False, batch=key,
                outcomes=[dict(key=j['key'], id=j['id'], parent_class=j['path'], mapping_observed=i == 0)
                          for i, j in enumerate(original[:2])], interrupted_job=original[2]['key'],
                sources={manifest.relative_to(root).as_posix(): collector.sha(manifest)})
            current = [dict(job, key='new-' + job['key']) for job in original]
            self.assertEqual(collector.unattempted_jobs(current, [audit], root), current[3:])
            manifest.write_bytes(manifest.read_bytes() + b' ')
            with self.assertRaisesRegex(AssertionError, 'identities changed'):
                collector.unattempted_jobs(current, [audit], root)

    def closed_fixture(self, root, *, complete=False):
        _, manifest, lines = fixtures.SubtreeTests().fixture()
        second = dict(manifest['jobs'][0], key='c' * 20)
        manifest['jobs'].append(second)
        source_map = {name: hashlib.sha256(('fixture ' + name).encode()).hexdigest() for name in subtree.SOURCES}
        identity = dict(schema=1, kind='boss_subtree_inventory', build=collector.BUILD,
                        jobs=manifest['jobs'], inventory_sha256='d' * 64, source_sha256=source_map)
        key = hashlib.sha256(canonical(identity)).hexdigest()[:20]
        manifest.update(identity, fingerprint=key, script_sha256=hashlib.sha256(b'-- frozen fixture').hexdigest(),
                        game_started=False, ui_input_sent=False, deployed=False, playable=False,
                        activation_allowed=False, execution_order_proven=False)
        lines = [line.replace('b' * 20, key) for line in lines]
        segment = lines[:-1] + [subtree.PREFIX + 'JOB_BEGIN=' + second['key'] + '|fixture|' + second['path']]
        if complete:
            first_key = manifest['jobs'][0]['key']
            segment = lines[:-1] + [line.replace(first_key, second['key']) for line in lines[1:-1]] + [lines[-1]]
        work = root / 'evidence/official-validation/20261119-000000'; work.mkdir(parents=True)
        state = root / 'runtime/official-validation-20261119-000000/state.json'; state.parent.mkdir(parents=True)
        state.write_text(json.dumps(dict(restored=True, work=str(work))), encoding='utf-8')
        (work / 'postcheck.json').write_text(json.dumps(dict(validation_state=str(state), validation_restored=True,
            research_box_empty=True, research_loader_removed=True, host_registry_unchanged=True,
            formal_files_changed=[], host_config_files_changed=[])), encoding='utf-8')
        batch = root / subtree.OUTPUT / key; batch.mkdir(parents=True)
        (batch / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        (batch / 'subtree-probe.lua').write_bytes(b'-- frozen fixture')
        location(work, manifest, 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        location(work, manifest, 'probe.lua').write_bytes(b'-- frozen fixture')
        prefix = b'prefix\n'
        staged = dict(state_file=str(state), batch=key, research_pid=77, metadata_only=True, ui_input_sent=False,
            manifest_sha256=collector.sha(batch / 'manifest.json'), script_sha256=manifest['script_sha256'],
            log_byte_offset=len(prefix), log_prefix_sha256=hashlib.sha256(prefix).hexdigest())
        for suffix in ('intent.json', 'staged.json'):
            location(work, manifest, suffix).write_text(json.dumps(staged), encoding='utf-8')
        (work / 'UE4SS.log').write_bytes(prefix + ('\n'.join(segment) + '\n').encode())
        if complete:
            captured = dict(state_file=str(state), research_pid=77, batch=key,
                script_sha256=manifest['script_sha256'], metadata_only=True, playable=False,
                execution_order_proven=False, lines=segment, outcomes=subtree.analyze(segment, manifest))
            location(work, manifest, 'capture.json').write_text(json.dumps(captured), encoding='utf-8')
        for name in source_map:
            path = work / 'subtree-source-snapshot' / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('fixture ' + name).encode())
        for name in ('tools/collect_boss_subtree_progress.py', 'tools/boss_subtree_inventory.py',
                     'tools/stage_boss_subtrees.py', 'tests/test_boss_subtree_progress.py'):
            path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'current audit fixture')
        return work, batch

    def test_complete_history_requires_exact_capture_without_creating_partial_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); work, batch = self.closed_fixture(root, complete=True)
            with self.assertRaises(AssertionError): collector.replay('20261119-000000', batch, root)
            report = collector.replay('20261119-000000', batch, root, allow_complete=True)
            self.assertTrue(report['batch_complete']); self.assertEqual(len(report['outcomes']), 2)
            self.assertEqual(collector.history(root), [report])
            self.assertFalse((work / 'subtree-interrupted-progress.json').exists())
            manifest = json.loads((batch / 'manifest.json').read_bytes())
            path = location(work, manifest, 'capture.json'); value = json.loads(path.read_bytes())
            value['playable'] = True; path.write_text(json.dumps(value), encoding='utf-8')
            with self.assertRaises(AssertionError): collector.history(root)

    def test_complete_collection_replays_original_query_after_current_inventory_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); work, batch = self.closed_fixture(root, complete=True)
            # Current inventory may include grants observed after this query.
            # Historical collection must not rebuild it or validate old files
            # against current generator bytes.
            with patch.object(subtree, 'verify', side_effect=AssertionError('current inventory changed')):
                result = stage.collect(batch, '20261119-000000', root)
                self.assertEqual(result['queries'], 2)
                self.assertEqual(result['mappings'], 2)
                self.assertFalse(result['playable'])
                self.assertEqual(stage.collect(batch, '20261119-000000', root), result)
            path = Path(result['receipt']); original = path.read_bytes()
            path.write_bytes(original + b' ')
            # JSON whitespace does not change the receipt; captured outcomes do.
            manifest = json.loads((batch / 'manifest.json').read_bytes())
            capture = location(work, manifest, 'capture.json')
            changed = json.loads(capture.read_bytes()); changed['outcomes'][0]['playable'] = True
            capture.write_text(json.dumps(changed), encoding='utf-8')
            with self.assertRaises(AssertionError): stage.collect(batch, '20261119-000000', root)
            self.assertEqual(path.read_bytes(), original + b' ')

    def test_complete_collection_rejects_incomplete_or_changed_closed_evidence(self):
        for mutation in ('incomplete', 'source', 'script', 'prefix', 'postcheck', 'extra_file'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                work, batch = self.closed_fixture(root, complete=mutation != 'incomplete')
                if mutation == 'source':
                    (work / 'subtree-source-snapshot/tools/boss_subtree_probe.lua').write_bytes(b'changed')
                elif mutation == 'script': (batch / 'subtree-probe.lua').write_bytes(b'changed')
                elif mutation == 'prefix':
                    log = work / 'UE4SS.log'; log.write_bytes(b'changed' + log.read_bytes())
                elif mutation == 'postcheck':
                    post = work / 'postcheck.json'; value = json.loads(post.read_bytes())
                    value['research_box_empty'] = False; post.write_text(json.dumps(value), encoding='utf-8')
                elif mutation == 'extra_file': (batch / 'unreviewed.lua').write_bytes(b'changed')
                with self.assertRaises(AssertionError): stage.collect(batch, '20261119-000000', root)
                self.assertFalse((root / 'research/boss-adaptation/subtree-receipts').exists())

    def test_closed_replay_requires_original_sources_prefix_script_and_postcheck(self):
        for mutation in ('none', 'source', 'prefix', 'script', 'postcheck'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve(); work, batch = self.closed_fixture(root)
                if mutation == 'source': (work / 'subtree-source-snapshot/tools/boss_subtree_probe.lua').write_bytes(b'changed')
                elif mutation == 'prefix':
                    log = work / 'UE4SS.log'; log.write_bytes(b'changed' + log.read_bytes())
                elif mutation == 'script': (batch / 'subtree-probe.lua').write_bytes(b'changed')
                elif mutation == 'postcheck':
                    post = work / 'postcheck.json'; value = json.loads(post.read_bytes())
                    value['formal_files_changed'] = ['changed']; post.write_text(json.dumps(value), encoding='utf-8')
                if mutation == 'none':
                    _, report = collector.collect('20261119-000000', batch, root)
                    self.assertEqual(collector.replay('20261119-000000', batch, root), report)
                    self.assertFalse(report['playable']); self.assertFalse(report['batch_complete'])
                    self.assertEqual(len(report['outcomes']), 1)
                else:
                    with self.assertRaises(AssertionError): collector.collect('20261119-000000', batch, root)


if __name__ == '__main__':
    unittest.main()
