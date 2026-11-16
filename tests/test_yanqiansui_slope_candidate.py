from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from mod_installation import ROOT
from build_yanqiansui_slope_candidate import expected, verify
from four_boss_integration_workflow import modules
from yanqiansui_slope_acceptance import verify_current


class SlopeCandidateTests(unittest.TestCase):
    def test_only_initialization_changes_and_unchanged_skill_proofs_are_reparsed(self):
        target = ROOT / 'runtime/release-candidates' / expected()[-1]
        manifest = verify(target)
        current = modules(manifest)
        actions, sources = verify_current(current)
        self.assertEqual(len(actions), 8)
        self.assertIn('tools/yanqiansui_clearance_slope.lua', sources)
        for name in ('yanqiansui_clearance_core.lua', 'owned_arena.lua', 'ue_camera.lua', 'ue_combat.lua', 'runtime.lua'):
            with self.subTest(name=name), self.assertRaises(AssertionError):
                verify_current(dict(current, **{name: '0' * 64}))


if __name__ == '__main__':unittest.main()
