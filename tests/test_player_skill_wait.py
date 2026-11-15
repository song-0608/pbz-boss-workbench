"""拒绝出招后仍须等待本次真实恢复，不能被已有success=false提前截断。"""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import test_player_skill_batch as batch


class PlayerSkillWaitTests(unittest.TestCase):
    def test_catalog_slot_and_ability_aliases_remain_exact(self):
        rows=[{'slot':'slot1','skill':'skill_01','key':'F1'},
              {'slot':'primary_attack','skill':'skill_01','key':'LEFT_MOUSE_BUTTON'},
              {'slot':'native_combo','skill':'attack_01','key':'R'}]
        self.assertEqual(batch.resolve_binding(rows,'skill_01'),rows[0])
        self.assertEqual(batch.resolve_binding(rows,'primary_attack'),rows[1])
        self.assertEqual(batch.resolve_binding(rows,'attack_01'),rows[2])
        with self.assertRaises(RuntimeError):
            batch.resolve_binding([dict(rows[0],skill='heavy_01')],'slot1')

    def test_rejection_does_not_short_circuit_cleanup_wait(self):
        rejected='[PBZBossControl] skill success=false state=ACTIVE'
        path=Mock();path.read_text.side_effect=[rejected,rejected+'\nRESTORED']
        with patch.object(batch.time,'sleep'):
            value=batch.wait_for(path,0,lambda text:'RESTORED'in text,1)
        self.assertIn('RESTORED',value)
        self.assertEqual(path.read_text.call_count,2)

    def test_activation_wait_can_stop_on_real_rejection(self):
        path=Mock();path.read_text.return_value='[PBZBossControl] skill success=false state=ACTIVE'
        with patch.object(batch.time,'sleep') as sleep:
            batch.wait_for(path,0,lambda text:False,1,True)
        sleep.assert_not_called()

    def test_fault_always_stops_wait(self):
        path=Mock();path.read_text.return_value='state=FAULTED'
        with patch.object(batch.time,'sleep') as sleep:
            batch.wait_for(path,0,lambda text:False,1)
        sleep.assert_not_called()


if __name__=='__main__':unittest.main()
