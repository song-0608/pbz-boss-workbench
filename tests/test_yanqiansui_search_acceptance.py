from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from mod_installation import ROOT,validate_package
from build_yanqiansui_search_candidate import expected,verify,MODULE,BASE
from yanqiansui_search_acceptance import verify_current
from four_boss_integration_workflow import modules


class SearchAcceptanceTests(unittest.TestCase):
    def current(self):
        _,_,_,_,identifier=expected()
        return modules(verify(ROOT/'runtime/release-candidates'/identifier))

    def test_only_navigation_module_changes(self):
        current=self.current()
        old=modules(validate_package(ROOT/'runtime/release-candidates'/BASE))
        self.assertEqual({n for n,d in current.items()if d!=old[n]},
                         {MODULE.removeprefix('PBZBossControl/Scripts/')})
        actions,sources=verify_current(current)
        self.assertEqual(len(actions),8)
        self.assertIn('tools/yanqiansui_search_acceptance.py',sources)
        self.assertIn('tools/yanqiansui_clearance_search.lua',sources)

    def test_shared_execution_and_catalog_mutations_refused(self):
        for name in('runtime.lua','boss_catalog.lua','ue_combat.lua','owned_arena.lua',
                    'profiles/yanqiansui.lua','yanqiansui_arena_clearance.lua'):
            with self.subTest(name=name):
                current=self.current();current[name]='0'*64
                with self.assertRaises(AssertionError):verify_current(current)


if __name__=='__main__':unittest.main()
