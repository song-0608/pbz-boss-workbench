"""The new preparation separates UI observation without weakening lease or save gates."""
from contextlib import ExitStack
import copy
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import prepare_research_ui as prepare


class ObservedPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.work = self.root / 'evidence/session'
        self.state_path = self.root / 'runtime/state.json'
        self.owner_path = self.root / 'runtime/owner.json'
        self.work.mkdir(parents=True)
        self.state_path.parent.mkdir(parents=True)
        self.now = 1000.0
        self.state = dict(state_file=str(self.state_path), work=str(self.work), deadline_unix=2000,
            deadline_at='fixture deadline', offline_validation=True, network_active=False, restored=False,
            save_gameplay_allowed=True, gameplay_save_probe=True, formal_before={})
        self.owner = dict(state_file=str(self.state_path), phase='preparing', observed_ui_preparation=True)
        prepare.validation.save(self.state_path, self.state)
        prepare.validation.save(self.owner_path, self.owner)
        prepare.validation.save(self.work / 'observed-ui-preparation.json', dict(
            state_file=str(self.state_path), source_sha256=prepare.source_sha(), phase='awaiting-properties-observation'))
        self.screenshot = self.root / 'runtime/steam-menu-private.png'
        self.screenshot.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
        os.utime(self.screenshot, (self.now, self.now))
        self.observation = dict(captured_at=self.now, state_file=str(self.state_path),
            window=dict(id=88, title='[#] 影之刃零 [#]'),
            screenshot_sha256=hashlib.sha256(self.screenshot.read_bytes()).hexdigest())
        stack = self.enterContext(ExitStack())
        self.mocks = {}
        targets = (
            (prepare.validation, 'ROOT', self.root),
            (prepare.validation, 'state_path', lambda: self.state_path),
            (prepare.validation, 'LATEST', self.root / 'no-latest'),
            (prepare.practice, 'OWNER', self.owner_path),
            (prepare.time, 'time', lambda: self.now),
            (prepare.validation.c.preflight, 'games_running', lambda: []),
            (prepare.validation.c.baseline, 'formal_files', lambda: {}),
            (prepare.validation.c.isolation, 'select_box', lambda *a, **k: None),
            (prepare.validation.c.isolation, 'api', lambda: 'fixture'),
            (prepare.validation.c.isolation, 'check_policy', lambda *a, **k: None),
            (prepare.validation.c, 'host_steam_pids', lambda *a: []),
            (prepare.validation.c, 'box_processes', lambda *a: [dict(Name='steamwebhelper.exe', ProcessId=123)]),
            (prepare, 'native_window', lambda *a: dict(pid=123, title=self.observation['window']['title'])),
        )
        for owner, key, value in targets:
            stack.enter_context(patch.object(owner, key, value))
        for owner, key in ((prepare.checkpoint, 'apply'), (prepare.validation, 'finish'),
                           (prepare.validation, 'prepare'), (prepare.gameplay_save_probe, 'prepare'),
                           (prepare, 'active_mod_root')):
            self.mocks[(id(owner), key)] = stack.enter_context(patch.object(owner, key))

    def mock(self, owner, name):
        return self.mocks[(id(owner), name)]

    def test_prepare_keeps_owner_pending_and_does_not_invoke_legacy_ui(self):
        with patch.object(prepare.practice, 'step', side_effect=AssertionError('no legacy UI')):
            result = prepare.prepare()
        self.assertEqual(result['phase'], 'awaiting-properties-observation')
        self.assertEqual(prepare.practice.read(self.owner_path)['phase'], 'preparing')
        self.mock(prepare.validation, 'prepare').assert_called_once_with(launch_ready=True, local_saved=True,
            block_steam_overlay=True, block_nvidia_overlay=True, token_setting='UnstrippedToken',
            offline_validation=True, lease_minutes=20)
        self.mock(prepare.checkpoint, 'apply').assert_not_called()

    def test_prepare_failure_closes_the_research_session(self):
        self.mock(prepare.gameplay_save_probe, 'prepare').side_effect = RuntimeError('save isolation failed')
        with self.assertRaisesRegex(RuntimeError, 'save isolation'):
            prepare.prepare()
        self.mock(prepare.validation, 'finish').assert_called_once()
        self.assertEqual(prepare.practice.read(self.owner_path)['phase'], 'preparation_failed_and_closed')

    def test_acceptance_duration_is_selected_only_when_issuing_a_fresh_lease(self):
        source = "def prepare(**kwargs):\n    assert kwargs['lease_minutes']==40 and kwargs['offline_validation'] is True\n"
        with patch('prepare_offline_acceptance.render', return_value=source) as render:
            result = prepare.prepare(acceptance=True)
        self.assertEqual(result['session_minutes'], 40)
        render.assert_called_once()
        self.mock(prepare.validation, 'prepare').assert_not_called()

    def test_existing_active_session_cannot_be_replaced(self):
        latest = self.root / 'latest.json'
        latest.write_bytes(b'{}')
        with patch.object(prepare.validation, 'LATEST', latest), self.assertRaisesRegex(AssertionError, 'preserve'):
            prepare.prepare()
        self.mock(prepare.validation, 'prepare').assert_not_called()

    def test_complete_records_fresh_properties_then_applies_fixed_checkpoint(self):
        def check_prepared():
            owner = prepare.practice.read(self.owner_path)
            self.assertEqual(owner['phase'], 'prepared')
            self.assertEqual(owner['cloud_screenshot_sha256'], self.observation['screenshot_sha256'])
        self.mock(prepare.checkpoint, 'apply').side_effect = check_prepared
        result = prepare.complete(self.observation, cloud_off_reviewed=True)
        self.assertTrue(result['prepared'])
        self.assertFalse(result['game_started'])
        self.mock(prepare.checkpoint, 'apply').assert_called_once()

    def test_rejects_unreviewed_stale_future_changed_or_wrong_session_observation(self):
        variants = [dict(cloud_off_reviewed=False)]
        for field, value in (('captured_at', 939), ('captured_at', 1001),
                             ('screenshot_sha256', 'changed'), ('state_file', 'other')):
            row = copy.deepcopy(self.observation)
            row[field] = value
            variants.append(dict(observation=row, cloud_off_reviewed=True))
        for kwargs in variants:
            with self.subTest(kwargs=kwargs), self.assertRaises(AssertionError):
                prepare.complete(**dict(dict(observation=self.observation), **kwargs))
        self.mock(prepare.checkpoint, 'apply').assert_not_called()
        self.assertEqual(prepare.practice.read(self.owner_path)['phase'], 'preparing')

    def test_screenshot_clock_is_sampled_after_disk_observation(self):
        original = Path.read_bytes
        def flushed(path):
            result = original(path)
            if path == self.screenshot:
                self.now += 0.125
                os.utime(path, (self.now, self.now))
            return result
        with patch.object(Path, 'read_bytes', flushed):
            digest = prepare.observed_screenshot(self.observation, self.screenshot)
        self.assertEqual(digest, self.observation['screenshot_sha256'])

    def test_screenshot_future_stale_and_invalid_png_remain_rejected(self):
        for modified in (self.now + 0.125, self.now - 60.125):
            os.utime(self.screenshot, (modified, modified))
            with self.subTest(modified=modified), self.assertRaises(AssertionError):
                prepare.observed_screenshot(self.observation, self.screenshot)
        self.screenshot.write_bytes(b'not a PNG')
        os.utime(self.screenshot, (self.now, self.now))
        self.observation['screenshot_sha256'] = hashlib.sha256(self.screenshot.read_bytes()).hexdigest()
        with self.assertRaises(AssertionError):
            prepare.observed_screenshot(self.observation, self.screenshot)

    def test_login_main_window_or_foreign_process_cannot_substitute_for_properties(self):
        for title, pid in (('Steam', 123), ('登录 Steam', 123), ('影之刃零', 999)):
            observation = copy.deepcopy(self.observation)
            observation['window']['title'] = title
            with self.subTest(title=title, pid=pid), patch.object(prepare, 'native_window',
                    return_value=dict(pid=pid, title=title)), self.assertRaises(AssertionError):
                prepare.complete(observation, cloud_off_reviewed=True)
        self.mock(prepare.checkpoint, 'apply').assert_not_called()

    def test_host_steam_formal_change_running_game_or_bad_policy_blocks_completion(self):
        cases = ((prepare.validation.c, 'host_steam_pids', [999]),
                 (prepare.validation.c.baseline, 'formal_files', {'changed': True}),
                 (prepare.validation.c.preflight, 'games_running', [123]))
        for owner, name, result in cases:
            with self.subTest(name=name), patch.object(owner, name, return_value=result), self.assertRaises(AssertionError):
                prepare.complete(self.observation, cloud_off_reviewed=True)
        with patch.object(prepare.validation.c.isolation, 'check_policy', side_effect=RuntimeError('policy')):
            with self.assertRaisesRegex(RuntimeError, 'policy'):
                prepare.complete(self.observation, cloud_off_reviewed=True)
        self.mock(prepare.checkpoint, 'apply').assert_not_called()

    def test_checkpoint_failure_closes_session_instead_of_leaving_it_launchable(self):
        self.mock(prepare.checkpoint, 'apply').side_effect = RuntimeError('checkpoint drift')
        with self.assertRaisesRegex(RuntimeError, 'checkpoint drift'):
            prepare.complete(self.observation, cloud_off_reviewed=True)
        self.mock(prepare.validation, 'finish').assert_called_once()
        self.assertEqual(prepare.practice.read(self.owner_path)['phase'], 'checkpoint_failed_and_closed')

    def test_cleanup_failure_still_revokes_launchability_and_retains_original_error(self):
        self.mock(prepare.checkpoint, 'apply').side_effect = RuntimeError('checkpoint drift')
        self.mock(prepare.validation, 'finish').side_effect = RuntimeError('cleanup failure')
        with self.assertRaisesRegex(RuntimeError, 'checkpoint drift') as result:
            prepare.complete(self.observation, cloud_off_reviewed=True)
        self.assertEqual(prepare.practice.read(self.owner_path)['phase'], 'checkpoint_failed')
        self.assertIn('cleanup failure', str(result.exception.__notes__))


if __name__ == '__main__':
    unittest.main()
