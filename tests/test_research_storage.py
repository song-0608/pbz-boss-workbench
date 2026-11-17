import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from research_storage import container_path,PROJECT_STORAGE


class ResearchStorageTests(unittest.TestCase):
    def fixture(self,data=None):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        if data is not None:
            (root/'runtime').mkdir();(root/'runtime/research-storage.json').write_text(
                json.dumps(data,ensure_ascii=False),encoding='utf-8')
        return root

    def mapping(self):
        return dict(schema=1,project_storage=str(PROJECT_STORAGE),
            containers={'PBZSteamLab':str(PROJECT_STORAGE/'研究运行环境/PBZSteamLab')})

    def test_no_migration_preserves_original_container(self):
        root=self.fixture();self.assertEqual(container_path(root=root),root/'sandbox/PBZSteamLab')

    def test_only_migrated_box_moves(self):
        root=self.fixture(self.mapping())
        self.assertEqual(container_path(root=root),PROJECT_STORAGE/'研究运行环境/PBZSteamLab')
        self.assertEqual(container_path('PBZBossLab',root=root),root/'sandbox/PBZBossLab')

    def test_invalid_or_escaped_mapping_is_not_silently_used(self):
        for change in (lambda d:d.update(schema=2),lambda d:d.update(project_storage='C:\\'),
                       lambda d:d['containers'].update(PBZSteamLab='E:\\Other'),
                       lambda d:d['containers'].update(Other='E:\\Other')):
            data=self.mapping();change(data)
            with self.subTest(data=data):
                with self.assertRaises(ValueError):container_path(root=self.fixture(data))

    def test_unknown_box_cannot_select_arbitrary_files(self):
        with self.assertRaises(ValueError):container_path('../Other',root=self.fixture())


if __name__=='__main__':unittest.main()
