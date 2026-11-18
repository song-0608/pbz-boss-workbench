import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from prepare_boss_variant_candidates import ability_reason, definitions
import prepare_boss_variant_candidates as variants


class BossVariantCandidatesTests(unittest.TestCase):
    def fixture(self):
        prefix = '/PBZCombatAsset/ActorData/Mobs/Fixture/'
        actor = prefix + 'BP_Monster_Fixture.BP_Monster_Fixture_C'
        variant = dict(path=actor, metadata='verified', spawn_configs=[], receipts=['character.json'],
            observation=dict(observed_config=prefix + 'ActorData/ActorC_Fixture.ActorC_Fixture',
                display_name='测试角色', lineage=[actor, '/Script/ProjectPBZ.PBZCharacter_NPC', '/Script/Engine.Character']))
        abilities = [dict(path=prefix + f'Ability/GA_Fixture_Skill_{i:02}.GA_Fixture_Skill_{i:02}_C',
            metadata='verified', kind='leaf', receipts=['leaf.json'], grants=[])
            for i in range(1, 36)]
        return [dict(id='fixture', folder='Fixture', variants=[variant], abilities=abilities)], \
            {'character.json': 'identity', 'leaf.json': 'ability'}

    def test_all_leaf_candidates_are_bounded_without_claiming_grants_or_playability(self):
        characters, sources = self.fixture()
        pools, deferred = definitions(characters, sources)
        self.assertEqual([len(p['definition']['ability_pool']) for p in pools], [32, 3])
        self.assertFalse(deferred)
        self.assertEqual(len({a for p in pools for a in p['definition']['ability_pool']}), 35)
        for pool in pools:
            self.assertFalse(pool['playable'] or pool['runtime_verified'] or pool['activation_allowed']
                             or pool['historical_native_grants_verified'])
            self.assertEqual(pool['definition']['config_path'], characters[0]['variants'][0]['observation']['observed_config'])

    def test_existing_grants_rejected_metadata_contexts_and_empty_families_do_not_become_candidates(self):
        for mutate in (
            lambda c: c[0]['variants'][0].update(spawn_configs=['native observed']),
            lambda c: c[0]['variants'][0].update(metadata='rejected'),
            lambda c: c[0]['variants'][0]['observation'].update(display_name='None'),
            lambda c: c[0].update(abilities=[]),
            lambda c: c[0]['variants'][0].update(path=c[0]['variants'][0]['path'].replace('Fixture_C', 'Fixture_ForSeq_C')),
        ):
            characters, sources = self.fixture()
            mutate(characters)
            self.assertFalse(definitions(characters, sources)[0])

    def test_cross_folder_missing_lineage_receipts_or_config_cannot_be_paired(self):
        for mutate in (
            lambda c: c[0]['variants'][0]['observation'].update(observed_config='/Other.ActorC_Other'),
            lambda c: c[0]['variants'][0]['observation'].update(lineage=['/Script/Engine.Character']),
            lambda c: c[0]['variants'][0].update(receipts=[]),
            lambda c: c[0]['abilities'][0].update(path='/Other.GA_Fixture_Skill_01_C'),
            lambda c: c[0]['abilities'][0].update(receipts=[]),
        ):
            characters, sources = self.fixture()
            mutate(characters)
            with self.assertRaises(AssertionError):
                definitions(characters, sources)

    def test_contextual_abilities_never_receive_standalone_keys(self):
        prefix = '/PBZCombatAsset/ActorData/Mobs/Fixture/Ability/'
        for short in ('GA_Fixture_Skill_01_Child_C', 'GA_Fixture_CA_01_GEx_C',
                      'GA_Fixture_Skill_01_GEd_C', 'GA_Fixture_Passive_C',
                      'GA_Fixture_Skill_01_Seq_C', 'GA_Fixture_Resurrect_C'):
            self.assertTrue(ability_reason(prefix + short[:-2] + '.' + short), short)
        self.assertIsNone(ability_reason(prefix + 'GA_Fixture_MiddleAttack_01.GA_Fixture_MiddleAttack_01_C'))

    def test_verification_reconstructs_immutable_module_and_manifest(self):
        characters, sources = self.fixture()
        entries, deferred = definitions(characters, sources)
        identity = dict(definitions=entries, deferred=deferred)
        key = 'fixture-fingerprint'
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            for source in variants.SOURCES:
                path = root / source
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'-- fixture source\n')
            target = root / variants.OUTPUT / key
            rows = variants.write_candidates(identity, key, target, root)
            directory = root / rows[0]['directory']
            with patch.object(variants, 'inputs', return_value=(identity, key)):
                self.assertFalse(variants.verify(directory, root)['playable'])
                for file in ('boss_candidate.lua', 'manifest.json'):
                    path = directory / file
                    original = path.read_bytes()
                    path.write_bytes(b'changed')
                    with self.subTest(file=file), self.assertRaises(AssertionError):
                        variants.verify(directory, root)
                    self.assertEqual(path.read_bytes(), b'changed', 'verification must never repair evidence')
                    path.write_bytes(original)

    def test_generated_controller_accepts_catalog_scope_only_after_bundle_validation(self):
        import boss_inventory_bundle as bundle
        import prepare_boss_inventory_workflow as workflow
        files = workflow.render()
        runner = files['stage_candidate.py'].decode('utf-8')
        self.assertIn('044_pengmeng', runner)
        self.assertIn('inventory_ui_controller', runner)
        self.assertNotIn('menu.click', runner)
        self.assertIn('controller.begin_stage', runner)
        self.assertIn('from boss_inventory_spawn_repair import overrides', runner)
        self.assertIn('module_overrides.update(overrides())', runner)
        self.assertIn('source_files=previous.source_hashes(root)',
                      files['inventory_ui_controller.py'].decode('utf-8'))
        gate = {}
        exec(compile(files['boss_candidate_gate.py'], 'generated-variant-gate', 'exec'), gate)
        with patch.object(bundle, 'validate', return_value={'exact_bundle': True}) as validate:
            result = gate['validate']('044_pengmeng', bundle=Path('exact-bundle'))
            self.assertEqual(result, {'exact_bundle': True})
            validate.assert_called_once()
            with self.assertRaises(RuntimeError):
                gate['validate']('not-in-observed-catalog', bundle=Path('exact-bundle'))
            with self.assertRaises(RuntimeError):
                gate['validate']('044_pengmeng', bundle=None)
        with patch.object(bundle, 'historical_pool', side_effect=AssertionError('unregistered exact candidate')):
            with self.assertRaisesRegex(AssertionError, 'unregistered exact candidate'):
                bundle.validate('unknown', Path('runtime/unregistered-candidate').resolve())

    def test_native_dump_preserves_present_but_unbound_skills_and_variant_boundaries(self):
        characters, sources = self.fixture()
        pools, _ = definitions(characters, sources)
        definition = pools[0]['definition']
        paths = definition['ability_pool']
        events = ['SPAWN_ATTEMPT=1', 'CANDIDATE_IDENTITY_READY=fixture|'
            + definition['class_path'] + '|' + definition['config_path'], 'GRANTED_COUNT=6']
        events += ['GRANTED_ABILITY=BlueprintGeneratedClass ' + path for path in paths[:6]]
        events += ['INTERACTIVE_READY=true']
        tail = '\n'.join('[Lua] PBZ_CONTROL_LIFECYCLE:' + event for event in events)
        bindings = [dict(class_path=path) for path in paths[:4]]
        result = variants.captured_grants(tail, definition, bindings)
        self.assertEqual(result['missing_native_grants'], paths[6:])
        self.assertEqual(result['unbound_candidates'], paths[4:6])
        self.assertEqual(result['duplicate_native_candidates'], [])
        self.assertNotIn(paths[4], result['missing_native_grants'])
        self.assertTrue(set(result['unbound_candidates']).isdisjoint(result['missing_native_grants']))
        for broken in (tail.replace('GRANTED_COUNT=6', 'GRANTED_COUNT=7'),
                       tail.replace(definition['config_path'], '/Other.Config'),
                       tail.replace('INTERACTIVE_READY=true', '')):
            with self.subTest(broken=broken), self.assertRaises(AssertionError):
                variants.captured_grants(broken, definition, bindings)
        with self.assertRaises(AssertionError):
            variants.captured_grants(tail, definition, [dict(class_path=paths[-1])])

    def test_duplicate_grants_are_separate_from_missing_or_unbound_candidates(self):
        characters, sources = self.fixture()
        pools, _ = definitions(characters, sources)
        definition = pools[0]['definition']
        paths = definition['ability_pool']
        events = ['SPAWN_ATTEMPT=1', 'CANDIDATE_IDENTITY_READY=fixture|'
            + definition['class_path'] + '|' + definition['config_path'], 'GRANTED_COUNT=4']
        events += ['GRANTED_ABILITY=BlueprintGeneratedClass ' + path
                   for path in (paths[0], paths[1], paths[1], paths[2])]
        events += ['INTERACTIVE_READY=true']
        tail = '\n'.join('[Lua] PBZ_CONTROL_LIFECYCLE:' + event for event in events)
        result = variants.captured_grants(tail, definition, [dict(class_path=paths[0])])
        self.assertEqual(result['unbound_candidates'], [paths[2]])
        self.assertEqual(result['duplicate_native_candidates'], [paths[1]])
        self.assertEqual(result['missing_native_grants'], paths[3:])
        with self.assertRaises(AssertionError):
            variants.captured_grants(tail, definition, [dict(class_path=paths[1])])


if __name__ == '__main__':
    unittest.main()
