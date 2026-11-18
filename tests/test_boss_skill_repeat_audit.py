import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import boss_skill_repeat_audit as audit


def entry(session='20261118-220000', actor='Boss0'):
    return ('[PBZBossControl] enter success=true state=ACTIVE reason=\n'
        'PBZ_CONTROL_LIFECYCLE:CONTROL_WORLD_ID=official-validation-' + session + '|World Test|77\n' +
        ''.join('PBZ_CONTROL_LIFECYCLE:CONTROL_PARTICIPANT=' + kind + '|' + name +
                '|address=' + str(address) + '|class=Class ' + name + '\n'
                for kind, name, address in (('player_controller', 'PC0', 10), ('player', 'Player0', 20), ('boss', actor, 30))))


def cast(before=1000, damage=100, distance=12, skill='skill_01', cls='GA_Test_C'):
    return (f'PBZ_CONTROL_LIFECYCLE:KEY_SKILL_BEGIN={skill}|target=Target0|health={before}|active=1\n'
            f'PBZ_CONTROL_LIFECYCLE:SKILL_INSTANCE={skill}|active=true|cancelable=true|object={cls} Boss0.Instance0\n'
            f'PBZ_CONTROL_LIFECYCLE:KEY_SKILL_END={skill}|peak=1|active=0|natural=true|health_before={before}'
            f'|health_after={before-damage}|distance={distance}|sample_ticks=12|tail_ticks=15\n')


def restore(label='exit'):
    return (f'[PBZBossControl] {label} success=true state=OFF reason=finished\n'
            'PBZ_CONTROL_LIFECYCLE:ORIGINAL_PLAYER_POSITION_DELTA=0.0\n'
            'PBZ_CONTROL_LIFECYCLE:ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0\n'
            'PBZ_CONTROL_LIFECYCLE:CAMERA_CLEANUP_ENGINE_VERIFIED=true\n')


def cycle(count=5, damage=100, label='exit'):
    return entry() + ''.join(cast(1000 - i*damage, damage) for i in range(count)) + restore(label)


