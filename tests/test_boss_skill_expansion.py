import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import boss_skill_expansion as expansion
from boss_adaptation_workflow import ROOT

class SkillExpansionTests(unittest.TestCase):
    def test_three_independent_bosses_have_four_new_observed_native_actions(self):
        for row in expansion.read(ROOT/expansion.QUEUE)['bosses']:
            value,projection=expansion.definition(row['id'])
            self.assertEqual(len(set(value['ability_pool'])),4)
            self.assertTrue(all(a['historical_native_grant_observed'] for a in projection['actions']))
            self.assertTrue(all(not a['current_leaf_verified'] and not a['activation_verified'] and not a['playable'] for a in projection['actions']))

    def altered_queue(self,change):
        original=expansion.read;queue=copy.deepcopy(original(ROOT/expansion.QUEUE));change(queue['bosses'][0])
        return patch.object(expansion,'read',side_effect=lambda p:queue if Path(p)==ROOT/expansion.QUEUE else original(p))

    def test_unknown_expansion_is_rejected(self):
        with self.assertRaises(AssertionError):expansion.definition('other')

    def test_previously_accepted_action_is_not_relabelled_as_new(self):
        with self.altered_queue(lambda row:row['actions'][0].update(class_short='GA_WanJun_HeavyAttack_01_C')):
            with self.assertRaises(AssertionError):expansion.definition('057_wanjun')

    def test_guessed_or_other_boss_class_cannot_be_bound(self):
        for short in ['GA_NotObserved_C','GA_YouLong_HeavyAttack_02_C']:
            with self.altered_queue(lambda row:row['actions'][0].update(class_short=short)):
                with self.assertRaises(AssertionError):expansion.definition('057_wanjun')

    def test_scene_dependent_action_is_blocked_even_if_its_name_is_known(self):
        with self.altered_queue(lambda row:row['actions'][0].update(class_short='GA_YanQianSui_Skill_01_C')):
            with self.assertRaises(AssertionError):expansion.definition('057_wanjun')

    def test_duplicate_actions_and_keys_are_rejected(self):
        for change in [lambda r:r['actions'][1].update(key=r['actions'][0]['key']),
                       lambda r:r['actions'][1].update(id=r['actions'][0]['id']),
                       lambda r:r['actions'][1].update(class_short=r['actions'][0]['class_short'])]:
            with self.altered_queue(change):
                with self.assertRaises(AssertionError):expansion.definition('057_wanjun')

    def test_control_keys_cannot_be_used_as_extra_action_keys(self):
        with self.altered_queue(lambda row:row['actions'][0].update(key='F6')):
            with self.assertRaises(AssertionError):expansion.definition('057_wanjun')

    def test_bundle_is_reproducible_and_remains_developer_only(self):
        for identifier in ['057_wanjun','073_yanqiansui','056_youlong']:
            first=expansion.build(identifier);self.assertEqual(first,expansion.build(identifier))
            data=expansion.read(first/'manifest.json');grant=expansion.validate(identifier,first)
            self.assertFalse(data['playable']);self.assertFalse(data['auto_deploy'])
            self.assertEqual(grant['boss_candidate'],identifier)

    def test_character_scopes_do_not_share_native_action_paths(self):
        pools=[set(expansion.definition(id)[0]['ability_pool']) for id in ['057_wanjun','073_yanqiansui','056_youlong']]
        self.assertFalse(pools[0]&pools[1] or pools[1]&pools[2] or pools[0]&pools[2])

    def test_projection_digest_does_not_claim_current_native_grants(self):
        value,projection=expansion.definition('056_youlong')
        self.assertEqual(value['ability_metadata_receipt_sha256'],expansion.digest(json.dumps(projection,sort_keys=True).encode()))
        self.assertFalse(projection['current_live_grants_verified'])

if __name__=='__main__':unittest.main()
