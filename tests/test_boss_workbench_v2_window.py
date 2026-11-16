import ast
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import boss_workbench_v2_window as window


class LauncherTests(unittest.TestCase):
    def test_only_accepted_startup_roles(self):
        for boss in ('ahua_guitoudao', '057_wanjun'):
            self.assertEqual(window.startup_settings({'boss_id': boss}), ({'boss_id': boss}, False))
        for boss in ('073_yanqiansui', '056_youlong'):
            self.assertEqual(window.startup_settings({'boss_id': boss}), ({'boss_id': 'ahua_guitoudao'}, True))
        for data in ({'boss_id': 'unknown'}, {}, {'boss_id': 'ahua_guitoudao', 'extra': True}):
            with self.assertRaises(ValueError):
                window.startup_settings(data)

    def test_versioned_window_preserves_research_entry(self):
        source = window.render()
        ast.parse(source)
        self.assertIn("str(ROOT / 'tools/ahua_practice.py')", source)
        self.assertIn("command.append('--cloud-off-reviewed')", source)
        self.assertIn('烟千岁仍锁定预览', source)
        self.assertIn('67-三Boss工作台v2交付说明.md', source)


if __name__ == '__main__':
    unittest.main()
