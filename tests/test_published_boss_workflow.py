import ast
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import published_boss_workflow as published
import boss_workbench_v5_window as window


class PublishedWorkflowTests(unittest.TestCase):
    def test_launcher_routes_only_to_published_player_tools(self):
        flow = ROOT / 'runtime/player-workflows/v5-test'
        source = window.render(flow, 7)
        ast.parse(source)
        self.assertIn(repr(str(flow)), source)
        self.assertIn("else PLAYER_FLOW / 'ahua_practice.py'", source)
        self.assertIn("'tools/research_scene_checkpoint.py'", source)
        self.assertIn("command = [sys.executable, '-B', '-X', 'utf8',", source)
        self.assertIn('7角色', source)

    def test_published_carrier_uses_installed_package_verifier(self):
        release = ROOT / 'releases/ahua-boss-workbench-v5-test'
        files = published.render(release, {'expansion_profiles': []})
        self.assertEqual(set(files), {'ahua_practice.py', 'run_control_lifecycle_probe.py', 'player_settings.py', 'player_keymap.py'})
        for name, data in files.items(): ast.parse(data.decode('utf-8'), filename=name)
        self.assertIn('from published_boss_workflow import installed_mod_root as candidate_mod_root',
                      files['run_control_lifecycle_probe.py'].decode())
        self.assertIn('lock_target', files['player_keymap.py'].decode())


if __name__ == '__main__': unittest.main()
