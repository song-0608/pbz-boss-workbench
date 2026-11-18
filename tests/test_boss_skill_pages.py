import copy
from pathlib import Path
import sys
import unittest

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
            grants=[dict(actor=ACTOR, config=CONFIG, count=1, session='closed')]))
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


if __name__ == '__main__':
    unittest.main()
