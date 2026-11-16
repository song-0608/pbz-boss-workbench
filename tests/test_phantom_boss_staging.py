from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import stage_phantom_boss_pair as stage


class StagingTests(unittest.TestCase):
    def fixture(self,root):
        source=Path(root)/'current-research'
        (source/'SaveGames').mkdir(parents=True)
        (source/'SaveGames/slot.sav').write_bytes(b'current research progress')
        (source/'PBZLocalSetting.sav').write_bytes(b'current settings')
        (source/'shader.cache').write_bytes(b'ignored cache')
        return source

    def test_four_copies_are_independent_and_source_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=self.fixture(tmp);snapshot=stage.save_snapshot(source)
            for name in ('host/game','host/local','guest/game','guest/local'):
                stage.copy_snapshot(source,Path(tmp)/name,snapshot)
            (Path(tmp)/'host/game/SaveGames/slot.sav').write_bytes(b'host changes')
            self.assertEqual(stage.save_snapshot(source),snapshot)
            for name in ('host/local','guest/game','guest/local'):
                self.assertEqual(stage.save_snapshot(Path(tmp)/name),snapshot)

    def test_existing_save_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=self.fixture(tmp);snapshot=stage.save_snapshot(source)
            target=Path(tmp)/'existing';target.mkdir()
            protected=target/'slot.sav';protected.write_bytes(b'preserve')
            with self.assertRaises(FileExistsError):stage.copy_snapshot(source,target,snapshot)
            self.assertEqual(protected.read_bytes(),b'preserve')

    def test_changed_source_is_rejected_before_creating_a_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=self.fixture(tmp);snapshot=stage.save_snapshot(source)
            (source/'SaveGames/slot.sav').write_bytes(b'changed progress')
            target=Path(tmp)/'target'
            with self.assertRaisesRegex(AssertionError,'changed before'):stage.copy_snapshot(source,target,snapshot)
            self.assertFalse(target.exists())

    def test_loader_uses_object_cache_and_preserves_recovery_from_hot_reload(self):
        source=(stage.ROOT.parent/'upstream/RE-UE4SS/assets/UE4SS-settings.ini').read_text(encoding='utf-8-sig')
        data=stage.loader_settings(source).decode()
        for line in ('bUseUObjectArrayCache = true','bForceGUObjectArrayForIteration = true',
                     'EnableHotReloadSystem = 0','HookLoadMap = 1','HookEngineTick = 1'):
            self.assertIn(line,data)
        with self.assertRaisesRegex(AssertionError,'Missing/ambiguous'):
            stage.loader_settings(source+'\nHookEngineTick = 0\n')

    def test_empty_or_unexpected_save_layout_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(AssertionError,'progress'):stage.save_snapshot(tmp)
            source=self.fixture(tmp);(source/'Elsewhere').mkdir()
            (source/'Elsewhere/foreign.sav').write_bytes(b'not expected')
            with self.assertRaisesRegex(AssertionError,'Unexpected'):stage.save_snapshot(source)


if __name__=='__main__':unittest.main()
