from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from four_boss_ordinary_reuse import verify,ROOT
from four_boss_integration_workflow import CANDIDATE,modules
from mod_installation import validate_package
import native_menu_input


class MissingOnlyTests(unittest.TestCase):
    def test_eight_real_ordinary_actions_reparse(self):
        current=modules(validate_package(ROOT/'runtime/release-candidates'/CANDIDATE))
        rows,sources=verify(current);self.assertEqual(len(rows),8);self.assertEqual(len(sources),1)
        changed=dict(current);changed['runtime.lua']='0'*64
        with self.assertRaises(AssertionError):verify(changed)

    def test_bounded_menu_variant_keeps_frozen_gate(self):
        module=native_menu_input.variant()
        self.assertEqual(module.v.ROOT,ROOT);self.assertTrue(callable(module.validate_control_menu_transition))
        with self.assertRaises(AssertionError):native_menu_input.click('control_attack')


if __name__=='__main__':unittest.main()
