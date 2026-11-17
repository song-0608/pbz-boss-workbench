import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from player_experience_trial import validate_action


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.owner=dict(phase='armed',player_entry=True,log_offset=0,
            actual_controls=dict(enter='F6',exit='F10',cycle_target='F7',lock_target='MIDDLE_MOUSE_BUTTON'),
            actual_bindings=[dict(slot='slot1',skill='skill_01',key='F1')])
        self.deployment=dict(player_entry=True)
        self.active='[PBZBossControl] enter success=true state=ACTIVE\n'

    def test_gameplay_requires_fresh_successful_takeover(self):
        for action in ('cast','shift_cast','lock','cycle_target','exit'):
            self.assertIsInstance(validate_action(action,self.owner,self.deployment,self.active),str)
            for text in ('',self.active+'[PBZBossControl] exit success=true\n',
                         self.active+'[PBZBossControl] auto_exit success=true\n'):
                with self.assertRaises(AssertionError):validate_action(action,self.owner,self.deployment,text)

    def test_bad_source_or_runtime_state_never_permits_input(self):
        for changed in (dict(phase='closed'),dict(skill_lab=True),dict(expanded=True),
                        dict(actual_bindings=[dict(slot='slot1',skill='invented',key='F1')]),
                        dict(actual_controls=dict(self.owner['actual_controls'],lock_target='F12'))):
            with self.assertRaises(AssertionError):
                validate_action('shift_cast',dict(self.owner,**changed),self.deployment,self.active)
        for fault in ('state=FAULTED','ISSUE_TEST=bad','[Lua::execute_file]'):
            with self.assertRaises(AssertionError):
                validate_action('cast',self.owner,self.deployment,self.active+fault)
        with self.assertRaises(AssertionError):validate_action('arbitrary',self.owner,self.deployment,self.active)

    def test_selection_only_in_open_restored_workbench(self):
        for action in ('down','up','confirm','close'):
            with self.assertRaises(AssertionError):validate_action(action,self.owner,self.deployment,'')
            self.assertIsInstance(validate_action(action,self.owner,self.deployment,
                'WORKBENCH_INPUT_LOCKED=true'),str)
            with self.assertRaises(AssertionError):validate_action(action,self.owner,self.deployment,
                'WORKBENCH_INPUT_LOCKED=true\nWORKBENCH_INPUT_RESTORED=true')


if __name__=='__main__':unittest.main()
