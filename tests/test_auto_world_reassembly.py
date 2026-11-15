"""自动重装配证据必须拒绝缺失回读、手动重arm和同一World。"""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from collect_auto_world_reassembly import proof


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.text=(ROOT/'tests/fixtures/auto-world-success.log').read_text(encoding='utf-8')

    def test_complete_original_sequence(self):
        self.assertTrue(proof(self.text)['passed'])

    def test_missing_restoration_or_title_wait(self):
        for token in ('CAMERA_CLEANUP_ENGINE_VERIFIED=true','ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0',
                      'WORLD_REASSEMBLY_AWAITING_GAMEPLAY=true','IDLE_WORLD_OBJECTS_RETIRED='):
            with self.subTest(token=token):
                self.assertFalse(proof(self.text.replace(token,'REMOVED='))['passed'])

    def test_manual_retire_or_additional_assembly(self):
        for extra in ('PBZ_REARM_RETIRE:PASS=true','PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=ahua'):
            self.assertFalse(proof(self.text+extra)['passed'])

    def test_no_damage_or_no_new_world(self):
        self.assertFalse(proof(self.text.replace('health_after=8750.0','health_after=9000.0'))['passed'])
        self.assertFalse(proof(self.text.replace('|85075713344','|20761920992'))['passed'])


if __name__=='__main__':unittest.main()