class RepeatAuditTests(unittest.TestCase):
    def test_five_uses_with_one_receipt_and_one_recovery(self):
        row = audit.audit_cycle(cycle(), 'skill_01', 'GA_Test_C')
        self.assertTrue(row['same_control_verified'])
        self.assertTrue(row['consecutive_natural_uses_verified'])
        self.assertTrue(row['every_use_health_decrease_observed'])
        self.assertTrue(row['explicit_player_exit_verified'])
        self.assertTrue(row['repeated_effect_and_recovery_observed'])
        self.assertEqual([a['observed_health_decrease'] for a in row['attempts']], [100]*5)
        for key in ('playable', 'release_accepted', 'cancellation_verified', 'exact_native_grant_path_verified'):
            self.assertFalse(row[key])

    def test_two_uses_are_not_enough_and_movement_is_not_attack_damage(self):
        row = audit.audit_cycle(cycle(2), 'skill_01', 'GA_Test_C')
        self.assertEqual(row['observed_attempts'], 2)
        self.assertFalse(row['consecutive_natural_uses_verified'])
        row = audit.audit_cycle(cycle(damage=0), 'skill_01', 'GA_Test_C')
        self.assertTrue(row['consecutive_natural_uses_verified'])
        self.assertFalse(row['every_use_health_decrease_observed'])
        self.assertFalse(row['repeated_effect_and_recovery_observed'])
        row = audit.audit_cycle(cycle(damage=0), 'skill_01', 'GA_Test_C', action_kind='dodge')
        self.assertTrue(row['every_use_dodge_displacement_observed'])
        self.assertTrue(row['repeated_effect_and_recovery_observed'])
        self.assertFalse(row['every_use_health_decrease_observed'])

    def test_interrupted_class_changed_duplicate_and_incomplete_uses_fail(self):
        original = cycle()
        for mode in ('end', 'instance', 'active', 'natural', 'wrong_class', 'duplicate_end', 'duplicate_instance',
                     'health', 'foreign', 'too_far', 'native_rejected', 'late_sixth_failure', 'after_exit_skill'):
            text = original
            if mode == 'end': text = text.replace('KEY_SKILL_END=skill_01', 'MISSING_END=skill_01', 1)
            elif mode == 'instance': text = text.replace('SKILL_INSTANCE=skill_01', 'NO_INSTANCE=skill_01', 1)
            elif mode == 'active': text = text.replace('|active=0|natural=true', '|active=1|natural=true', 1)
            elif mode == 'natural': text = text.replace('|natural=true|', '|natural=false|', 1)
            elif mode == 'wrong_class': text = text.replace('object=GA_Test_C', 'object=GA_Foreign_C', 1)
            elif mode == 'duplicate_end': text = text.replace(restore(), cast().splitlines()[-1] + '\n' + restore())
            elif mode == 'duplicate_instance': text = text.replace('KEY_SKILL_END=skill_01', 'SKILL_INSTANCE=skill_01|active=true|cancelable=true|object=GA_Test_C Boss0.Instance0\nKEY_SKILL_END=skill_01', 1)
            elif mode == 'health': text = text.replace('health_before=1000', 'health_before=999', 1)
            elif mode == 'foreign': text = text.replace('skill_01', 'heavy_01', 3)
            elif mode == 'too_far': text = text.replace('distance=12', 'distance=3001', 1)
            elif mode == 'native_rejected': text = text.replace(restore(), 'SKILL_NATIVE_REJECTED=skill_01|consecutive=1\n' + restore())
            elif mode == 'after_exit_skill': text += cast().splitlines()[-1] + '\n'
            else: text = original.replace(restore(), cast(500).replace('natural=true', 'natural=false') + restore())
            with self.subTest(mode=mode):
                row = audit.audit_cycle(text, 'skill_01', 'GA_Test_C')
                self.assertFalse(row['repeated_effect_and_recovery_observed'])

    def test_natural_completion_does_not_replace_recovery_or_manual_exit(self):
        text = cycle().replace(restore(), '')
        row = audit.audit_cycle(text, 'skill_01', 'GA_Test_C')
        self.assertTrue(row['consecutive_natural_uses_verified'])
        self.assertFalse(row['restoration']['passed'])
        self.assertFalse(row['repeated_effect_and_recovery_observed'])
        row = audit.audit_cycle(cycle(label='auto_exit'), 'skill_01', 'GA_Test_C')
        self.assertTrue(row['restoration']['passed'])
        self.assertFalse(row['explicit_player_exit_verified'])
        text = cycle().replace('CAMERA_CLEANUP_ENGINE_VERIFIED=true', '')
        row = audit.audit_cycle(text, 'skill_01', 'GA_Test_C')
        self.assertFalse(row['repeated_effect_and_recovery_observed'])

    def test_cannot_join_takeovers_worlds_or_borrow_later_recovery(self):
        with self.assertRaises(AssertionError): audit.audit_cycle(cycle() + cycle(), 'skill_01', 'GA_Test_C')
        with self.assertRaises(AssertionError):
            audit.audit_cycle(cycle().replace(restore(), 'SPAWN_ATTEMPT=2\n' + restore()), 'skill_01', 'GA_Test_C')
        row = audit.audit_cycle(cycle().replace(restore(), 'CONTROL_WORLD_ID=new|world\n' + restore()), 'skill_01', 'GA_Test_C')
        self.assertFalse(row['same_control_verified'])
        text = cycle().replace('CAMERA_CLEANUP_ENGINE_VERIFIED=true', '') + restore()
        row = audit.audit_cycle(text, 'skill_01', 'GA_Test_C')
        self.assertFalse(row['restoration']['passed'])
        text = cycle() + cycle(3)
        _, _, first = audit.cycle_interval(text, 0)
        _, _, second = audit.cycle_interval(text, 1)
        self.assertEqual(audit.audit_cycle(first, 'skill_01', 'GA_Test_C')['observed_attempts'], 5)
        self.assertFalse(audit.audit_cycle(second, 'skill_01', 'GA_Test_C')['consecutive_natural_uses_verified'])

    def test_missing_identity_malformed_begin_and_unbounded_requirements_rejected(self):
        row = audit.audit_cycle(cycle().replace('CONTROL_PARTICIPANT=boss', 'MISSING=boss'), 'skill_01', 'GA_Test_C')
        self.assertFalse(row['same_control_verified'])
        with self.assertRaises(AssertionError):
            audit.audit_cycle(cycle().replace('health=1000', 'missing=1000', 1), 'skill_01', 'GA_Test_C')
        for count in (0, 2, 6, True):
            with self.assertRaises(AssertionError): audit.audit_cycle(cycle(), 'skill_01', 'GA_Test_C', repetitions=count)

    def fixture(self, root):
        session = '20261118-220000'
        work = root / 'evidence/official-validation' / session; work.mkdir(parents=True)
        state_path = root / 'runtime' / ('official-validation-' + session) / 'state.json'
        state_path.parent.mkdir(parents=True)
        state = dict(state_file=str(state_path), work=str(work), restored=True)
        post = dict(validation_state=str(state_path), research_box_empty=True, research_loader_removed=True,
                    host_registry_unchanged=True, formal_files_changed=[], host_config_files_changed=[])
        state_path.write_text(json.dumps(state), encoding='utf-8')
        (work / 'postcheck.json').write_text(json.dumps(post), encoding='utf-8')
        (work / 'UE4SS.log').write_text('earlier context\n' + cycle(), encoding='utf-8')
        return session, work, state_path, post

    def test_closed_audit_requires_unchanged_and_empty_research_box(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); session, work, state_path, post = self.fixture(root)
            row = audit.closed_audit(session, 0, 'skill_01', 'GA_Test_C', root=root)
            self.assertTrue(row['historical_observation_only'])
            self.assertFalse(row['runtime_acceptance_current'])
            self.assertEqual(len(row['sources']), 3)
            for key in ('research_box_empty', 'research_loader_removed', 'host_registry_unchanged'):
                changed = copy.deepcopy(post); changed[key] = False
                (work / 'postcheck.json').write_text(json.dumps(changed), encoding='utf-8')
                with self.assertRaises(AssertionError): audit.closed_audit(session, 0, 'skill_01', 'GA_Test_C', root=root)
            changed = dict(post, formal_files_changed=['changed'])
            (work / 'postcheck.json').write_text(json.dumps(changed), encoding='utf-8')
            with self.assertRaises(AssertionError): audit.closed_audit(session, 0, 'skill_01', 'GA_Test_C', root=root)


if __name__ == '__main__': unittest.main()
