import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import boss_offline_inventory as inventory


BASE = '/PBZCombatAsset/ActorData/Mobs/001_Test/'
ACTOR = BASE + 'BP_Monster_Test.BP_Monster_Test_C'
CONFIG = BASE + 'ActorConfig/ActorC_Test.ActorC_Test'
SKILL = BASE + 'Ability/GA_Test.GA_Test_C'
FOLDERS = {'001_test': '001_Test'}


def lines(*entries):
    return ['[time] [Lua] PBZ_CONTROL_LIFECYCLE:' + entry for entry in entries]


def prefix():
    return ['SPAWN_ATTEMPT=1', 'CANDIDATE_IDENTITY_READY=001_test|' + ACTOR + '|' + CONFIG]


def candidate():
    return dict(id='001_test', resource_folder='001_Test', reference_only=False, assets=[
        dict(role='character_blueprint_clue', package=ACTOR.split('.')[0]),
        dict(role='actor_config_clue', package=CONFIG.split('.')[0]),
        dict(role='ability_clue', package=SKILL.split('.')[0])])


class InventoryBoundaryTests(unittest.TestCase):
    def extract(self, entries, profiles=()):
        return list(inventory.grant_snapshots(lines(*entries), FOLDERS, profiles))

    def test_counts_and_boundaries(self):
        entries = [*prefix(), 'GRANTED_COUNT=1', 'GRANTED_ABILITY=Class ' + SKILL, 'ISSUE_READY=done']
        found = self.extract(entries)
        self.assertEqual(found[0]['grants'], {SKILL: 1})
        self.assertEqual(found[0]['identity_source'], 'explicit_candidate_identity')
        self.assertFalse(self.extract(entries[:-1]))  # truncated raw stream

    def test_incomplete_and_overfull_dumps_rejected(self):
        for count, copies in ((2, 1), (1, 2), (0, 1), (513, 1)):
            with self.subTest(count=count, copies=copies):
                self.assertFalse(self.extract([*prefix(), f'GRANTED_COUNT={count}',
                    *['GRANTED_ABILITY=Class ' + SKILL] * copies, 'END=done']))

    def test_duplicate_specs_are_not_silently_unique(self):
        found, = self.extract([*prefix(), 'GRANTED_COUNT=2', *['GRANTED_ABILITY=Class ' + SKILL] * 2, 'END=x'])
        self.assertEqual(found['grants'][SKILL], 2)

    def test_cannot_borrow_next_spawn_grants(self):
        self.assertFalse(self.extract([*prefix(), 'SPAWN_ATTEMPT=2', 'GRANTED_COUNT=1',
            'GRANTED_ABILITY=Class ' + SKILL, 'END=x']))
        self.assertFalse(self.extract([*prefix(), 'CANDIDATE_IDENTITY_READY=bad', 'GRANTED_COUNT=1',
            'GRANTED_ABILITY=Class ' + SKILL, 'END=x']))

    def test_foreign_identity_is_rejected(self):
        for actor, config in ((ACTOR.replace('001_Test', '002_Foreign'), CONFIG),
                              (ACTOR, CONFIG.replace('001_Test', '002_Foreign'))):
            self.assertFalse(self.extract(['SPAWN_ATTEMPT=1',
                'CANDIDATE_IDENTITY_READY=001_test|' + actor + '|' + config,
                'GRANTED_COUNT=1', 'GRANTED_ABILITY=Class ' + SKILL, 'END=x']))

    def test_spawn_cdo_requires_exact_published_actor(self):
        profile = dict(folder='001_test', actor=ACTOR, config=CONFIG)
        cdo = 'SPAWN_STATE=class_default|object=BP_Monster_Test_C ' + BASE + 'BP_Monster_Test.Default__BP_Monster_Test_C|root=true'
        entries = ['SPAWN_ATTEMPT=1', cdo, 'GRANTED_COUNT=1', 'GRANTED_ABILITY=Class ' + SKILL, 'END=x']
        self.assertFalse(self.extract(entries))
        self.assertEqual(self.extract(entries, [profile])[0]['identity_source'], 'spawn_cdo_and_v5_config')
        self.assertFalse(self.extract([e.replace('class_default', 'target_before_finish_1') for e in entries], [profile]))

    def test_utility_does_not_become_attack_pool(self):
        self.assertTrue(inventory.special_ability(BASE + 'Ability/GA_Test_SwitchPhase.GA_Test_SwitchPhase_C'))
        self.assertTrue(inventory.special_ability(BASE + 'Ability/GA_Test_GroupResurrect.GA_Test_GroupResurrect_C'))
        self.assertFalse(inventory.special_ability(SKILL))

    def test_metadata_conflict_and_false_observations(self):
        status, fact = inventory.observation_state([
            dict(metadata_verified=False, ability_kind='leaf')], ('ability_kind',))
        self.assertEqual((status, fact), ('rejected', None))
        status, fact = inventory.observation_state([
            dict(metadata_verified=True, ability_kind='leaf'),
            dict(metadata_verified=True, ability_kind='subtree')], ('ability_kind',))
        self.assertEqual((status, fact), ('conflict', None))

    def test_grants_do_not_cross_variants(self):
        snap = dict(id='001_test', actor=ACTOR, config=CONFIG, session='old',
                    grant_count_line=5, grants={SKILL: 1}, identity_source='explicit_candidate_identity')
        receipts = {('001_test', SKILL): [dict(role='ability', metadata_verified=True,
                    ability_kind='leaf', receipt='fixture')]}
        rows, batches = inventory.plan(dict(candidates=[candidate()]), receipts, [snap], {})
        ability = rows[0]['abilities'][0]
        self.assertEqual(ability['route'], 'leaf_with_historical_grant')
        self.assertEqual(ability['grants'][0]['actor'], ACTOR)
        self.assertNotIn('playable', ability)
        self.assertEqual(batches, [])

    def test_exact_unindexed_grants_get_bounded_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            rows = []
            for index in range(5):
                identifier = f'role_{index}'
                rows.append(dict(id=identifier, abilities=[dict(path=SKILL.replace('GA_Test', f'GA_Test_{j}'),
                    route='exact_grant_needs_metadata', catalog_clue=False,
                    grants=[dict(count=1, actor=ACTOR, config=CONFIG)]) for j in range(35)]))
            batches = inventory.write_exact_batches(rows, root / 'generated', root, 'fixture')
            self.assertEqual(sum(batch['requests'] for batch in batches), 175)
            for batch in batches:
                manifest = inventory.read(root / batch['directory'] / 'manifest.json')
                self.assertLessEqual(len(manifest['jobs']), 64)
                self.assertLessEqual(len({job['id'] for job in manifest['jobs']}), 3)
                self.assertFalse(manifest['activation_allowed'])


if __name__ == '__main__':
    unittest.main()
