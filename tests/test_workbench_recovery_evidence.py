import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from collect_workbench_recovery import proof


class RecoveryEvidenceTests(unittest.TestCase):
    enter='[PBZBossControl] enter success=true state=ACTIVE reason=\n'
    clear='PBZ_COMBAT_TARGET:CLEAR_VERIFIED=true|fallback=true\n'
    restore=('[PBZBossControl] exit success=true state=OFF reason=\n'
        'ORIGINAL_PLAYER_POSITION_DELTA=0.0\nORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0\n'
        'CAMERA_CLEANUP_ENGINE_VERIFIED=true\n')

    def hud(self,health=0):
        return 'PBZ_PLAYER_UI:STATUS='+json.dumps({'text':
            '新娘阿花 | ACTIVE\n目标：新娘阿花（已死亡） | 生命 '+str(health)})+'\n'

    def test_dead_stale_target_with_full_same_cycle_restoration_passes(self):
        self.assertTrue(proof(self.enter+self.hud()+self.clear+self.restore)['passed'])

    def test_native_success_requires_actual_empty_component_readback_too(self):
        text=self.enter+self.hud()+self.clear.replace('fallback=true','fallback=false')+self.restore
        result=proof(text)
        self.assertTrue(result['passed'])
        self.assertFalse(result['dead_target_clear_restorations'][0]['fallback_used'])
        self.assertFalse(proof(text.replace('CLEAR_VERIFIED=true','CLEAR_VERIFIED=false'))['passed'])
        self.assertFalse(proof(text.replace(self.clear.replace('fallback=true','fallback=false'),
            'PBZ_COMBAT_TARGET:STALE_LOCK_CLEARED=true\n'))['passed'])
        self.assertTrue(proof(self.enter+self.clear+self.hud()+self.clear+self.restore)['passed'])

    def test_missing_native_fallback_dead_status_or_readback_fails(self):
        text=self.enter+self.hud()+self.clear+self.restore
        for missing in (self.clear,self.hud(),'CAMERA_CLEANUP_ENGINE_VERIFIED=true',
                        'ORIGINAL_PLAYER_POSITION_DELTA=0.0'):
            with self.subTest(missing=missing):self.assertFalse(proof(text.replace(missing,''))['passed'])

    def test_live_target_and_later_control_cycle_cannot_supply_proof(self):
        self.assertFalse(proof(self.enter+self.hud(9000)+self.clear+self.restore)['passed'])
        self.assertFalse(proof(self.enter+self.hud()+self.enter+self.clear+self.restore)['passed'])
        self.assertFalse(proof(self.enter+self.hud()+self.hud(9000)+self.clear+self.restore)['passed'])

    def test_fault_and_player_drift_remain_failures(self):
        text=self.enter+self.hud()+self.clear+self.restore
        self.assertFalse(proof(text+'state=FAULTED')['passed'])
        self.assertFalse(proof(text.replace('DELTA=0.0','DELTA=25'))['passed'])

    def test_observed_dead_then_rejected_cycle_to_empty_lock_passes(self):
        empty='PBZ_PLAYER_UI:STATUS='+json.dumps({'text':'新娘阿花 | ACTIVE\n目标：无有效锁定\n'})+'\n'
        rejected='[PBZBossControl] target_request success=false state=ACTIVE reason=no visible living hostile target within radius\n'
        text=self.enter+self.hud()+rejected+empty+self.clear+self.restore
        self.assertTrue(proof(text)['passed'])
        for altered in (text.replace(rejected,''),text.replace(self.hud(),''),
                        text.replace(empty,self.hud(9000)),text.replace(empty,'KEY_SKILL_BEGIN=skill_01|\n'+empty)):
            with self.subTest(altered=altered):self.assertFalse(proof(altered)['passed'])


if __name__=='__main__':unittest.main()
