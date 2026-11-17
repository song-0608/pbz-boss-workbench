"""Input authorization follows current native state and the latest assembly."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from player_travel_trial import validate_action


class TravelInputTests(unittest.TestCase):
    def setUp(self):
        self.owner = dict(phase='armed', player_entry=True, log_offset=0,
            actual_controls=dict(enter='F6', exit='F10', cycle_target='F7', lock_target='MIDDLE_MOUSE_BUTTON'),
            actual_bindings=[dict(slot='primary_attack', key='LEFT_MOUSE_BUTTON')])
        self.deployment = dict(player_entry=True)
        self.ready = ('PBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT=1\n'
            'PBZ_CONTROL_LIFECYCLE:PLAYER_BINDING=slot1|skill_01|F1\n'
            'PBZ_CONTROL_LIFECYCLE:PLAYER_BINDING=primary_attack|skill_01|LEFT_MOUSE_BUTTON\n'
            'PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=role\n')
        self.active = self.ready + '[PBZBossControl] enter success=true state=ACTIVE\n'

    def test_primary_requires_current_binding_and_takeover(self):
        self.assertEqual(validate_action('primary', self.owner, self.deployment, self.active), 'LEFT_MOUSE_BUTTON')
        for text in (self.ready, self.active + self.ready.replace('PLAYER_BINDING=primary_attack', 'UNBOUND=primary_attack')):
            with self.assertRaises(AssertionError):
                validate_action('primary', self.owner, self.deployment, text)

    def test_menu_restore_allows_picker_but_not_skill(self):
        opened = self.active + ('PBZ_CONTROL_LIFECYCLE:WORKBENCH_INPUT_LOCKED=owner\n'
                                '[PBZBossControl] workbench_toggle success=true state=OFF\n')
        self.assertEqual(validate_action('picker_confirm', self.owner, self.deployment, opened), 'F6')
        with self.assertRaises(AssertionError):
            validate_action('primary', self.owner, self.deployment, opened)

    def test_new_role_selection_invalidates_previous_takeover(self):
        text = self.active + 'PBZ_CONTROL_LIFECYCLE:WORKBENCH_BOSS_SELECTED=other\n'
        with self.assertRaises(AssertionError):
            validate_action('primary', self.owner, self.deployment, text)

    def test_primary_follows_new_assembly_instead_of_initial_owner(self):
        self.owner['actual_bindings'] = []
        switched = self.active + 'PBZ_CONTROL_LIFECYCLE:WORKBENCH_BOSS_SELECTED=other\n' + self.active
        self.assertEqual(validate_action('primary', self.owner, self.deployment, switched), 'LEFT_MOUSE_BUTTON')
        missing = self.ready.replace('PLAYER_BINDING=primary_attack', 'UNBOUND=primary_attack')
        text = switched + missing + '[PBZBossControl] enter success=true state=ACTIVE\n'
        with self.assertRaises(AssertionError):
            validate_action('primary', self.owner, self.deployment, text)

    def test_duplicate_primary_binding_is_rejected(self):
        duplicate = self.active.replace('PLAYER_ENTRY_READY=role',
            'PLAYER_BINDING=primary_attack|other|LEFT_MOUSE_BUTTON\nPLAYER_ENTRY_READY=role')
        with self.assertRaises(AssertionError):
            validate_action('primary', self.owner, self.deployment, duplicate)

    def test_native_travel_preparation_is_explicit_and_once_only(self):
        text = self.active + ('PBZ_CONTROL_LIFECYCLE:TRANSITION_TRIAL_KEY=F12; restore once '
                              'for native map menu travel\n')
        with self.assertRaises(AssertionError):
            validate_action('prepare_native_travel', self.owner, self.deployment, text)
        self.owner['scene_transition_trial'] = self.deployment['scene_transition_trial'] = True
        self.assertEqual(validate_action('prepare_native_travel', self.owner, self.deployment, text), 'F12')
        with self.assertRaises(AssertionError):
            validate_action('prepare_native_travel', self.owner, self.deployment, text + 'NATIVE_TRAVEL_MENU_READY=true')

    def test_native_light_is_only_the_current_wanjun_slot(self):
        text = self.active.replace('PLAYER_ENTRY_READY=role',
            'PLAYER_BINDING=skill_07|skill_07|F9\nPLAYER_ENTRY_READY=057_wanjun')
        self.assertEqual(validate_action('native_light', self.owner, self.deployment, text), 'F9')
        for changed in (text.replace('057_wanjun', '073_yanqiansui'),
                        text.replace('skill_07|skill_07|F9', 'skill_07|skill_07|Q'),
                        text+'[PBZBossControl] exit success=true state=OFF\n'):
            with self.assertRaises(AssertionError):
                validate_action('native_light', self.owner, self.deployment, changed)


if __name__ == '__main__':
    unittest.main()
