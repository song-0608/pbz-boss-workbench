"""Native-library publication preserves saved author work and startup helpers."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import creative_boss_library as library
import creative_workspace as cw


class BossLibraryTests(unittest.TestCase):
    def test_publish_is_additive_and_rejects_later_author_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Path(directory)
            cw.initialize(storage, 'ue')
            cw.initialize(storage, 'backend')
            base = cw.paths(storage)['base']
            report = base / 'native.json'
            report.write_text('{}', encoding='utf-8')
            name = 'Content/PBZCreative/BossLibrary20261119/Characters/BP_Boss_AHua.uasset'
            source = cw.paths(storage, 'backend')['workspace'] / name
            source.parent.mkdir(parents=True)
            source.write_bytes(b'checked-native-package')
            native = dict(library='/Game/PBZCreative/BossLibrary20261119',
                          map='/Game/PBZCreative/BossLibrary20261119/L_PBZBossGallery_v3',
                          dependency_packages=['/Game/PBZCreative/BossLibrary20261119/Characters/BP_Boss_AHua'])
            with patch.object(library, 'native', return_value=(base, report, native)):
                first = library.publish(storage)
                self.assertEqual(first['newly_added'], 1)
                self.assertTrue(library.verify(storage)['completed'])
                author_asset = cw.paths(storage)['workspace'] / name
                author_asset.write_bytes(b'author-own-edit')
                self.assertEqual(library.verify(storage)['locally_modified'], [name])
                active_before = cw.paths(storage)['active'].read_bytes()
                with self.assertRaisesRegex(AssertionError, 'existing author asset preserved'):
                    library.publish(storage)
                self.assertEqual(author_asset.read_bytes(), b'author-own-edit')
                self.assertEqual(cw.paths(storage)['active'].read_bytes(), active_before)

    def test_menu_install_preserves_starter_and_customized_menu(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            python = project / 'Content/Python'
            python.mkdir(parents=True)
            init = python / 'init_unreal.py'
            init.write_text('# existing starter\n', encoding='utf-8')
            library.install_menu(project)
            initial = init.read_bytes()
            library.install_menu(project)
            self.assertEqual(init.read_bytes(), initial)
            self.assertTrue(initial.startswith(b'# existing starter\n'))
            menu = python / 'pbz_boss_editor_menu.py'
            menu.write_bytes(b'# user customization\n')
            with self.assertRaisesRegex(AssertionError, 'customized editor menu preserved'):
                library.install_menu(project)
            self.assertEqual(menu.read_bytes(), b'# user customization\n')


if __name__ == '__main__':
    unittest.main()
