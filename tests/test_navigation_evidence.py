"""落点初始化失败、无实际效果或串用下一次恢复的区间不能计作导航成功。"""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from collect_navigation_layouts import layout_proof

SUCCESS=('NAVIGATION_LAYOUT_VERIFIED=boss=1,2,3|targets=2\nNAVIGATION_TARGET_VISIBILITY_VERIFIED=2\n'
    'INTERACTIVE_READY=ready\n[PBZBossControl] enter success=true state=ACTIVE\n'
    'KEY_SKILL_END=skill|peak=1|active=0|natural=true|health_before=9000|health_after=8900|distance=0\n'
    '[PBZBossControl] exit success=true state=OFF reason=manual exit\n'
    'ORIGINAL_PLAYER_POSITION_DELTA=0\nORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0\nCAMERA_CLEANUP_ENGINE_VERIFIED=true\n')


class NavigationEvidenceTests(unittest.TestCase):
    def test_complete_cycle(self):self.assertTrue(layout_proof(SUCCESS)['passed'])

    def test_failed_candidate_and_missing_visibility(self):
        for text in (SUCCESS+'NAVIGATION_LAYOUT_REJECTED=1:1\n',SUCCESS+'PREREQUISITE_NOT_READY=x\n',
                     SUCCESS.replace('NAVIGATION_TARGET_VISIBILITY_VERIFIED=2','removed')):
            self.assertFalse(layout_proof(text)['passed'])

    def test_no_effect_is_not_a_gameplay_validation(self):
        self.assertFalse(layout_proof(SUCCESS.replace('health_after=8900','health_after=9000'))['passed'])

    def test_restoration_from_next_enter_cannot_complete_previous_cast(self):
        text=SUCCESS.replace('[PBZBossControl] exit success=true',
            '[PBZBossControl] enter success=true state=ACTIVE\n[PBZBossControl] exit success=true')
        self.assertFalse(layout_proof(text)['passed'])


if __name__=='__main__':unittest.main()
