import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_grant_skill_gate as gate
from tests.test_boss_skill_repeat_audit import entry, cast, restore


class SkillGateTests(unittest.TestCase):
    def fixture(self):
        manifest = {'id': '071_xianzhe'}
        state = {'state_file': str(Path('official-validation-20261118-220000/state.json'))}
        definition = dict(class_path='Boss0', display_name='弦儿', ability_pool=['Class.Test_C'])
        capture = dict(id='071_xianzhe', state_file=state['state_file'],
                       bindings=[dict(skill='skill_01', class_path='Class.Test_C')])
        header = 'PLAYER_BINDING=slot1|skill_01|F1\n'
        hud = dict(session='official-validation-20261118-220000', at=100, expires_at=200,
                   player='player', text='弦儿 | ACTIVE\n目标：Target0 | 生命 1000')
        live = header + entry() + 'PBZ_PLAYER_UI:STATUS=' + json.dumps(hud, ensure_ascii=False) + '\n'
        return manifest, state, definition, capture, header, live

    def choose(self, tail, purpose, skill=None):
        manifest, state, definition, capture, _, _ = self.fixture()
        return gate.choose_action(tail, manifest, capture, definition, state, purpose, skill, 100)

    def test_enter_and_reenter_require_inactive_and_complete_recovery(self):
        *_, header, live = self.fixture()
        self.assertEqual(self.choose(header, 'enter')['key'], 'F6')
        with self.assertRaises(AssertionError): self.choose(live, 'enter')
        self.assertEqual(self.choose(live + restore(), 'enter')['key'], 'F6')
        with self.assertRaises(AssertionError): self.choose(live + restore().replace('CAMERA_CLEANUP_ENGINE_VERIFIED=true', ''), 'enter')

    def test_cast_uses_only_actual_registered_key_and_fresh_visible_target(self):
        *_, live = self.fixture()
        row = self.choose(live, 'cast', 'skill_01')
        self.assertEqual(row['key'], 'F1'); self.assertEqual(row['class_path'], 'Class.Test_C')
        for tail in (live.replace('|F1', '|F12'), live.replace('|F1', '|F1') + 'PLAYER_BINDING=slot1|skill_01|F1\n' + entry(),
                     live.replace('生命 1000', '生命 0'), live.replace('Target0 |', 'Target0（视线遮挡） |'),
                     live.replace('"at": 100', '"at": 90'), live.replace('class=Class Boss0', 'class=Class Other')):
            with self.assertRaises(AssertionError): self.choose(tail, 'cast', 'skill_01')
        with self.assertRaises(AssertionError): self.choose(live, 'cast', 'heavy_01')

    def test_repeat_waits_for_natural_zero_and_stops_after_native_rejection(self):
        *_, live = self.fixture()
        self.assertEqual(self.choose(live + cast(), 'cast', 'skill_01')['key'], 'F1')
        for suffix in (cast().replace('natural=true', 'natural=false'),
                       cast().replace('|active=0|natural', '|active=1|natural'),
                       cast().split('KEY_SKILL_END=')[0], cast() + 'SKILL_NATIVE_REJECTED=skill_01\n',
                       cast(skill='heavy_01')):
            with self.assertRaises(AssertionError): self.choose(live + suffix, 'cast', 'skill_01')

    def test_exit_does_not_wait_for_target_or_natural_skill_completion(self):
        *_, header, live = self.fixture()
        self.assertEqual(self.choose(live + cast().split('KEY_SKILL_END=')[0], 'exit')['key'], 'F10')
        self.assertEqual(self.choose(live.replace('生命 1000', '生命 0'), 'exit')['key'], 'F10')
        with self.assertRaises(AssertionError): self.choose(header, 'exit')


if __name__ == '__main__': unittest.main()
