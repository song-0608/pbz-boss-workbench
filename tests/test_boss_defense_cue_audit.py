import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import boss_defense_cue_audit as audit

PARENT = '/PBZCombatAsset/GA_Parent.GA_Parent_C'
CHILD = '/PBZCombatAsset/GA_Child.GA_Child_C'


def reference(path, field='Super'):
    package, name = path.rsplit('.', 1)
    return {field: dict(ObjectName=f"LegoAbilityBlueprintGeneratedClass'{name}'", ObjectPath=package+'.123')}


def ability(path, parent=None, declared=True):
    ref = reference(parent)['Super'] if parent else None
    return dict(class_path=path, serialized_super=ref, issues=[],
        serialized_class_properties={'AbilityTimelines': []} if declared else {},
        timelines=[dict(name='Main', actions=[dict(ordinal=3, track=2, start_seconds=-0.01,
            duration_seconds=0.5, action_type='GAAction_WeaponParticle_BlueRedEye_C',
            serialized_action_properties={'ActivationRequirements': {'RequireTags': ['Native.Blue']}})])]
            if declared else [])


class DefenseCueAuditTests(unittest.TestCase):
    def test_weapon_overrides_keep_absent_empty_and_exact_grants_distinct(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'weapon.json'
            objects = [dict(Type='PBZ_MainWeaponConfig_C', Name=name, Properties=props)
                for name, props in [('Absent', {}), ('Empty', {'Equip Abilities': []}),
                    ('Stance', {'Equip Abilities': [reference(PARENT)['Super']]})]]
            path.write_text(json.dumps(objects), encoding='utf-8')
            row = dict(package='/PBZ/Weapon_Example', declaration=path.name,
                       declaration_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            result = audit.weapon_declarations(folder, {'packages': [row]})
            self.assertEqual([r['equip_abilities_declared'] for r in result], [False, True, True])
            self.assertEqual([r['equipped_class_paths'] for r in result], [[], [], [PARENT]])
            self.assertTrue(all(r['live_grant_verified'] is False for r in result))
            path.write_text('[]', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'changed'):
                audit.weapon_declarations(folder, {'packages': [row]})

    def test_weapon_grants_require_exact_classes_and_a_serialized_list(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'weapon.json'
            for invalid in (None, {}, [dict(ObjectName="AnimMontage'Fake'", ObjectPath='/X.0')]):
                path.write_text(json.dumps([dict(Type='PBZ_MainWeaponConfig_C', Name='Bad',
                    Properties={'Equip Abilities': invalid})]), encoding='utf-8')
                row = dict(package='/PBZ/Weapon_Example', declaration=path.name,
                           declaration_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                with self.assertRaises(ValueError):
                    audit.weapon_declarations(folder, {'packages': [row]})

    def test_empty_native_tables_are_incomplete_not_absent_interfaces(self):
        asc = dict(path='/Script/GameplayAbilities.AbilitySystemComponent', properties=[], functions=[])
        self.assertFalse(audit.native_contract_ready([asc]))
        asc['properties'] = [{'name': 'ActivatableAbilities'}]
        self.assertFalse(audit.native_contract_ready([asc]))
        asc['functions'] = [{'name': 'TryActivateAbilityByClass'}]
        self.assertTrue(audit.native_contract_ready([asc]))

    def test_both_native_parent_fields_and_conflicts(self):
        self.assertEqual(audit.parent_reference(reference(PARENT)), PARENT)
        self.assertEqual(audit.parent_reference(reference(PARENT, 'SuperStruct')), PARENT)
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            audit.parent_reference(dict(**reference(PARENT), **reference(CHILD, 'SuperStruct')))
        self.assertIsNone(audit.class_reference(dict(ObjectName="AnimMontage'GA_Fake_C'", ObjectPath='/X.0')))

    def test_inherited_timeline_keeps_owner_time_track_and_activation_requirements(self):
        parent, child = ability(PARENT), ability(CHILD, PARENT, declared=False)
        original = copy.deepcopy(parent)
        result = list(audit.cue_actions(child, {PARENT: parent, CHILD: child}))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['timeline_owner'], PARENT)
        self.assertEqual((result[0]['ordinal'], result[0]['track'], result[0]['start_seconds']), (3, 2, -0.01))
        self.assertEqual(result[0]['activation_requirements'], {'RequireTags': ['Native.Blue']})
        self.assertEqual(parent, original)

    def test_explicit_empty_override_does_not_resurrect_parent_cues(self):
        parent, child = ability(PARENT), ability(CHILD, PARENT)
        child['timelines'] = []
        self.assertEqual(list(audit.cue_actions(child, {PARENT: parent})), [])

    def test_cycles_and_unresolved_parents_are_not_silently_verified(self):
        with self.assertRaisesRegex(ValueError, 'cycle'):
            audit.lineage(PARENT, {PARENT: {'parent': CHILD}, CHILD: {'parent': PARENT}})
        child, parent = ability(CHILD, PARENT, False), ability(PARENT, CHILD, False)
        with self.assertRaisesRegex(ValueError, 'cycle'):
            list(audit.cue_actions(child, {CHILD: child, PARENT: parent}))
        self.assertEqual(audit.lineage(CHILD, {CHILD: {'parent': PARENT}}), ([CHILD, PARENT], PARENT))

    def test_stance_uses_ancestry_and_never_promotes_runtime_access(self):
        stance = ability(PARENT, audit.STANCE_BASE, declared=False)
        index = dict(kind='offline_serialized_boss_skill_index', indexing_issues=0, failed_packages=0,
                     pending_packages=0, packages=[dict(folder='fixture', abilities=[stance])])
        result = audit.audit(index, {'rows': []}, {audit.STANCE_BASE: {'parent': None}}, [])
        self.assertEqual(result['declared_stance_classes'], 1)
        self.assertFalse(result['activation_allowed'])
        self.assertFalse(result['defense_runtime_verified'])
        self.assertFalse(result['cue_render_verified'])
        bad = copy.deepcopy(index)
        bad['packages'][0]['abilities'].append(stance)
        with self.assertRaisesRegex(ValueError, 'Unique'):
            audit.audit(bad, {'rows': []}, {}, [])

    def test_colored_effect_and_missing_state_remain_declared_conditions(self):
        a = ability(PARENT)
        action = a['timelines'][0]['actions'][0]
        action['action_type'] = 'GAAction_WeaponParticleFrame_C'
        action['serialized_action_properties']['NiagaraEffect'] = {'AssetPathName': '/FX/NS_Ground_Red_101.NS_Ground_Red_101'}
        found, = audit.cue_actions(a, {PARENT: a})
        self.assertEqual(found['activation_requirements']['RequireTags'], ['Native.Blue'])
        self.assertEqual(found['explicit_cue_assets'], ['/FX/NS_Ground_Red_101.NS_Ground_Red_101'])


if __name__ == '__main__':
    unittest.main()
