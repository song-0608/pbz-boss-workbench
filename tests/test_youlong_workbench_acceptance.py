from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from mod_installation import ROOT,validate_package
from build_youlong_workbench_candidate import expected,verify,BASE
from four_boss_integration_workflow import modules
from youlong_workbench_acceptance import verify_current


class ThreeProfileTests(unittest.TestCase):
    def current(self):
        _,_,_,_,identifier=expected()
        return modules(verify(ROOT/'runtime/release-candidates'/identifier))

    def test_only_locked_registry_and_preview_change(self):
        actions,sources=verify_current(self.current())
        self.assertEqual(len(actions),8)
        self.assertIn('tools/test_youlong_workbench_world.py',sources)
        self.assertTrue(all(p['boss']=='056_youlong'for p in actions))

    def test_execution_and_ability_changes_refused(self):
        for name in('runtime.lua','owned_arena.lua','boss_catalog.lua','workbench_catalog.lua',
                    'profiles/youlong.lua','ue_combat.lua','yanqiansui_arena_clearance.lua'):
            with self.subTest(name=name):
                current=self.current();current[name]='0'*64
                with self.assertRaises(AssertionError):verify_current(current)

    def test_versioned_driver_preserves_readiness_and_deadline_gates(self):
        original=(ROOT/'tools/test_four_boss_world_missing.py').read_text(encoding='utf-8')
        original=original.replace('from four_boss_ordinary_reuse import verify',
            'from youlong_workbench_acceptance import verify_current as verify')
        original=original.replace('range(3)','range(2)').replace(
            'Fresh YouLong original-menu World lifecycle only; do not repeat accepted ordinary skills.',
            'Three-profile exact registry: YouLong World cycle, retaining the frozen readiness gates.')
        self.assertEqual((ROOT/'tools/test_youlong_workbench_world.py').read_text(encoding='utf-8'),original)


if __name__=='__main__':unittest.main()
