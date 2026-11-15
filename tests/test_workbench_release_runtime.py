from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from release_boss_workbench import validate_common_runtime


class RuntimeGateTests(unittest.TestCase):
    def fixture(self):
        base={'ue_combat.lua':'old','control_bridge.lua':'same','remote_control.lua':'same'}
        current=dict(base,**{'profiles/wanjun.lua':'profile','profiles/wanjun_bindings.lua':'keys'})
        return base,current

    def test_unchanged_adapters_keep_independent_base(self):
        base,current=self.fixture();validate_common_runtime(current,base)

    def test_new_complete_exact_source_baseline_accepts_initialization_modules(self):
        base,current=self.fixture();current.update({'owned_arena.lua':'new','owned_readiness.lua':'new','owned_initialization.lua':'new'})
        validate_common_runtime(current,dict(current))
        other=dict(current,**{'owned_arena.lua':'another'})
        with self.assertRaises(AssertionError):validate_common_runtime(current,other)

    def test_changed_target_adapter_requires_exact_source_recovery(self):
        base,current=self.fixture();current['ue_combat.lua']='new'
        recovery={'passed':True,'module_source_sha256':dict(current),
            'dead_target_clear_restorations':[{'restoration':{'passed':True}}],
            'requires_real_dead_target_status':True,'requires_native_clear_readback_and_full_restoration':True}
        validate_common_runtime(current,base,recovery)
        for bad in (None,dict(recovery,passed=False),dict(recovery,module_source_sha256=base),
                    dict(recovery,dead_target_clear_restorations=[])):
            with self.subTest(bad=bad),self.assertRaises(AssertionError):
                validate_common_runtime(current,base,bad)

    def test_unrelated_runtime_edits_are_not_waived(self):
        base,current=self.fixture();current['remote_control.lua']='changed'
        with self.assertRaisesRegex(AssertionError,'independent Boss adapter changed'):
            validate_common_runtime(current,base)

    def test_unexpected_added_or_missing_module_is_rejected(self):
        base,current=self.fixture();current['extra.lua']='unexpected'
        with self.assertRaises(AssertionError):validate_common_runtime(current,base)
        del current['extra.lua'];del current['control_bridge.lua']
        with self.assertRaises(AssertionError):validate_common_runtime(current,base)


if __name__=='__main__':unittest.main()
