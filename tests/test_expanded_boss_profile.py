import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import build_expanded_boss_profile as profile


class ExpandedBossProfileTests(unittest.TestCase):
    def fixture(self):
        path = '/PBZCombatAsset/ActorData/Mobs/071_XianZhe/Ability/GA_XianZhe_Skill_05.GA_XianZhe_Skill_05_C'
        definition = dict(id='071_xianzhe', display_name='弦儿', ability_pool=[path])
        action = dict(class_path=path, natural_completion_verified=True,
                      cancellation_runtime_verified=True, gameplay_verified=True, movement_runtime_verified=False)
        report = dict(id=definition['id'], target_build_sha256=profile.BUILD,
            base_control_accepted=True, playable=False, metadata_identity=copy.deepcopy(definition),
            stability={'passed': True}, cleanup={k: True for k in
                ('boss', 'boss_controller', 'target', 'target_controller', 'extra_target', 'extra_target_controller')},
            movement_camera={k: True for k in ('movement_verified', 'camera_rotation_verified', 'milestone_passed')},
            skills={'skill_01': copy.deepcopy(action)}, accepted_skills={'skill_01': copy.deepcopy(action)})
        return report, definition

    def test_accepts_only_collected_native_actions(self):
        report, definition = self.fixture()
        self.assertEqual(list(profile.validate_report(report, definition)), ['skill_01'])
        self.assertEqual(profile.label(report['skills']['skill_01']['class_path']), '技能05')

    def test_rejects_unproven_and_foreign_actions(self):
        for failure in ('natural', 'cancel', 'effect', 'foreign', 'mismatch', 'duplicate', 'unknown_slot'):
            report, definition = self.fixture()
            accepted = report['accepted_skills']
            if failure == 'natural': accepted['skill_01']['natural_completion_verified'] = False
            elif failure == 'cancel': accepted['skill_01']['cancellation_runtime_verified'] = False
            elif failure == 'effect': accepted['skill_01']['gameplay_verified'] = False
            elif failure == 'foreign':
                accepted['skill_01']['class_path'] = '/Foreign.Ability_C'
                report['skills'] = copy.deepcopy(accepted)
            elif failure == 'mismatch': report['skills']['skill_01']['movement_runtime_verified'] = True
            else:
                key = 'heavy_01' if failure == 'duplicate' else 'unreviewed'
                accepted[key] = copy.deepcopy(accepted['skill_01'])
                report['skills'][key] = copy.deepcopy(accepted[key])
            with self.subTest(failure=failure), self.assertRaises(AssertionError):
                profile.validate_report(report, definition)

    def test_requires_closed_control_scope(self):
        for section, field in (('stability', 'passed'), ('cleanup', 'target'),
                               ('movement_camera', 'camera_rotation_verified')):
            report, definition = self.fixture(); report[section][field] = False
            with self.subTest(section=section), self.assertRaises(AssertionError):
                profile.validate_report(report, definition)
        report, definition = self.fixture(); report['metadata_identity']['display_name'] = '其他角色'
        with self.assertRaises(AssertionError): profile.validate_report(report, definition)


if __name__ == '__main__': unittest.main()
