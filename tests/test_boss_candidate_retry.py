import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import boss_candidate_retry as retry


class RetryTests(unittest.TestCase):
    def fixture(self):
        proof = {'natural_completion': {'distance': 200, 'damage_observed': True, 'movement_observed': True},
            'active_cancel_and_restoration': False, 'activation_instance_verified': True,
            'ability_class_short': 'Ability_C', 'restoration': {'passed': True}}
        raw = 'observed action\nCONTROLLED_BOSS_POSITION_DELTA=200\n'
        action = {'interrupt': False, 'passed': True, 'state_file': 'state', 'log_offset': 0,
            'log_end': len(raw), 'lines': raw.splitlines(), 'skill': 'skill_01'}
        report = {'skills': {'skill_01': {'class_path': '/Fixture.Ability_C'}}}
        return report, raw, [action], proof

    def test_reuse_is_exact_and_reanalyzed(self):
        report, raw, actions, proof = self.fixture()
        with patch.object(retry, 'analyze', return_value=proof) as analyze:
            result = retry.verify_actions(report, raw, actions, 'state')
        analyze.assert_called_once_with(raw, 'skill_01')
        self.assertEqual(result['skill_01']['exact_granted_class'], '/Fixture.Ability_C')

    def test_wrong_state_raw_class_duplicate_or_unsafe_effect_rejected(self):
        for mode in ('state', 'raw', 'class', 'duplicate', 'unsafe', 'no_restore', 'not_natural'):
            report, raw, actions, proof = self.fixture()
            if mode == 'state': actions[0]['state_file'] = 'other'
            elif mode == 'raw': actions[0]['lines'] = ['foreign']
            elif mode == 'class': proof['ability_class_short'] = 'Foreign_C'
            elif mode == 'duplicate': actions.append(copy.deepcopy(actions[0]))
            elif mode == 'unsafe': proof['natural_completion']['distance'] = 162716
            elif mode == 'no_restore': proof['restoration']['passed'] = False
            else: proof['natural_completion'] = None
            with self.subTest(mode=mode), patch.object(retry, 'analyze', return_value=proof), self.assertRaises(AssertionError):
                retry.verify_actions(report, raw, actions, 'state')

    def test_failed_or_cancel_actions_never_reused_as_natural(self):
        for field in ('passed', 'interrupt'):
            report, raw, actions, proof = self.fixture()
            actions[0][field] = field == 'interrupt'
            with self.assertRaises(AssertionError):
                retry.verify_actions(report, raw, actions, 'state')


if __name__ == '__main__':
    unittest.main()
