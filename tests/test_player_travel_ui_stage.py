import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import player_travel_ui_stage as stage
from player_travel_ui_stage import initialization, initialization_status


READY = '\n'.join(('PBZ_CONTROL_LIFECYCLE:INTERACTIVE_READY=one',
    'PBZ_CONTROL_LIFECYCLE:MAP_TRAVEL_GUARD_READY=true',
    'PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=056_youlong',
    'PBZ_CONTROL_LIFECYCLE:PLAYER_BINDING=slot1|skill_01|F1'))


class PlayerTravelUIStageTests(unittest.TestCase):
    def test_native_combat_development_launch_is_injected_once_before_entry(self):
        original=b'prefix\nPBZBossControlLaunch={boss_id="ahua",options={}}\nreturn run()\n'
        contract=dict(pid=42,cues={'class_path':'/Cue'},defense_by_role={},native_input_binding_verified=True)
        output=stage.combat_launch_payload(original,contract)
        self.assertIn(b'options.developer_only=true',output)
        self.assertLess(output.index(b'options.native_combat_contract='),output.index(b'return run()'))
        self.assertTrue(output.endswith(b'return run()\n'))
        for invalid in (output,original+original,b'unknown'):
            with self.assertRaises(AssertionError):stage.combat_launch_payload(invalid,contract)

    def test_controls_use_exact_frozen_schema_and_reject_changed_or_legacy_bindings(self):
        controls = dict(enter='F6', exit='F10', cycle_target='F7', lock_target='MIDDLE_MOUSE_BUTTON')
        with tempfile.TemporaryDirectory() as name:
            flow = Path(name)
            source = flow / 'player_keymap.py'
            source.write_text('def validate(value):\n    return value\n', encoding='utf-8')
            record = dict(files={'player_keymap.py': hashlib.sha256(source.read_bytes()).hexdigest()})
            with patch.object(stage.workflow, 'verify', return_value=record):
                self.assertEqual(stage.frozen_controls(flow, dict(player_keymap=dict(controls=controls))), controls)
                legacy = {k: v for k, v in controls.items() if k != 'lock_target'}
                wrong = dict(controls, lock_target='F8')
                for value in (legacy, wrong, dict(controls, unexpected='F9')):
                    with self.subTest(value=value), self.assertRaises(AssertionError):
                        stage.frozen_controls(flow, dict(player_keymap=dict(controls=value)))
                source.write_text('def validate(value):\n    raise RuntimeError("changed")\n', encoding='utf-8')
                with self.assertRaises(AssertionError):
                    stage.frozen_controls(flow, dict(player_keymap=dict(controls=controls)))

    def test_bad_keymap_cannot_leave_a_partial_capture_or_arm_owner(self):
        with tempfile.TemporaryDirectory() as name:
            owner = dict(phase='game_launched')
            state = dict(work=name)
            with patch.object(stage, 'snapshot', return_value=(owner, state, {}, {}, READY)), \
                 patch.object(stage, 'frozen_controls', side_effect=AssertionError('wrong keymap')), \
                 patch.object(stage.practice, 'save_owner') as save, \
                 patch.object(stage.subprocess, 'Popen') as popen:
                with self.assertRaisesRegex(AssertionError, 'wrong keymap'):
                    stage.capture(Path(name))
                self.assertEqual(list(Path(name).iterdir()), [])
                self.assertEqual(owner['phase'], 'game_launched')
                save.assert_not_called()
                popen.assert_not_called()

    def test_normal_capture_persists_four_controls_and_arms_once(self):
        controls = dict(enter='F6', exit='F10', cycle_target='F7', lock_target='MIDDLE_MOUSE_BUTTON')
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'runtime').mkdir()
            owner, state = dict(phase='game_launched'), dict(work=name)
            with patch.object(stage, 'ROOT', root), \
                 patch.object(stage, 'snapshot', return_value=(owner, state, dict(log_offset=5), {}, READY)), \
                 patch.object(stage, 'frozen_controls', return_value=controls), \
                 patch.object(stage.practice, 'save_owner') as save, \
                 patch.object(stage.subprocess, 'Popen') as popen:
                popen.return_value.pid = 123
                result = stage.capture(root)
                recorded = json.loads((root / (stage.LABEL + '-capture.json')).read_bytes())
                self.assertEqual(recorded['controls'], controls)
                self.assertEqual(owner['actual_controls'], controls)
                self.assertEqual(owner['phase'], 'armed')
                self.assertFalse(result['input_sent'] or result['runtime_acceptance_current'])
                self.assertEqual(popen.call_count, 2)
                self.assertEqual(save.call_count, 2)
                owner['phase'] = 'armed'
                with self.assertRaises(AssertionError):
                    stage.capture(root)

    def test_pending_status_names_missing_stages_without_claiming_acceptance(self):
        pending = initialization_status('PBZ_CONTROL_LIFECYCLE:PRIMARY_READY_BEFORE_TARGET=true')
        self.assertFalse(pending['complete'])
        self.assertEqual(len(pending['missing']), 3)
        self.assertFalse(pending['input_sent'] or pending['runtime_acceptance_current'])
        self.assertIn('PRIMARY_READY_BEFORE_TARGET', pending['last_stage'])
        self.assertTrue(initialization_status(READY)['complete'])
        self.assertFalse(initialization_status(READY + '\n' + READY)['complete'])
        self.assertFalse(initialization_status(READY + '\nPBZ_CONTROL_LIFECYCLE:ISSUE_READY=error')['complete'])

    def test_idle_complete_initialization_only(self):
        self.assertEqual(initialization(READY), [dict(slot='slot1', skill='skill_01', key='F1')])
        for broken in (READY + '\n' + READY, READY.replace('MAP_TRAVEL_GUARD_READY=true', 'MAP_TRAVEL_GUARD_READY=false'),
                       READY + '\n[PBZBossControl] enter success=true state=ACTIVE',
                       READY + '\nPBZ_CONTROL_LIFECYCLE:ISSUE_INIT=failed',
                       READY + '\nPBZ_CONTROL_LIFECYCLE:PLAYER_BINDING=slot1|other|F2'):
            with self.subTest(broken=broken), self.assertRaises(AssertionError):
                initialization(broken)

    def test_candidate_workflow_contains_no_legacy_ui_reload(self):
        import build_player_travel_candidate as candidate
        import player_travel_workflow as workflow
        manifest, _ = candidate.expected()
        with patch.object(candidate, 'build', side_effect=AssertionError('source test must not build a package')), \
             patch.object(candidate, 'verify', side_effect=AssertionError('source test must not need a package')):
            files = workflow.render(Path('uninstalled-source-fixture'), manifest)
        source = files['run_control_lifecycle_probe.py'].decode('utf-8')
        self.assertNotIn('research_game_menu', source)
        self.assertNotIn('menu.click', source)
        self.assertIn('collect_3c', source)
        self.assertIn('separate fresh window reload gate', source)


if __name__ == '__main__':
    unittest.main()
