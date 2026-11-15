import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import build_yanqiansui_profile as profile


class YanQianSuiProfileTests(unittest.TestCase):
    def report(self):
        prefix = '/PBZCombatAsset/ActorData/Mobs/073_YanQianSui/Ability/GA_YanQianSui_'
        return {'id': profile.IDENTIFIER, 'target_build_sha256': profile.BUILD,
                'base_control_accepted': True, 'playable': False, 'stability': {'passed': True},
                'cleanup': {k: True for k in ('boss', 'boss_controller', 'target', 'target_controller',
                                             'extra_target', 'extra_target_controller')},
                'movement_camera': {k: True for k in ('movement_verified', 'camera_rotation_verified', 'milestone_passed')},
                'accepted_skills': {skill: {'class_path': prefix + native + '.GA_YanQianSui_' + native + '_C',
                    'natural_completion_verified': True, 'cancellation_runtime_verified': True,
                    'gameplay_verified': skill != 'dash', 'movement_runtime_verified': True}
                    for _, skill, _, _, native in profile.SLOTS}}

    def test_missing_cancellation_or_effect_never_promotes(self):
        for field in ('natural_completion_verified', 'cancellation_runtime_verified', 'effects'):
            report = self.report()
            row = report['accepted_skills']['skill_01']
            if field == 'effects':
                row['gameplay_verified'] = row['movement_runtime_verified'] = False
            else:
                row[field] = False
            with self.subTest(field=field), self.assertRaises(AssertionError):
                profile.validate_report(report)

    def test_scene_dependent_or_missing_action_rejected(self):
        for changed in ('scene', 'missing', 'duplicate'):
            report = self.report()
            if changed == 'scene':
                report['accepted_skills']['skill_02']['class_path'] = report['accepted_skills']['skill_02']['class_path'].replace('Skill_03', 'Skill_01')
            elif changed == 'missing':
                del report['accepted_skills']['dash']
            else:
                report['accepted_skills']['dash'] = copy.deepcopy(report['accepted_skills']['skill_02'])
            with self.subTest(changed=changed), self.assertRaises(AssertionError):
                profile.validate_report(report)

    def test_failed_stability_cleanup_or_motion_rejected(self):
        for section, field in (('stability', 'passed'), ('cleanup', 'extra_target'),
                               ('movement_camera', 'camera_rotation_verified')):
            report = self.report()
            report[section][field] = False
            with self.subTest(section=section), self.assertRaises(AssertionError):
                profile.validate_report(report)

    def test_camera_is_extracted_from_tested_module(self):
        self.assertEqual(profile.camera_from('camera={binding_verified=false,distance=650,min_pitch=-60}'),
                         {'binding_verified': True, 'distance': 650, 'min_pitch': -60})
        for source in ('camera={binding_verified=false,distance=0/0}',
                       'camera={binding_verified=false,distance=650,distance=900}',
                       'camera={binding_verified=true,distance=650}'):
            with self.subTest(source=source), self.assertRaises(AssertionError):
                profile.camera_from(source)

    def test_staging_is_repeatable_and_does_not_register_boss(self):
        session = '20261116-000000'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = self.report()
            sources = {}

            def put(name, value):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value.encode('utf-8') if isinstance(value, str) else json.dumps(value).encode('utf-8'))
                sources[name] = profile.sha(path)
                return path

            state = put('runtime/official-validation-' + session + '/state.json', {'restored': True})
            work = 'evidence/official-validation/' + session + '/'
            put(work + 'postcheck.json', {'validation_state': str(state), 'research_box_empty': True,
                'research_loader_removed': True, 'host_registry_unchanged': True,
                'formal_files_changed': [], 'host_config_files_changed': []})
            receipt = put('research/identity.json', {'fixture': True})
            identity = {'id': profile.IDENTIFIER, 'identity_verified': True, 'class_path': '/Fixture.Boss_C',
                'config_path': '/Fixture.Config', 'display_name': '琴女烟千岁',
                'receipt': receipt.relative_to(root).as_posix(), 'receipt_sha256': profile.sha(receipt)}
            report['metadata_identity'] = identity
            bundle_dir = 'research/boss-adaptation/developer-bundles/fixture/'
            module = put(bundle_dir + 'boss_candidate.lua', 'camera={binding_verified=false,distance=650}')
            put(bundle_dir + 'manifest.json', {'id': profile.IDENTIFIER, 'target_build_sha256': profile.BUILD,
                'developer_only': True, 'playable': False, 'definition': identity,
                'overrides': {'Scripts/boss_candidate.lua': profile.sha(module)}})
            runtime = put('mod/PBZBossControl/Scripts/runtime.lua', '-- unchanged runtime')
            catalog = put('mod/PBZBossControl/Scripts/boss_catalog.lua', '-- unchanged catalog')
            report['module_source_sha256'] = {'boss_candidate.lua': profile.sha(module),
                                             'runtime.lua': profile.sha(runtime), 'boss_catalog.lua': profile.sha(catalog)}
            report['sources'] = sources.copy()
            put(work + 'boss-candidate-acceptance.json', report)
            target = profile.build(session, root)
            self.assertEqual(target, profile.build(session, root))
            self.assertEqual(catalog.read_text(), '-- unchanged catalog')
            receipt = profile.read(target / 'profile-candidate.json')
            self.assertFalse(receipt['playable'])
            self.assertFalse(receipt['player_registry_modified'])
            self.assertFalse(receipt['ordinary_switching_accepted'])
            self.assertEqual(len(receipt['files']), 2)
            module.write_text('tampered')
            with self.assertRaises(AssertionError):
                profile.build(session, root)


if __name__ == '__main__':
    unittest.main()
