import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import verify_research_scene_reload as reload_check


class SceneReloadTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.storage = self.root / 'saved-scenes'
        saved = self.storage / 'arena'
        (saved / 'SaveGames').mkdir(parents=True)
        (saved / 'SaveGames/main.sav').write_bytes(b'game-authored-test-save')
        self.checkpoint = dict(label=reload_check.LABEL, directory=str(saved),
                               files=reload_check.save_snapshot(saved))
        self.write(saved / 'checkpoint.json', self.checkpoint)
        self.write(self.storage / '当前研究场景.json', self.checkpoint)
        self.session = '20261117-170957'
        self.work = self.root / 'evidence/official-validation' / self.session
        state_path = self.root / 'runtime' / ('official-validation-' + self.session) / 'state.json'
        self.state = dict(state_file=str(state_path), work=str(self.work), restored=True,
                          offline_validation=True, launch_requested_at='2026-11-17T17:11:00+08:00',
                          network_active=False, remaining_box_pids=[], formal_files_changed=[],
                          host_config_files_changed=[])
        self.write(state_path, self.state)
        self.post = dict(validation_state=str(state_path), research_box_empty=True,
                         research_loader_removed=True, validation_restored=True,
                         host_registry_unchanged=True, all_temporary_network_removed=True,
                         formal_files_changed=[], host_config_files_changed=[], remaining_games=[])
        self.write(self.work / 'postcheck.json', self.post)
        self.write(self.work / 'research-checkpoint-applied.json',
                   dict(checkpoint=self.checkpoint, formal_files_modified=False))
        (self.work / 'UE4SS.log').write_text('test fixture: loader only', encoding='utf-8')
        script = self.root / 'tools/verify_research_scene_reload.py'
        script.parent.mkdir()
        script.write_text('# test fixture', encoding='utf-8')
        self.report_path = self.root / 'receipt.json'
        self.report = dict(schema=1, label=reload_check.LABEL, session=self.session,
                           checkpoint_manifest_sha256=reload_check.digest(saved / 'checkpoint.json'),
                           checkpoint_file_count=1,
                           observation=dict(method='assistant_visual_observation_via_computer_use',
                                            title_continue_observed=True,
                                            direct_open_area_spawn_observed=True,
                                            no_travel_or_teleport_performed=True,
                                            mod_not_armed=True, landmarks=['fixture arena']), sources={})
        self.refresh_sources()
        for item in (patch.object(reload_check, 'ROOT', self.root),
                     patch.object(reload_check, 'storage', return_value=self.storage),
                     patch.object(reload_check, 'assert_closed')):
            item.start()
            self.addCleanup(item.stop)

    @staticmethod
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def refresh_sources(self):
        files = [self.root / 'runtime' / ('official-validation-' + self.session) / 'state.json',
                 self.work / 'postcheck.json', self.work / 'research-checkpoint-applied.json',
                 self.work / 'UE4SS.log', self.root / 'tools/verify_research_scene_reload.py']
        self.report['sources'] = {p.relative_to(self.root).as_posix(): reload_check.digest(p) for p in files}
        self.write(self.report_path, self.report)

    def test_complete_closed_observation_verifies(self):
        self.assertTrue(reload_check.verify(self.report_path)['reload_verified'])

    def test_formal_change_rejected_even_with_matching_report_hash(self):
        self.post['formal_files_changed'] = ['changed-file']
        self.write(self.work / 'postcheck.json', self.post)
        self.refresh_sources()
        with self.assertRaises(AssertionError):
            reload_check.verify(self.report_path)

    def test_different_checkpoint_application_is_rejected(self):
        other = dict(self.checkpoint, label='different scene')
        self.write(self.work / 'research-checkpoint-applied.json', dict(checkpoint=other, formal_files_modified=False))
        self.refresh_sources()
        with self.assertRaises(AssertionError):
            reload_check.verify(self.report_path)

    def test_no_visual_observation_cannot_be_called_verified(self):
        self.report['observation']['direct_open_area_spawn_observed'] = False
        self.refresh_sources()
        with self.assertRaises(AssertionError):
            reload_check.verify(self.report_path)

    def test_mod_assembly_invalidates_loader_only_scene_verification(self):
        (self.work / 'UE4SS.log').write_text('SPAWN_ATTEMPT=1', encoding='utf-8')
        self.refresh_sources()
        with self.assertRaises(AssertionError):
            reload_check.verify(self.report_path)


if __name__ == '__main__':
    unittest.main()
