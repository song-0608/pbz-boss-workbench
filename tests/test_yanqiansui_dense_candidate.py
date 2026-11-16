from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from mod_installation import ROOT
from build_yanqiansui_dense_candidate import expected,verify
from four_boss_integration_workflow import modules
from yanqiansui_dense_acceptance import verify_current


class DenseCandidateTests(unittest.TestCase):
    def current(self):
        return modules(verify(ROOT/'runtime/release-candidates'/expected()[-1]))

    def test_exact_initialization_change_retains_eight_skill_proofs(self):
        actions,sources=verify_current(self.current())
        self.assertEqual(len(actions),8)
        self.assertIn('tools/yanqiansui_clearance_dense.lua',sources)

    def test_unknown_core_or_execution_change_is_rejected(self):
        for name in ('yanqiansui_clearance_core.lua','owned_arena.lua','ue_camera.lua',
                     'runtime.lua','ue_combat.lua','profiles/yanqiansui.lua'):
            current=self.current();current[name]='0'*64
            with self.subTest(name=name),self.assertRaises(AssertionError):verify_current(current)


if __name__=='__main__':unittest.main()
