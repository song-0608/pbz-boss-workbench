import ast
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import boss_workbench_v3_window as window


class WindowTests(unittest.TestCase):
    def test_four_role_ui_preserves_protected_entry(self):
        source = window.render()
        ast.parse(source)
        self.assertIn('四角色离线操控', source)
        self.assertIn('阿花 · 万钧 · 烟千岁 · 游龙', source)
        self.assertIn("str(ROOT / 'tools/ahua_practice.py')", source)
        self.assertIn("command.append('--cloud-off-reviewed')", source)
        self.assertNotIn('烟千岁仍锁定预览', source)

    def test_candidate_and_three_role_installs_are_rejected(self):
        manifest = {'status': 'release', 'complete_mod': True, 'runtime_acceptance_current': True,
                    'release_id': 'ahua-boss-workbench-v3-test', 'bosses': [{'id': n} for n in window.IDS], 'locked_previews': []}
        with patch.object(window, 'installed_package', return_value=({'enabled': True}, manifest, None)):
            self.assertEqual(window.check_installed(), manifest)
            for key, value in (('status', 'acceptance-candidate'), ('complete_mod', False), ('runtime_acceptance_current', False),
                               ('release_id', 'ahua-boss-workbench-v2-test'), ('locked_previews', ['073_yanqiansui'])):
                with self.subTest(key=key):
                    old = manifest[key];manifest[key] = value
                    with self.assertRaises(AssertionError):window.check_installed()
                    manifest[key] = old


if __name__ == '__main__':unittest.main()
