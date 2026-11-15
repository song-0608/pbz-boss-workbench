import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from candidate_effect_scope import local_effect


class LocalEffectTests(unittest.TestCase):
    def test_safe_damage_and_movement_preserved(self):
        result = {'natural_completion': {'distance': 235.7, 'damage_observed': True},
            'active_cancel_and_restoration': True}
        proof = local_effect(result, 'CONTROLLED_BOSS_POSITION_DELTA=235.7\n')
        self.assertTrue(proof['local_displacement_verified'])
        self.assertTrue(proof['natural_completion']['damage_observed'])
        self.assertEqual(result['natural_completion']['distance'], 235.7)

    def test_observed_scene_teleport_is_rejected(self):
        proof = local_effect({'natural_completion': {'distance': 162716.2147793},
            'active_cancel_and_restoration': True}, 'CONTROLLED_BOSS_POSITION_DELTA=162716.45569321')
        self.assertFalse(proof['local_displacement_verified'])
        self.assertIsNone(proof['natural_completion'])
        self.assertFalse(proof['active_cancel_and_restoration'])

    def test_missing_nonfinite_negative_and_late_excess_rejected(self):
        for text in ('', 'CONTROLLED_BOSS_POSITION_DELTA=nan', 'CONTROLLED_BOSS_POSITION_DELTA=-1',
                'CONTROLLED_BOSS_POSITION_DELTA=1\nCONTROLLED_BOSS_POSITION_DELTA=3001'):
            with self.subTest(text=text):
                proof = local_effect({'natural_completion': None, 'active_cancel_and_restoration': True}, text)
                self.assertFalse(proof['local_displacement_verified'])
                self.assertFalse(proof['active_cancel_and_restoration'])

    def test_cancel_requires_post_restoration_position_and_fixed_bound(self):
        proof = local_effect({'natural_completion': None, 'active_cancel_and_restoration': True},
            'CONTROLLED_BOSS_POSITION_DELTA=100')
        self.assertTrue(proof['active_cancel_and_restoration'])
        with self.assertRaises(AssertionError):
            local_effect({}, '', 200000)


if __name__ == '__main__':
    unittest.main()
