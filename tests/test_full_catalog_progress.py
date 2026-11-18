"""A timed-out full catalog must preserve complete batches without promoting partial reads."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import boss_metadata_jobs as metadata
import stage_full_boss_catalog as collector
from tests.test_boss_metadata_jobs import candidate


class CatalogProgressTests(unittest.TestCase):
    def setUp(self):
        jobs = metadata.jobs_for(candidate('fixture', characters=0, abilities=2))
        self.manifests = [dict(batch_fingerprint=letter * 20, jobs=[job])
                          for letter, job in zip(('a', 'b'), jobs)]
        self.report = dict(fingerprint='c' * 20, batches=[dict(directory='first'), dict(directory='second')])
        self.first, self.second = (row['batch_fingerprint'] for row in self.manifests)

    def verify(self, path):
        return self.manifests[0 if Path(path).name == 'first' else 1]

    def outcome(self, index):
        job = self.manifests[index]['jobs'][0]
        return f"PBZ_ADAPTER_META:OUTCOME={job['key']}|ability|{job['lookup_path']}|leaf"

    def text(self, *tail):
        return '\n'.join([
            'PBZ_FULL_CATALOG:START=' + self.report['fingerprint'],
            'PBZ_ADAPTER_META:START=' + self.first, self.outcome(0),
            'PBZ_ADAPTER_META:END=' + self.first, *tail])

    def read_progress(self, raw):
        with patch.object(collector.metadata, 'verify_batch', side_effect=self.verify):
            return collector.progress(raw, self.report)

    def test_timeout_preserves_earlier_batch_only(self):
        raw = self.text('PBZ_ADAPTER_META:START=' + self.second, self.outcome(1),
                        'PBZ_FULL_CATALOG:STOP=outer metadata deadline')
        result = self.read_progress(raw)
        self.assertTrue(result['terminal'])
        self.assertFalse(result['complete'])
        self.assertEqual(result['completed_batch_keys'], [self.first])
        self.assertEqual(result['pending_batch_keys'], [self.second])
        self.assertEqual(len(result['outcomes']), 1)

    def test_timeout_between_batches_leaves_not_started_pending(self):
        result = self.read_progress(self.text('PBZ_FULL_CATALOG:STOP=outer metadata deadline'))
        self.assertEqual(result['started_batch_keys'], [self.first])
        self.assertEqual(result['pending_batch_keys'], [self.second])

    def test_inner_timeout_and_outer_timeout_preserve_same_complete_prefix(self):
        result = self.read_progress(self.text('PBZ_ADAPTER_META:START=' + self.second,
            'PBZ_ADAPTER_META:STOP=deadline or polling budget', 'PBZ_FULL_CATALOG:STOP=inner metadata deadline'))
        self.assertEqual(result['completed_batch_keys'], [self.first])
        self.assertFalse(result['complete'])

    def test_capture_rejects_a_still_running_collector(self):
        raw = self.text('PBZ_ADAPTER_META:START=' + self.second)
        self.assertFalse(self.read_progress(raw)['terminal'])
        with tempfile.TemporaryDirectory() as temp:
            snapshot = (self.report, None, {}, Path(temp), {}, raw)
            with patch.object(collector.core, 'snapshot', return_value=snapshot), \
                 patch.object(collector.metadata, 'verify_batch', side_effect=self.verify):
                with self.assertRaisesRegex(AssertionError, 'still running'):
                    collector.capture(Path(temp))
                self.assertEqual(list(Path(temp).iterdir()), [])

    def test_complete_run_preserves_every_batch(self):
        result = self.read_progress(self.text('PBZ_ADAPTER_META:START=' + self.second, self.outcome(1),
            'PBZ_ADAPTER_META:END=' + self.second, 'PBZ_FULL_CATALOG:END=' + self.report['fingerprint']))
        self.assertTrue(result['complete'])
        self.assertEqual(result['pending_batch_keys'], [])
        self.assertEqual(len(result['outcomes']), 2)

    def test_repeated_foreign_or_post_stop_metadata_is_rejected(self):
        cases = [
            self.text('PBZ_ADAPTER_META:START=' + self.first),
            self.text('PBZ_ADAPTER_META:START=' + 'd' * 20),
            self.text(self.outcome(1)),
            self.text('PBZ_ADAPTER_META:START=' + self.second, 'PBZ_ADAPTER_META:END=' + self.first),
            self.text('PBZ_FULL_CATALOG:STOP=timeout', self.outcome(1)),
            self.text('PBZ_FULL_CATALOG:START=' + self.report['fingerprint']),
            self.text('PBZ_FULL_CATALOG:END=' + self.report['fingerprint']),
        ]
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(AssertionError):
                self.read_progress(raw)

    def test_child_archives_exclude_incomplete_batch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for name, manifest in zip(('first', 'second'), self.manifests):
                batch = root / name
                batch.mkdir()
                (batch / 'metadata-probe.lua').write_bytes(b'-- fixture')
                (batch / 'metadata-probe-manifest.json').write_bytes(b'{}')
                manifest['script_sha256'] = hashlib.sha256(b'-- fixture').hexdigest()
            work = root / 'work'
            work.mkdir()
            raw = self.text('PBZ_ADAPTER_META:START=' + self.second, self.outcome(1),
                            'PBZ_FULL_CATALOG:STOP=outer metadata deadline')
            with patch.object(collector, 'ROOT', root), \
                 patch.object(collector.metadata, 'verify_batch', side_effect=self.verify):
                collector.record_children(self.report, dict(state_file='fixture'), work, raw, [self.first])
            self.assertEqual(len(list(work.iterdir())), 2)
            self.assertTrue(all(file.name.startswith(self.first) for file in work.iterdir()))

    def test_later_independent_query_does_not_invalidate_completed_prefix(self):
        terminal = self.text('PBZ_FULL_CATALOG:STOP=outer metadata deadline')
        other = '\n'.join(('PBZ_ADAPTER_META:START=' + 'd' * 20,
                           'PBZ_ADAPTER_META:OUTCOME=unrelated|ability|/Other.Path|leaf',
                           'PBZ_ADAPTER_META:END=' + 'd' * 20))
        self.assertEqual(self.read_progress(terminal), self.read_progress(terminal + '\n' + other))

    def test_later_query_cannot_hide_late_owned_results_or_duplicate_child(self):
        terminal = self.text('PBZ_FULL_CATALOG:STOP=outer metadata deadline')
        cases = [
            ('PBZ_ADAPTER_META:START=' + 'd' * 20, self.outcome(0)),
            ('PBZ_ADAPTER_META:START=' + 'd' * 20, self.outcome(1)),
            ('PBZ_ADAPTER_META:START=' + self.first,),
            ('PBZ_ADAPTER_META:START=' + self.second,),
            ('PBZ_ADAPTER_META:START=' + 'd' * 20, 'PBZ_ADAPTER_META:END=' + 'e' * 20),
        ]
        for lines in cases:
            with self.subTest(lines=lines), self.assertRaises(AssertionError):
                self.read_progress(terminal + '\n' + '\n'.join(lines))

    def test_no_completed_child_still_requires_successful_shutdown_postcheck(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / 'queue').mkdir()
            session = '20261118-211942'
            work = root / 'evidence/official-validation' / session
            state = root / ('runtime/official-validation-' + session) / 'state.json'
            collector.write_json(state, dict(restored=True, work=str(work)))
            for failure in ('missing', 'research_box_empty', 'research_loader_removed',
                            'host_registry_unchanged', 'formal_files_changed', 'host_config_files_changed'):
                post = dict(validation_state=str(state), research_box_empty=True,
                            research_loader_removed=True, host_registry_unchanged=True,
                            formal_files_changed=[], host_config_files_changed=[])
                if failure != 'missing':
                    post[failure] = ['changed'] if failure.endswith('_changed') else False
                    collector.write_json(work / 'postcheck.json', post)
                with self.subTest(failure=failure), patch.object(collector, 'ROOT', root), \
                     patch.object(collector, 'verify', return_value=({}, b'')), \
                     patch.object(collector, 'collect_batch') as archive:
                    with self.assertRaises((AssertionError, FileNotFoundError)):
                        collector.collect(root / 'queue', session)
                    archive.assert_not_called()

    def test_closed_zero_progress_attempt_retains_all_pending_without_receipts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            directory = root / 'queue'
            directory.mkdir()
            session = '20261118-211942'
            work = root / 'evidence/official-validation' / session
            state = root / ('runtime/official-validation-' + session) / 'state.json'
            collector.write_json(state, dict(restored=True, work=str(work)))
            collector.write_json(work / 'postcheck.json', dict(validation_state=str(state), research_box_empty=True,
                research_loader_removed=True, host_registry_unchanged=True,
                formal_files_changed=[], host_config_files_changed=[]))
            script = b'-- fixture'
            report = dict(self.report, script_sha256=hashlib.sha256(script).hexdigest())
            collector.write_json(directory / 'manifest.json', report)
            def file(suffix):
                return work / f"{collector.LABEL}-{report['fingerprint']}-{suffix}"
            stage = dict(state_file=str(state), research_pid=12, script_sha256=report['script_sha256'],
                         batch=report['fingerprint'], metadata_only=True, input_sent=False,
                         manifest_sha256=collector.sha(directory / 'manifest.json'), log_byte_offset=0,
                         log_prefix_sha256=hashlib.sha256(b'').hexdigest())
            collector.write_json(file('staged.json'), stage)
            collector.write_json(file('intent.json'), stage)
            collector.write_json(file('manifest.json'), report)
            file('metadata.lua').write_bytes(script)
            raw = 'PBZ_FULL_CATALOG:START=' + report['fingerprint'] + '\nPBZ_FULL_CATALOG:STOP=timeout\n'
            (work / 'UE4SS.log').write_bytes(raw.encode())
            observed = self.read_progress(raw)
            collector.write_json(file('results.json'), dict(state_file=str(state), research_pid=12, **observed,
                fingerprint=report['fingerprint'],
                lines=raw.splitlines(), metadata_only=True, playable=False))
            with patch.object(collector, 'ROOT', root), patch.object(collector, 'verify', return_value=(report, script)), \
                 patch.object(collector.metadata, 'verify_batch', side_effect=self.verify), \
                 patch.object(collector.core, 'QUERY_LABEL', collector.LABEL), \
                 patch.object(collector, 'collect_batch') as archive:
                result = collector.collect(directory, session)
                self.assertFalse(result['complete'])
                self.assertEqual(result['pending_batch_keys'], [self.first, self.second])
                self.assertEqual(result['receipts'], [])
                archive.assert_not_called()
                # Shutdown may append an independent query, but a late owned
                # outcome must never be absorbed under that query's fingerprint.
                later = 'PBZ_ADAPTER_META:START=' + 'd' * 20 + '\n'
                (work / 'UE4SS.log').write_bytes((raw + later).encode())
                self.assertEqual(collector.collect(directory, session), result)
                (work / 'UE4SS.log').write_bytes((raw + later + self.outcome(1)).encode())
                with self.assertRaisesRegex(AssertionError, 'late result'):
                    collector.collect(directory, session)

    def test_empty_queue_does_not_inspect_or_mutate_a_research_carrier(self):
        with patch.object(collector, 'verify', return_value=(dict(batches=[]), b'')), \
             patch.object(collector.core, 'current') as current, \
             patch.object(collector.core, 'stage') as stage:
            with self.assertRaisesRegex(AssertionError, 'nothing to query'):
                collector.stage(Path('empty'))
            current.assert_not_called()
            stage.assert_not_called()


if __name__ == '__main__':
    unittest.main()
