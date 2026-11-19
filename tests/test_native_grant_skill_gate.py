import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_grant_skill_gate as gate
from tests.test_boss_skill_repeat_audit import entry, cast, restore


class SkillGateTests(unittest.TestCase):
    def test_new_work_cannot_consume_the_existing_restoration_reserve(self):
        receipt, state = dict(grant_expires_at=1000), dict(deadline_unix=2000)
        for purpose, reserve in (('enter', 120), ('cast', 90), ('exit', 30)):
            with self.subTest(purpose=purpose):
                self.assertEqual(gate.remaining_budget(receipt, state, purpose, 999-reserve), (reserve, reserve+1))
                with self.assertRaises(AssertionError): gate.remaining_budget(receipt, state, purpose, 1000-reserve)
        # The observed late-cast case: still enough for F10, insufficient to
        # start another skill and subsequently pass a new F10 validation.
        with self.assertRaises(AssertionError): gate.remaining_budget(receipt, state, 'cast', 950)
        self.assertEqual(gate.remaining_budget(receipt, state, 'exit', 950), (30, 50))
        # The session's independent cleanup deadline can be the shorter bound.
        with self.assertRaises(AssertionError):
            gate.remaining_budget(receipt, dict(deadline_unix=1100), 'cast', 900)

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

    def cancel_fixture(self):
        manifest, state, definition, capture, header, live = self.fixture()
        manifest.update(kind='native_combo_ui_stage', developer_only=True, playable=False, bundle='fixture')
        definition['parent_class'] = definition['ability_pool'][0]
        return manifest, state, definition, capture, header, live

    def test_cancel_pair_uses_current_registered_cast_and_same_takeover_recovery(self):
        m, s, d, c, _, live = self.cancel_fixture()
        actions = gate.choose_cancel_trial(live, m, c, d, s, 'skill_01', 100)
        self.assertEqual([(r['purpose'], r['key']) for r in actions], [('cast', 'F1'), ('exit', 'F10')])
        self.assertEqual(actions[0]['identity'], actions[1]['identity'])
        for field, value in (('kind', 'inventory_skill_ui_stage'), ('developer_only', False), ('playable', True)):
            changed = dict(m, **{field: value})
            with self.subTest(field=field), self.assertRaises(AssertionError):
                gate.choose_cancel_trial(live, changed, c, d, s, 'skill_01', 100)
        for text in (live + cast().split('KEY_SKILL_END=')[0],
                     live + 'SKILL_NATIVE_REJECTED=skill_01\n', live.replace('生命 1000', '生命 0')):
            with self.assertRaises(AssertionError): gate.choose_cancel_trial(text, m, c, d, s, 'skill_01', 100)
        with self.assertRaises(AssertionError): gate.choose_cancel_trial(live, m, c, d, s, None, 100)
        with self.assertRaises(AssertionError):
            gate.choose_cancel_trial(live, m, c, dict(d, parent_class='other parent'), s, 'skill_01', 100)

    def test_paired_gate_replays_once_retains_cast_reserve_and_issues_only_ten_seconds(self):
        m, s, d, c, header, live = self.cancel_fixture()
        receipt = dict(workflow_manifest_sha256='frozen', research_pid=77, grant_expires_at=1000)
        with tempfile.TemporaryDirectory() as directory:
            s.update(work=directory, deadline_unix=2000)
            c.update(workflow_manifest_sha256='frozen', initialization_observed=True, lines=header.splitlines())
            capture_path = Path(directory) / (gate.flow.LABEL + '-capture.json')
            capture_path.write_text(json.dumps(c), encoding='utf-8')
            with patch.dict(sys.modules, {'official_validation': SimpleNamespace()}), \
                    patch.object(gate.flow, 'staged_guard', return_value=(m, s, receipt, live)) as replay, \
                    patch.object(gate.flow.bundle, 'read', return_value=dict(definition=d)), \
                    patch.object(gate.flow, 'foreground_window', return_value=321) as foreground, \
                    patch.object(gate.time, 'time', side_effect=[100, 106]), \
                    patch.object(gate.time, 'time_ns', return_value=7), \
                    patch.object(gate, 'uuid4', return_value=SimpleNamespace(hex='fixture')):
                result = gate.gate(Path(directory), 'cast-cancel', 'skill_01')
            replay.assert_called_once_with(Path(directory)); foreground.assert_called_once()
            self.assertEqual(result['gate_expires_at'], 116)
            self.assertEqual(result['action_and_restore_reserve_seconds'], 90)
            self.assertFalse(result['input_sent'] or result['active_cancellation_observed'])
            self.assertEqual(result['max_action_count'], 2)
            self.assertEqual([r['key'] for r in result['actions']], ['F1', 'F10'])
            saved = Path(directory) / 'native-grant-skill-gate-cast-cancel-7-fixture.json'
            self.assertEqual(json.loads(saved.read_bytes()), result)
            # Foreground checks cannot use up the remaining cast/recovery
            # reserve and still issue a seemingly fresh permission.
            with patch.dict(sys.modules, {'official_validation': SimpleNamespace()}), \
                    patch.object(gate.flow, 'staged_guard', return_value=(m, s, receipt, live)), \
                    patch.object(gate.flow.bundle, 'read', return_value=dict(definition=d)), \
                    patch.object(gate.flow, 'foreground_window', return_value=321), \
                    patch.object(gate.time, 'time', side_effect=[900, 910]):
                with self.assertRaises(AssertionError): gate.gate(Path(directory), 'cast-cancel', 'skill_01')
            self.assertEqual(list(Path(directory).glob('native-grant-skill-gate-*')), [saved])

    def test_same_clock_tick_keeps_all_receipts_separate_and_never_overwrites(self):
        m, s, d, c, header, live = self.fixture()
        m['bundle'] = 'fixture'
        receipt = dict(workflow_manifest_sha256='frozen', research_pid=77, grant_expires_at=1000)
        with tempfile.TemporaryDirectory() as directory:
            s.update(work=directory, deadline_unix=2000)
            c.update(workflow_manifest_sha256='frozen', initialization_observed=True, lines=header.splitlines())
            (Path(directory) / (gate.flow.LABEL + '-capture.json')).write_text(json.dumps(c), encoding='utf-8')
            with patch.dict(sys.modules, {'official_validation': SimpleNamespace()}), \
                    patch.object(gate.flow, 'staged_guard', return_value=(m, s, receipt, live)), \
                    patch.object(gate.flow.bundle, 'read', return_value=dict(definition=d)), \
                    patch.object(gate.flow, 'foreground_window', return_value=321), \
                    patch.object(gate.time, 'time', return_value=100), \
                    patch.object(gate.time, 'time_ns', return_value=7), \
                    patch.object(gate, 'uuid4', side_effect=[SimpleNamespace(hex=v) for v in ('a', 'b', 'a', 'a')]):
                first = gate.gate(Path(directory), 'cast', 'skill_01')
                repeated = gate.gate(Path(directory), 'cast', 'skill_01')
                second = gate.gate(Path(directory), 'exit')
                with self.assertRaises(FileExistsError): gate.gate(Path(directory), 'cast', 'skill_01')
            for purpose, suffix, value in (('cast', 'a', first), ('cast', 'b', repeated), ('exit', 'a', second)):
                path = Path(directory) / ('native-grant-skill-gate-' + purpose + '-7-' + suffix + '.json')
                self.assertEqual(json.loads(path.read_bytes()), value)
            self.assertEqual(len(list(Path(directory).glob('native-grant-skill-gate-*'))), 3)


if __name__ == '__main__': unittest.main()
