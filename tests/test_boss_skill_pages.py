import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from prepare_boss_skill_pages import page_definitions, deferred_reason


ID = '058_maddoctor'
BASE = '/PBZCombatAsset/ActorData/Mobs/058_MadDoctor/'
ACTOR = BASE + 'BP_Test.BP_Test_C'
CONFIG = BASE + 'ActorConfig/ActorC_Test.ActorC_Test'


def fixture(count=9):
    character = dict(id=ID, folder='058_MadDoctor', variants=[dict(path=ACTOR,
        observation=dict(observed_config=CONFIG, display_name='fixture'), receipts=['identity'])], abilities=[])
    for index in range(count):
        path = BASE + f'Ability/GA_Test_{index:02d}.GA_Test_{index:02d}_C'
        character['abilities'].append(dict(path=path, route='leaf_with_historical_grant',
            metadata='verified', kind='leaf', receipts=['ability'],
            grants=[dict(actor=ACTOR, config=CONFIG, count=1,
                         session='20261119-010000', grant_count_line=20)]))
    return character


class SkillPageTests(unittest.TestCase):
    def plan(self, character):
        return page_definitions([character], {}, {'identity': 'identity-sha', 'ability': 'ability-sha'})

    def test_every_skill_has_a_stable_four_slot_page(self):
        character = fixture()
        pages, deferred = self.plan(character)
        self.assertFalse(deferred)
        self.assertEqual([len(p['definition']['ability_pool']) for p in pages], [4, 4, 1])
        self.assertEqual([s for p in pages for s in p['definition']['ability_pool']],
                         [a['path'] for a in character['abilities']])
        self.assertTrue(all(p['definition']['require_complete_pool'] for p in pages))
        character['abilities'].reverse()
        self.assertEqual(self.plan(character)[0], pages)

    def test_variant_grants_cannot_be_borrowed(self):
        character = fixture(2)
        character['abilities'][1]['grants'][0]['config'] = BASE + 'ActorConfig/Other.Other'
        pages, deferred = self.plan(character)
        self.assertEqual(len(pages), 1)
        self.assertEqual(len(pages[0]['definition']['ability_pool']), 1)
        self.assertEqual(len(deferred), 1)
        self.assertEqual(len(pages[0]['historical_unique_grants']), 1)

    def test_same_variant_with_disjoint_phase_grants_uses_separate_pages(self):
        character = fixture(4)
        for ability in character['abilities'][2:]:
            ability['grants'][0]['grant_count_line'] = 40
        pages, deferred = self.plan(character)
        self.assertFalse(deferred)
        self.assertEqual([len(p['definition']['ability_pool']) for p in pages], [2, 2])
        self.assertEqual([p['historical_grant_cohorts'] for p in pages], [
            [dict(session='20261119-010000', grant_count_line=20)],
            [dict(session='20261119-010000', grant_count_line=40)]])

    def test_same_line_in_different_sessions_is_not_one_snapshot(self):
        character = fixture(2)
        character['abilities'][1]['grants'][0]['session'] = '20261119-020000'
        pages, _ = self.plan(character)
        self.assertEqual([len(p['definition']['ability_pool']) for p in pages], [1, 1])

    def test_alternative_complete_snapshots_are_retained(self):
        character = fixture(2)
        for ability in character['abilities']:
            ability['grants'].append(dict(ability['grants'][0], session='20261119-020000'))
        pages, _ = self.plan(character)
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]['historical_grant_cohorts'], [
            dict(session='20261119-010000', grant_count_line=20),
            dict(session='20261119-020000', grant_count_line=20)])

    def test_overlapping_snapshots_cover_all_moves_once_and_stay_deterministic(self):
        character = fixture(7)
        for index, ability in enumerate(character['abilities']):
            if index >= 3:
                ability['grants'][0]['grant_count_line'] = 40
        character['abilities'][2]['grants'].append(dict(
            character['abilities'][2]['grants'][0], grant_count_line=40))
        pages, _ = self.plan(character)
        pools = [p['definition']['ability_pool'] for p in pages]
        self.assertEqual([len(pool) for pool in pools], [4, 2, 1])
        self.assertEqual(len({path for pool in pools for path in pool}), 7)
        for page in pages:
            for cohort in page['historical_grant_cohorts']:
                for path in page['definition']['ability_pool']:
                    ability = next(a for a in character['abilities'] if a['path'] == path)
                    self.assertTrue(any(all(g.get(k) == v for k, v in cohort.items())
                                        for g in ability['grants']))
        character['abilities'].reverse()
        for ability in character['abilities']:
            ability['grants'].reverse()
        self.assertEqual([p['definition'] for p in self.plan(character)[0]],
                         [p['definition'] for p in pages])

    def test_missing_or_invalid_snapshot_identity_cannot_merge_grants(self):
        for key, value in (('session', 'closed'), ('session', None),
                           ('grant_count_line', None), ('grant_count_line', 0),
                           ('grant_count_line', True)):
            character = fixture(1)
            character['abilities'][0]['grants'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(AssertionError):
                self.plan(character)

    def test_duplicate_only_or_unverified_grants_do_not_create_pages(self):
        character = fixture(1)
        character['abilities'][0]['grants'][0]['count'] = 2
        self.assertEqual(self.plan(character), ([], []))
        character['abilities'][0]['route'] = 'needs_variant_grant'
        self.assertEqual(self.plan(character), ([], []))

    def test_identity_conflict_and_absence_are_deferred(self):
        character = fixture(1)
        character['variants'].append(copy.deepcopy(character['variants'][0]))
        character['variants'][1]['observation']['display_name'] = 'different'
        self.assertFalse(self.plan(character)[0])
        character['variants'] = []
        self.assertFalse(self.plan(character)[0])

    def test_metadata_conflicts_are_not_silently_promoted(self):
        character = fixture(1)
        character['abilities'][0]['kind'] = 'subtree'
        with self.assertRaises(AssertionError):
            self.plan(character)

    def test_historical_scene_failure_and_utilities_stay_blocked(self):
        for name in ('GA_YanQianSui_Skill_01_C', 'GA_YouLong_SummonPassive_General_C',
                     'GA_XieQiuDong_SubTitles_C', 'GA_MadDoctor_RitualistHeal_C',
                     'GA_YouLong_FrontRecovery_C', 'GA_Test_SwitchPhase_C'):
            self.assertIsNotNone(deferred_reason(BASE + 'Ability/Test.' + name))
        self.assertIsNone(deferred_reason(BASE + 'Ability/Test.GA_Test_Skill_02_C'))

    def test_counter_context_cannot_be_paged_as_an_independent_attack(self):
        character = fixture(2)
        character['abilities'][0]['path'] = BASE + 'Ability/Test.GA_MadDoctor_CA_01_GEx_C'
        pages, deferred = self.plan(character)
        self.assertEqual(len(pages), 1)
        self.assertEqual(len(pages[0]['definition']['ability_pool']), 1)
        self.assertEqual(len(deferred), 1)
        self.assertIn('counter-context', deferred[0]['reason'])
        for name in ('GA_WanJun_CA_01_C', 'GA_YanQianSui_CA_01_Gex_C'):
            self.assertIn('counter-context', deferred_reason(BASE + 'Ability/Test.' + name))

    def test_new_role_moves_from_variant_pool_to_exact_pages_without_disappearing(self):
        from tests.test_boss_variant_candidates import BossVariantCandidatesTests
        from prepare_boss_variant_candidates import definitions
        characters, sources = BossVariantCandidatesTests().fixture()
        c = characters[0]
        c['abilities'] = c['abilities'][:3]
        self.assertEqual(len(definitions(characters, sources)[0]), 1)
        actor = c['variants'][0]['path']; config = c['variants'][0]['observation']['observed_config']
        c['variants'][0]['spawn_configs'] = [config]
        for ability in c['abilities']:
            ability.update(route='leaf_with_historical_grant', grants=[dict(actor=actor, config=config, count=1,
                session='20261119-010000', grant_count_line=20,
                identity_source='explicit_candidate_identity')])
        self.assertFalse(definitions(characters, sources)[0])
        pages, deferred = page_definitions(characters, {}, sources)
        self.assertFalse(deferred)
        self.assertEqual([p['definition']['ability_pool'] for p in pages], [[a['path'] for a in c['abilities']]])
        for change in ('lineage', 'metadata', 'actor_context', 'missing_grant', 'child'):
            candidate = copy.deepcopy(c)
            if change == 'lineage': candidate['variants'][0]['observation']['lineage'] = []
            elif change == 'metadata': candidate['variants'][0]['metadata'] = 'conflict'
            elif change == 'actor_context':
                candidate['variants'][0]['path'] += '_ForSeq'
                for a in candidate['abilities']: a['grants'][0]['actor'] = candidate['variants'][0]['path']
            elif change == 'missing_grant':
                for a in candidate['abilities']: a['grants'] = []
            else:
                for a in candidate['abilities']: a['path'] = a['path'].replace('_C', '_Child_C')
            with self.subTest(change=change):
                self.assertFalse(page_definitions([candidate], {}, sources)[0])

    def test_new_role_page_passes_exact_reconstruction_without_legacy_role_whitelist(self):
        import boss_inventory_bundle as bundle
        import prepare_boss_skill_pages as pages
        from boss_metadata_jobs import canonical
        from tests.test_boss_variant_candidates import BossVariantCandidatesTests
        characters, sources = BossVariantCandidatesTests().fixture()
        c = characters[0]; c['abilities'] = c['abilities'][:3]
        actor = c['variants'][0]['path']; config = c['variants'][0]['observation']['observed_config']
        for a in c['abilities']:
            a.update(route='leaf_with_historical_grant', grants=[dict(actor=actor, config=config, count=1,
                session='20261119-010000', grant_count_line=20)])
        identity = dict(characters=characters, sources=sources)
        key = hashlib.sha256(canonical(identity)).hexdigest()[:20]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for name in pages.SOURCES:
                target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((pages.ROOT / name).read_bytes())
            (root / bundle.OUTPUT / key).mkdir(parents=True)
            page_root = root / 'runtime/boss-skill-pages/fixture'
            rows, _ = pages.write_pages(characters, {}, sources, page_root, root)
            pool = root / rows[0]['directory']
            with patch.object(bundle, 'inputs', return_value=(identity,)), \
                 patch.object(bundle, 'candidate_ids', return_value=('fixture',)), \
                 patch.object(pages, 'inputs', return_value=(identity, {}, sources, 'fixture')):
                self.assertEqual(bundle.historical_pool('fixture', pool, root)['definition']['id'], 'fixture')
                module = pool / 'boss_candidate.lua'; original = module.read_bytes()
                module.write_bytes(original + b'-- changed')
                with self.assertRaises(AssertionError): bundle.historical_pool('fixture', pool, root)
                self.assertEqual(module.read_bytes(), original + b'-- changed')


if __name__ == '__main__':
    unittest.main()
