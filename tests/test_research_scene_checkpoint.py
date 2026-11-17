import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import research_scene_checkpoint as checkpoint


class ResearchCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / 'checkpoints'
        self.source = self.store / 'saved-scene'
        self.box = self.root / 'research-box'
        self.target = self.box / 'Saved'
        self.work = self.root / 'session'
        for path, data in ((self.source, b'open-arena'), (self.target, b'old-research')):
            (path / 'SaveGames').mkdir(parents=True)
            (path / 'SaveGames/main.sav').write_bytes(data)
        self.record = dict(schema=1, label=checkpoint.LABEL, directory=str(self.source),
                           files=checkpoint.save_snapshot(self.source))
        self.write(self.source / 'checkpoint.json', self.record)
        self.write(self.store / '当前研究场景.json', self.record)
        self.owner = dict(phase='prepared')
        self.state = dict(formal_before={'formal': 'unchanged'}, work=str(self.work))
        mocks = (
            patch.object(checkpoint, 'storage', return_value=self.store),
            patch.object(checkpoint.practice, 'owned_session', return_value=(self.owner, self.state)),
            patch.object(checkpoint.v.c.preflight, 'games_running', return_value=[]),
            patch.object(checkpoint.v.c.baseline, 'formal_files', return_value=self.state['formal_before']),
            patch.object(checkpoint.v.c.isolation, 'select_box'),
            patch.object(checkpoint.v.c.isolation, 'api'),
            patch.object(checkpoint.v.c.isolation, 'check_policy'),
            patch.object(checkpoint.v.c.isolation, 'get_root', return_value=self.box),
            patch.object(checkpoint.v.c.isolation, 'virtual_file', return_value=self.target),
        )
        for mock in mocks:
            mock.start()
            self.addCleanup(mock.stop)

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def test_apply_restores_arena_and_keeps_previous_research_backup(self):
        checkpoint.apply()
        self.assertEqual((self.target / 'SaveGames/main.sav').read_bytes(), b'open-arena')
        self.assertEqual((self.work / 'before-research-checkpoint/SaveGames/main.sav').read_bytes(),
                         b'old-research')
        receipt = json.loads((self.work / 'research-checkpoint-applied.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['checkpoint'], self.record)
        self.assertFalse(receipt['formal_files_modified'])

    def test_changed_snapshot_is_rejected_before_writing(self):
        (self.source / 'SaveGames/main.sav').write_bytes(b'changed')
        with self.assertRaises(AssertionError):
            checkpoint.apply()
        self.assertEqual((self.target / 'SaveGames/main.sav').read_bytes(), b'old-research')
        self.assertFalse(self.work.exists())

    def test_running_game_cannot_receive_checkpoint(self):
        with patch.object(checkpoint.v.c.preflight, 'games_running', return_value=[123]):
            with self.assertRaises(AssertionError):
                checkpoint.apply()
        self.assertEqual((self.target / 'SaveGames/main.sav').read_bytes(), b'old-research')

    def test_destination_outside_research_box_is_rejected(self):
        with patch.object(checkpoint.v.c.isolation, 'virtual_file', return_value=self.source):
            with self.assertRaises(AssertionError):
                checkpoint.apply()
        self.assertFalse(self.work.exists())


if __name__ == '__main__':
    unittest.main()
