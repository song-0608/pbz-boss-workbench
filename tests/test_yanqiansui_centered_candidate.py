from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from mod_installation import ROOT
from build_yanqiansui_centered_candidate import expected, verify, patched, PATCHES
from four_boss_integration_workflow import modules
from yanqiansui_centered_acceptance import verify_current


class CenteredCandidateTests(unittest.TestCase):
    def test_only_floor_reference_changes_and_original_is_reconstructible(self):
        original = (ROOT / 'tools/yanqiansui_clearance_dense.lua').read_bytes()
        source = patched(original).decode('utf-8')
        for before, after in reversed(PATCHES):
            self.assertEqual(source.count(after), 1)
            source = source.replace(after, before)
        self.assertEqual(source.encode(), original)

    def test_exact_candidate_reuses_only_unchanged_skills(self):
        target = ROOT / 'runtime/release-candidates' / expected()[-1]
        current = modules(verify(target))
        actions, sources = verify_current(current)
        self.assertEqual(len(actions), 8)
        self.assertIn('tools/build_yanqiansui_centered_candidate.py', sources)
        for name in ('yanqiansui_clearance_core.lua', 'owned_arena.lua', 'ue_camera.lua', 'ue_combat.lua', 'runtime.lua'):
            with self.subTest(name=name), self.assertRaises(AssertionError):
                verify_current(dict(current, **{name: '0' * 64}))


if __name__ == '__main__':
    unittest.main()
