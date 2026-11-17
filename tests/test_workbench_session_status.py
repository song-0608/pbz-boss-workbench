"""UI safety checks use synthetic state; never start or control the game."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import boss_workbench_v5_window as base_window
import workbench_session_status as status
import workbench_status_bootstrap as bootstrap


class SessionStatusTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.state_path = self.root / 'runtime/official-validation-20261117-210000/state.json'
        self.state = dict(restored=False, deadline_unix=2000, control_probe_expires_at=1600)
        self.owner = dict(state_file=str(self.state_path), phase='prepared',
            actual_controls=dict(enter='F6', exit='F10', cycle_target='F7', lock_target='MIDDLE_MOUSE_BUTTON'),
            actual_bindings=[dict(key='F1', skill='skill_01')])
        self.save()

    def save_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def save(self):
        self.save_json(self.state_path, self.state)
        self.save_json(self.root / 'runtime/ahua-practice.json', self.owner)
        self.save_json(self.root / 'runtime/latest-official-validation.json', dict(state_file=str(self.state_path)))

    def view(self):
        return status.snapshot(self.root, now=1000)

    def test_phase_buttons_only_offer_the_next_valid_step(self):
        for phase, expected in [('prepared', 'launch'), ('game_launched', 'arm'), ('armed', 'stop')]:
            with self.subTest(phase=phase):
                self.owner['phase'] = phase; self.save()
                view = self.view()
                self.assertEqual(view.phase, phase)
                self.assertIn(expected, view.allowed)
                self.assertNotIn('prepare', view.allowed)
                if phase == 'armed':
                    self.assertNotIn('launch', view.allowed); self.assertNotIn('arm', view.allowed)
                    self.assertIn('10:00', view.message)
                    self.assertIn('F1 skill_01', view.bindings)

    def test_expired_grant_only_allows_cleanup(self):
        self.owner['phase'] = 'armed'; self.state['control_probe_expires_at'] = 999; self.save()
        self.assertEqual(self.view().phase, 'control_expired')
        self.assertEqual(self.view().allowed, ('stop', 'status'))

    def test_expired_session_does_not_offer_prepare_before_cleanup(self):
        self.state['deadline_unix'] = 999; self.save()
        self.assertEqual(self.view().phase, 'expired')
        self.assertEqual(self.view().allowed, ('stop', 'status'))

    def test_restored_with_pending_postcheck_cannot_start_a_new_round(self):
        self.state['restored'] = True; self.owner['postcheck_review_required'] = True; self.save()
        self.assertEqual(self.view().phase, 'postcheck')
        self.assertNotIn('prepare', self.view().allowed)
        self.owner['postcheck_review_required'] = False; self.save()
        self.assertEqual(self.view().allowed, ('prepare', 'status'))

    def test_foreign_session_cannot_be_stopped_or_overwritten(self):
        self.owner['state_file'] = str(self.root / 'runtime/official-validation-20261117-190000/state.json')
        self.save()
        self.assertEqual(self.view().phase, 'foreign')
        self.assertEqual(self.view().allowed, ('status',))

    def test_partial_json_and_unexpected_paths_fail_closed(self):
        self.state_path.write_text('{', encoding='utf-8')
        self.assertEqual(self.view().allowed, ('status',))
        self.save_json(self.root / 'runtime/latest-official-validation.json', dict(state_file=str(self.root / 'outside.json')))
        self.assertEqual(self.view().phase, 'unavailable')

    def test_snapshot_is_read_only_and_uses_saved_control_limits(self):
        paths = [self.state_path, self.root / 'runtime/ahua-practice.json', self.root / 'runtime/latest-official-validation.json']
        before = {path: path.read_bytes() for path in paths}
        self.owner['phase'] = 'armed'; self.state.pop('control_probe_expires_at'); self.save()
        self.assertEqual(self.view().phase, 'unavailable')
        after_save = {path: path.read_bytes() for path in paths}
        self.view()
        self.assertEqual(after_save, {path: path.read_bytes() for path in paths})
        self.assertNotEqual(before, after_save)

    def test_no_session_has_only_prepare_and_status(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(status.snapshot(directory).allowed, ('prepare', 'status'))
            self.assertFalse((Path(directory) / 'runtime').exists())

    def test_action_lock_blocks_a_second_window_and_releases(self):
        first, second = status.ActionLease(self.root), status.ActionLease(self.root)
        try:
            self.assertTrue(first.acquire()); self.assertFalse(second.acquire())
            self.assertFalse(status.action_available(self.root))
            first.release(); self.assertTrue(second.acquire())
        finally:
            first.release(); second.release()
        self.assertTrue(status.action_available(self.root))

    def test_operating_system_releases_lock_after_process_exit(self):
        program = ('import sys;sys.path.insert(0,sys.argv[1]);from workbench_session_status import ActionLease;'
                   'lock=ActionLease(sys.argv[2]);assert lock.acquire()')
        result = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-c', program, str(ROOT / 'tools'), str(self.root)],
            capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        self.assertTrue(status.action_available(self.root))


class RenderedGuardTests(unittest.TestCase):
    def rendered(self):
        return bootstrap.render(base_window.render(ROOT / 'runtime/player-workflows/test', 6))

    def test_overlay_keeps_original_backend_path_and_explicit_input_gates(self):
        source = self.rendered(); ast.parse(source)
        self.assertIn("else PLAYER_FLOW / 'ahua_practice.py'", source)
        self.assertIn("'tools/research_scene_checkpoint.py'", source)
        self.assertIn('lease.release()', source)
        self.assertIn('window.after(1000, refresh_session)', source)
        self.assertNotIn('先点第1步，等待准备完成', source)

    def test_already_armed_jobs_do_not_dispatch_or_acquire_a_lease(self):
        node = next(n for n in ast.walk(ast.parse(self.rendered())) if isinstance(n, ast.FunctionDef) and n.name == 'job')
        view = status.SessionView('armed', 'Boss已启用', ('stop', 'status'))
        lease = Mock(side_effect=AssertionError('No lease for rejected step'))
        thread = Mock(side_effect=AssertionError('No worker for rejected step'))
        notice, add_line = Mock(), Mock()
        scope = dict(busy={'value': False}, snapshot=lambda root: view, ROOT=ROOT,
            status=notice, add_line=add_line, ActionLease=lease, threading=types.SimpleNamespace(Thread=thread))
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<guard-test>', 'exec'), scope)
        for action in ('prepare', 'launch', 'arm'):
            scope['job'](action)
        self.assertEqual(notice.set.call_count, 3)
        lease.assert_not_called(); thread.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Windows Tk integration')
    def test_real_window_disables_repeat_steps_and_shows_saved_bindings(self):
        import tkinter as tk
        from tkinter import ttk
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); state_path = root / 'runtime/official-validation-20261117-210000/state.json'
            state_path.parent.mkdir(parents=True)
            state_path.write_text(json.dumps(dict(restored=False, deadline_unix=time.time()+300,
                control_probe_expires_at=time.time()+200)), encoding='utf-8')
            (root / 'runtime/latest-official-validation.json').write_text(
                json.dumps(dict(state_file=str(state_path))), encoding='utf-8')
            (root / 'runtime/ahua-practice.json').write_text(json.dumps(dict(state_file=str(state_path), phase='armed',
                actual_controls=dict(enter='F6',exit='F10',cycle_target='F7'),
                actual_bindings=[dict(key='F1',skill='skill_01')])), encoding='utf-8')
            scope = dict(__name__='ui_test', __file__=str(ROOT / 'tools/ahua_practice_window.py'))
            exec(compile(self.rendered(), '<window-test>', 'exec'), scope)
            scope['ROOT'] = root
            scope['player_settings'] = types.SimpleNamespace(BOSSES={'ahua':'阿花'}, read=lambda:dict(boss_id='ahua'))
            create = tk.Tk; observed = []; errors = []
            def factory():
                window = create()
                def inspect():
                    try:
                        widgets = list(window.winfo_children()); all_widgets = []
                        while widgets:
                            widget = widgets.pop(); all_widgets.append(widget); widgets.extend(widget.winfo_children())
                        buttons = {str(w.cget('text'))[0]:w for w in all_widgets if isinstance(w,ttk.Button)
                            and str(w.cget('text'))[:1] in ('1','2','3','4')}
                        self.assertEqual(set(buttons), {'1','2','3','4'})
                        for key in ('1','2','3'): self.assertTrue(buttons[key].instate(['disabled']))
                        self.assertFalse(buttons['4'].instate(['disabled']))
                        labels = '\n'.join(str(w.cget('text')) for w in all_widgets if isinstance(w,ttk.Label))
                        self.assertIn('Boss已启用',labels); self.assertIn('F1 skill_01',labels)
                        observed.append(True)
                    except Exception as error:
                        errors.append(error)
                    finally:
                        window.destroy()
                window.after(50,inspect)
                return window
            with patch.object(tk,'Tk',side_effect=factory), patch('subprocess.Popen',side_effect=AssertionError('No backend dispatch')):
                scope['main'](smoke=True)
            if errors: raise errors[0]
            self.assertEqual(observed,[True])


if __name__ == '__main__':
    unittest.main()
