import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import release_four_boss_workbench as release


class ReleaseTests(unittest.TestCase):
    def test_inheritance_changes_only_catalog_and_unaccepted_search(self):
        candidate = release.ROOT / 'runtime/release-candidates' / release.expected()[-1]
        self.assertTrue(release.inherited(candidate)['unchanged_execution_camera_input_restoration'])

    def test_missing_world_movement_or_real_skills_cannot_publish(self):
        current = {'runtime.lua': 'test'}
        previous = [{'skill': str(i)} for i in range(8)]
        roles = [('ahua_guitoudao', 'skill_01', False), ('ahua_guitoudao', 'skill_08', True),
                 ('073_yanqiansui', 'skill_01', False), ('073_yanqiansui', 'skill_01', False)]
        report = {'id': '073_yanqiansui', 'module_source_sha256': current, 'passed': True,
                  'ordinary_roundtrip_verified': True, 'input_layers_recovered': True,
                  'owned_object_cleanup_verified': True, 'new_profile_world_cycle_verified': True,
                  'movement_camera': {'passed': True}, 'world_cycle': {'passed': True, 'skill_natural_damage': True},
                  'reused_ordinary_skills': previous,
                  'skill_proofs': [dict(boss=b, skill=s, interrupt=i, local_displacement_verified=True,
                                       active_cancel_and_restoration=True, natural_completion=True, restoration={'passed': True}) for b, s, i in roles]}
        release.validate_integration(report, current, previous)
        for key in ('passed', 'ordinary_roundtrip_verified', 'input_layers_recovered', 'owned_object_cleanup_verified', 'new_profile_world_cycle_verified'):
            bad = copy.deepcopy(report);bad[key] = False
            with self.subTest(key=key), self.assertRaises(AssertionError):release.validate_integration(bad, current, previous)
        for key in ('movement_camera', 'world_cycle'):
            bad = copy.deepcopy(report);bad[key]['passed'] = False
            with self.subTest(key=key), self.assertRaises(AssertionError):release.validate_integration(bad, current, previous)
        bad = copy.deepcopy(report);bad['skill_proofs'].pop()
        with self.assertRaises(AssertionError):release.validate_integration(bad, current, previous)
        with self.assertRaises(AssertionError):release.validate_integration(report, {'runtime.lua': 'changed'}, previous)


if __name__ == '__main__':unittest.main()
