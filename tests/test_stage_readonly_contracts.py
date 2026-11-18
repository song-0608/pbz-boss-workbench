import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import stage_readonly_contracts as flow
import ahua_practice as practice
import official_validation as validation


class ContractStageTests(unittest.TestCase):
    def fixture(self, root):
        work = root / 'evidence/official-validation/fixture'; work.mkdir(parents=True)
        target = root / 'mirror/Mods/PBZObserveAI/Scripts/main.lua'
        target.parent.mkdir(parents=True); target.write_bytes(b'-- idle\n')
        log = root / 'mirror/UE4SS.log'; log.write_bytes(b'old log\n')
        state = dict(state_file='owned', deadline_unix=1000,
            ue4ss_loader_manifest=[dict(physical_path=str(target), sha256=flow.sha(target))])
        return dict(root=root, work=work, target=target, log=log, state=state, pid=42)

    def patches(self, f):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(flow, 'current', side_effect=lambda:
            (practice, validation, f['state'], f['work'], f['target'], f['pid'])))
        stack.enter_context(patch.object(flow, 'payload', return_value=(b'-- exact query\n', {'source': 'hash'})))
        stack.enter_context(patch.object(practice, 'log_path', return_value=f['log']))
        stack.enter_context(patch.object(validation, 'save'))
        stack.enter_context(patch.object(validation, 'state_path', return_value=Path('owned')))
        stack.enter_context(patch.object(validation, 'verify_build'))
        stack.enter_context(patch.object(flow.time, 'time', return_value=100))
        return stack

    def test_stage_and_readback_preserve_prior_script_and_reject_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            f = self.fixture(Path(directory).resolve())
            with self.patches(f):
                row = flow.stage()
                self.assertFalse(row['ui_input_sent'])
                self.assertEqual((f['work'] / (flow.LABEL + '-before.lua')).read_bytes(), b'-- idle\n')
                self.assertEqual(f['target'].read_bytes(), b'-- exact query\n')
                flow.snapshot()
                with self.assertRaises(AssertionError): flow.stage()

    def test_snapshot_rejects_process_source_prefix_and_lease_changes(self):
        for mode in ('pid', 'target', 'prefix', 'lease'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                f = self.fixture(Path(directory).resolve())
                with self.patches(f):
                    flow.stage()
                    if mode == 'pid': f['pid'] = 43
                    elif mode == 'target': f['target'].write_bytes(b'changed')
                    elif mode == 'prefix': f['log'].write_bytes(b'changed')
                    else: f['state']['deadline_unix'] = 1100
                    with self.assertRaises(AssertionError): flow.snapshot()

    def test_gate_checks_focus_once_and_does_not_repeat_started_query(self):
        with tempfile.TemporaryDirectory() as directory:
            f = self.fixture(Path(directory).resolve())
            with self.patches(f):
                flow.stage()
                with patch.object(flow.controls, 'foreground_window', side_effect=AssertionError('focus')):
                    with self.assertRaises(AssertionError): flow.reload_gate()
                with patch.object(flow.controls, 'foreground_window', return_value=123):
                    row = flow.reload_gate()
                    self.assertEqual(row['key'], 'Control_L+r')
                    self.assertEqual(row['gate_expires_at'], 110)
                    self.assertFalse(row['input_sent'])
                    f['log'].write_bytes(f['log'].read_bytes() + b'PBZ_CAMERA_CONTRACT:START=query\n')
                    with self.assertRaises(AssertionError): flow.reload_gate()

    def test_query_capture_requires_both_results_and_no_actor_experiment(self):
        good = '\n'.join(token + 'read only' for token in flow.TOKENS)
        row = flow.analyze(good)
        self.assertTrue(row['query_completed']); self.assertFalse(row['playable'])
        for text in (good*2, good.splitlines()[0], good + '\nPBZ_COMBAT_CONTRACT:ISSUE=bad',
                     good + '\nPBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT=1'):
            with self.assertRaises(AssertionError): flow.analyze(text)


if __name__ == '__main__': unittest.main()
