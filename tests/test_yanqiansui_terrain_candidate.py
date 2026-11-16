from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from mod_installation import ROOT
from build_yanqiansui_terrain_candidate import expected, verify
from four_boss_integration_workflow import modules
from yanqiansui_terrain_acceptance import verify_current


class TerrainCandidateTests(unittest.TestCase):
    def current(self):
        return modules(verify(ROOT / 'runtime/release-candidates' / expected()[-1]))

    def test_exact_trace_reuses_only_unchanged_ordinary_skills(self):
        actions, sources = verify_current(self.current())
        self.assertEqual(len(actions), 8)
        self.assertIn('tools/yanqiansui_terrain_trace.lua', sources)

    def test_decision_or_execution_changes_are_refused(self):
        for name in ('yanqiansui_clearance_core.lua', 'yanqiansui_arena_clearance.lua', 'owned_arena.lua',
                     'ue_combat.lua', 'boss_workbench.lua', 'profiles/yanqiansui.lua'):
            current = self.current()
            current[name] = '0' * 64
            with self.subTest(name=name), self.assertRaises(AssertionError):
                verify_current(current)


if __name__ == '__main__':
    unittest.main()
