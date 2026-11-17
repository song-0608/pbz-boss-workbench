import ast
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import boss_workbench_v4_window as window


class V4WindowTests(unittest.TestCase):
    def test_render_explains_new_count_and_generic_native_skills(self):
        source=window.render();ast.parse(source)
        self.assertIn('四角色 · 52项能力',source)
        self.assertIn("selected!='ahua_guitoudao'",source)
        self.assertIn('72-四Boss技能扩展v4操作说明.md',source)
        self.assertIn("'tools/research_scene_checkpoint.py' if action=='prepare'",source)

    def test_development_build_is_not_offered_as_release(self):
        data=dict(status='development',complete_mod=False,runtime_acceptance_current=False)
        with patch.object(window,'installed_package',return_value=({'enabled':True},data,None)):
            with self.assertRaises(AssertionError):window.check_installed()


if __name__=='__main__':unittest.main()
