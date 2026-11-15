"""用已收尾真实日志重放载图前证据，明确拒绝缺失恢复、错World与错误顺序。"""
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from collect_map_travel_guard import proof


class TravelEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        work=ROOT/'evidence/official-validation/20261114-154159'
        witness=json.loads(next(work.glob('active-world-actions-*.json')).read_text(encoding='utf-8'))
        text=(work/'UE4SS.log').read_text(encoding='utf-8',errors='replace')
        cls.text=text[witness['log_offset']:witness['log_end']]

    def test_real_preload_only_not_full_travel(self):
        result=proof(self.text)
        self.assertTrue(result['passed']);self.assertFalse(result['full_travel_lifecycle_verified'])

    def test_missing_camera_or_position_is_not_restoration(self):
        for token in ('CAMERA_CLEANUP_ENGINE_VERIFIED=true','ORIGINAL_PLAYER_POSITION_DELTA=0.0',
                      'ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0','MAP_TRAVEL_RESTORED_BEFORE_LOAD=true'):
            with self.subTest(token=token):self.assertFalse(proof(self.text.replace(token,'removed='))['passed'])

    def test_wrong_world_or_late_preload_marker_rejected(self):
        self.assertFalse(proof(self.text.replace('MAP_TRAVEL_PRE_ACTIVE=World','MAP_TRAVEL_PRE_ACTIVE=OtherWorld'))['passed'])
        self.assertFalse(proof('MAP_TRAVEL_RESTORED_BEFORE_LOAD=true\n'+self.text)['passed'])

    def test_failure_before_load_rejected_but_postload_failure_preserved(self):
        self.assertFalse(proof('state=FAULTED\n'+self.text)['passed'])
        self.assertTrue(proof(self.text+'\nstate=FAULTED')['passed'])


if __name__=='__main__':unittest.main()
