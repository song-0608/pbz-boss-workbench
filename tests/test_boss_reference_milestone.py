import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from boss_adaptation_workflow import sha
from run_boss_reference_milestone import CURRENT, collector_modes, record_report


def fixture():
    return dict(base_report='base.json', base_sha256='base', source_sha256={'source.py': 'source'},
        reference_plan=dict(directory='runtime/boss-subtree-references/first',
            manifest_sha256='first', request_counts=dict(unique_queries=272), batches=14, queries=272),
        checks=[dict(name='regressions', passed=True, tests=182, output='Ran tests in 1s')],
        passed=True)


class ReferenceMilestoneTests(unittest.TestCase):
    def test_completed_queue_does_not_schedule_or_advertise_another_native_run(self):
        self.assertEqual(collector_modes(dict(jobs=[])), ())
        self.assertEqual(len(collector_modes(dict(jobs=[dict(key='fixture')]))), 6)
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            report = fixture()
            report['reference_plan'].update(queries=0, batches=0, request_counts=dict(unique_queries=0))
            record_report(report, root)
            pointer = json.loads((root / CURRENT).read_bytes())
            self.assertEqual(pointer['status'], 'reference_type_queue_complete')
            self.assertEqual(pointer['batches'], 0)

    def test_receipt_changed_plan_gets_new_report_with_same_source_bytes(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            first = fixture()
            original = record_report(first, root)
            original_bytes = original.read_bytes()
            changed = copy.deepcopy(first)
            changed['reference_plan'].update(directory='runtime/boss-subtree-references/second',
                                              manifest_sha256='second')
            latest = record_report(changed, root)
            self.assertNotEqual(original, latest)
            self.assertEqual(original.read_bytes(), original_bytes)
            pointer = json.loads((root / CURRENT).read_bytes())
            self.assertEqual(pointer['plan'], changed['reference_plan']['directory'])
            self.assertEqual(pointer['report_sha256'], sha(latest))
            self.assertFalse(pointer['separate_historical_grant_query_required'])
            self.assertEqual(pointer['authentication_state'], 'not_inferred')

    def test_repeated_timing_output_does_not_replace_original_report(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            report = fixture()
            path = record_report(report, root)
            original = path.read_bytes()
            report['checks'][0]['output'] = 'Ran tests in 2s'
            self.assertEqual(record_report(report, root), path)
            self.assertEqual(path.read_bytes(), original)

    def test_failed_check_and_successful_retry_remain_separate(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            failed = fixture()
            failed['passed'] = failed['checks'][0]['passed'] = False
            failure = record_report(failed, root)
            self.assertEqual(json.loads((root / CURRENT).read_bytes())['status'], 'offline_checks_failed')
            success = record_report(fixture(), root)
            self.assertNotEqual(failure, success)
            self.assertFalse(json.loads(failure.read_bytes())['passed'])
            pointer = json.loads((root / CURRENT).read_bytes())
            self.assertEqual(pointer['status'], 'ready_for_isolated_metadata_session')
            self.assertFalse(pointer['playable'] or pointer['native_type_queries_executed'])


if __name__ == '__main__':
    unittest.main()
