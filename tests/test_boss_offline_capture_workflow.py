import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import boss_offline_capture_workflow as workflow


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.files = [self.root/name for name in ('index.csv', 'exact.usmap', 'declarations.dll', 'scripts.dll', 'private.json')]
        for path in self.files:
            path.write_bytes(b'test local input')
        self.paks = self.root/'paks'; self.paks.mkdir()
        self.source = self.root/'source'; self.source.mkdir()
        self.target = self.root/'output'

    def run_capture(self, **kwargs):
        index, mapping, exporter, script_exporter, crypto = self.files
        return workflow.capture(index, mapping, [self.source], [], self.target,
            exporter, script_exporter, self.paks, crypto, **kwargs)

    def report(self, pending=0):
        return dict(extracted_packages=1, pending_dependency_count=pending,
            failed_dependency_count=1, unindexed_references=['/Other/Unavailable'],
            unresolved_script_functions=0, ability_indexing_issues=0, packages=[],
            root_packages=1, extracted_roots=1, ability_classes=1, declared_actions=7)

    def test_convergence_keeps_known_gaps_and_never_claims_final_mod(self):
        with patch.object(workflow.dependencies, 'scan', return_value=self.report()), \
                patch.object(workflow.dependencies, 'collect') as collect:
            result = self.run_capture()
        self.assertEqual(result['status'], 'converged_with_known_gaps')
        self.assertTrue(result['bounded_traversal_completed'])
        self.assertFalse(result['ready_for_final_delivery'])
        self.assertFalse(result['game_started'])
        collect.assert_not_called()
        self.assertEqual(json.loads((self.target/'result.json').read_bytes()), result)
        with self.assertRaises(FileExistsError):
            self.run_capture()

    def test_round_limit_does_not_turn_last_extraction_into_verified_convergence(self):
        with patch.object(workflow.dependencies, 'scan', return_value=self.report(pending=1)), \
                patch.object(workflow.dependencies, 'dependencies'), \
                patch.object(workflow.dependencies, 'collect', return_value=dict(extracted=1, failed=0, pending=0)):
            result = self.run_capture(max_rounds=1)
        self.assertEqual(result['status'], 'round_limit_reached')
        self.assertFalse(result['bounded_traversal_completed'])
        self.assertFalse(result['ready_for_final_delivery'])
        self.assertFalse(result['rounds'][0]['terminal'])

    def test_no_workflow_output_under_game_packages_and_no_unbounded_rounds(self):
        self.target = self.paks/'forbidden'
        with self.assertRaisesRegex(ValueError, 'outside game packages'):
            self.run_capture()
        self.assertFalse(self.target.exists())
        with self.assertRaisesRegex(ValueError, 'bounded offline rounds'):
            self.run_capture(max_rounds=0)

    def test_deferred_global_cache_keeps_workflow_in_known_gaps_with_pinned_policy(self):
        report=self.report()
        report.update(failed_dependency_count=0,unindexed_references=[],
            deferred_dependency_count=1,dependency_policy='defer_global_cinematic_prestream_cache')
        with patch.object(workflow.dependencies,'scan',return_value=report) as scan:
            result=self.run_capture()
        self.assertEqual(result['status'],'converged_with_known_gaps')
        self.assertEqual(result['deferred_dependencies'],1)
        self.assertEqual(result['dependency_policy'],'defer_global_cinematic_prestream_cache')
        self.assertTrue(scan.call_args.kwargs['defer_cinematic_cache'])
        self.assertTrue(json.loads((self.target/'workflow.json').read_bytes())['defer_cinematic_cache'])
        self.assertFalse(result['ready_for_final_delivery'])

    def test_next_round_reuses_previous_immutable_scan(self):
        with patch.object(workflow.dependencies,'scan',side_effect=[self.report(pending=1),self.report()]) as scan, \
                patch.object(workflow.dependencies,'dependencies'), \
                patch.object(workflow.dependencies,'collect',return_value=dict(extracted=1,failed=0,pending=0)):
            result=self.run_capture(max_rounds=2)
        self.assertIsNone(scan.call_args_list[0].kwargs['reuse_scan'])
        self.assertEqual(scan.call_args_list[1].kwargs['reuse_scan'],self.target/'scan-0001.json')
        self.assertTrue(result['bounded_traversal_completed'])

    def test_initial_scan_changes_stop_capture_before_next_round(self):
        initial=self.root/'initial.json';initial.write_text('{}',encoding='utf-8')
        def collect(*args):
            initial.write_text('{"changed":true}',encoding='utf-8')
            return dict(extracted=1,failed=0,pending=0)
        with patch.object(workflow.dependencies,'scan',return_value=self.report(pending=1)), \
                patch.object(workflow.dependencies,'dependencies'), \
                patch.object(workflow.dependencies,'collect',side_effect=collect):
            with self.assertRaisesRegex(ValueError,'Pinned initial scan changed'):
                self.run_capture(reuse_scan=initial)
        self.assertFalse((self.target/'result.json').exists())


if __name__ == '__main__':
    unittest.main()
