from pathlib import Path
from copy import deepcopy
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from prepare_complex_boss_configuration import PREFIX, ability_pools, candidate_slots, strategies
from prepare_complex_boss_candidates import SLOTS, definitions


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.move = PREFIX + '050_LeiDang_P2/Moves/GA_Test.GA_Test_C'
        self.shared = PREFIX + '047_LeiDang/Moves/GA_Shared.GA_Shared_C'
        self.other = PREFIX + '050_LeiDang_P2/Moves/GA_Context.GA_Context_C'
        self.skills = {
            path: (dict(timeline_available=True, declared_actions=11),
                   dict(native_metadata='verified', native_kind=kind))
            for path, kind in ((self.move, 'leaf'), (self.shared, 'leaf'), (self.other, 'subtree'))
        }

    def test_moves_must_be_owned_by_linked_tactic_or_tree_and_have_leaf_evidence(self):
        pools = [dict(path='/Assets/Pool.Pool', tactics=[dict(class_path=self.move), dict(class_path=self.other)])]
        trees = [dict(path='/Assets/Tree.Tree', nodes=[dict(ability=self.shared)])]
        slots, blocked = candidate_slots(
            ('GA_Test_C', 'GA_Shared_C', 'GA_Context_C', 'GENERIC_C'), pools, trees, self.skills, '050_LeiDang_P2')
        self.assertEqual([(x['key'], x['declared_by'], x['shared']) for x in slots],
                         [('F1', '/Assets/Pool.Pool', False), ('F2', '/Assets/Tree.Tree', True)])
        self.assertEqual([x['reason'] for x in blocked],
                         ['leaf_or_timeline_evidence_missing', 'exact_tactic_missing_or_ambiguous'])
        self.assertTrue(all(x['requires_native_grant'] and not x['binding_verified'] for x in slots))

    def test_same_short_name_in_two_linked_assets_is_ambiguous(self):
        duplicate = self.shared.replace('GA_Shared', 'GA_Test')
        skills = dict(self.skills)
        skills[duplicate] = skills[self.move]
        pools = [dict(path='/Assets/Pool.Pool', tactics=[dict(class_path=p) for p in (self.move, duplicate)])]
        self.assertEqual(candidate_slots(('GA_Test_C',), pools, [], skills, '050_LeiDang_P2')[0], [])

    def test_nested_pools_preserve_context_and_report_cycles(self):
        parent = dict(Package='/Game/Parent', Name='Parent', Type='SGameAIAbilityPool',
            Properties=dict(TacticActions=[], SubAbilityPools=['child']))
        child = dict(Package='/Game/Child', Name='Child', Type='SGameAIAbilityPool',
            Properties=dict(SubAbilityPools=['root'], TacticActions=[
                dict(Ability=dict(AssetPathName=self.move), Tags=['Phase.P2'], Conditions=['condition'])]))
        class Capture:
            def resolve(self, ref):
                return {'root': parent, 'child': child}[ref]
        pools, issues = ability_pools(Capture(), parent)
        self.assertEqual(pools[0]['subpools'], ['/Game/Child.Child'])
        self.assertEqual(pools[1]['tactics'][0]['conditions'], ['condition'])
        self.assertEqual(issues, [dict(pool='/Game/Parent.Parent', reason='subpool_cycle_or_depth_limit')])

    def test_strategy_follows_nested_trees_and_keeps_exact_leaf_links(self):
        ref = dict(ObjectName="BehaviorTree'Tree'", ObjectPath='/Game/Tree.0')
        child_ref = ('/Game/Nested', 1, 'BehaviorTree', 'Nested')
        root_ref = ('/Game/Tree', 0, 'BehaviorTree', 'Tree')
        trees = {
            root_ref: dict(path='/Game/Tree.Tree', nodes=[dict(subtree=child_ref)]),
            child_ref: dict(path='/Game/Nested.Nested', nodes=[dict(ability=self.move), dict(subtree=root_ref)]),
        }
        found, issues = strategies(dict(Properties=dict(BehaviorDefinition=[{'BehaviorTree': ref}])), trees.__getitem__)
        self.assertEqual([row['path'] for row in found], ['/Game/Tree.Tree', '/Game/Nested.Nested'])
        self.assertEqual(issues[0]['reason'], 'strategy_tree_cycle_or_depth_limit')


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.actor = PREFIX + '076_ZuoShang_P2/Actor.Actor_C'
        self.config = PREFIX + '076_ZuoShang_P2/Config.Config'
        self.identifier = '076_zuoshang_p2'
        slots = []
        for index, key in enumerate(SLOTS, 1):
            folder = '054_ZuoShang' if index == 4 else '076_ZuoShang_P2'
            name = f'GA_ZuoShang_Attack_0{index}'
            slots.append(dict(key=key, class_path=f'{PREFIX}{folder}/Moves/{name}.{name}_C',
                requires_native_grant=True, declared_by='/Asset/BT.BT', shared=index == 4))
        jobs = [dict(key=str(index)) for index in range(5)]
        self.profiles = [dict(id=self.identifier, class_path=self.actor, config_path=self.config,
            metadata_jobs=jobs, direct_controls=slots), dict(id='888_ultimateboss', class_path=None,
            config_path='/Test/Ultimate.Config', metadata_jobs=[])]
        body = dict(key='0', role='character', id=self.identifier, class_path=self.actor,
            metadata_verified=True, observed_config=self.config, config_in_observed_candidates=True,
            lineage=[self.actor, '/Script/Engine.Character'], display_name='左殇')
        self.receipt = dict(jobs=jobs, outcomes=[body, *(dict(key=str(i), id=self.identifier, role='ability',
            class_path=slot['class_path'], metadata_verified=True, ability_kind='leaf')
            for i, slot in enumerate(slots, 1))], directory='runtime/probe', session='20261122-000000')

    def test_exact_phase_config_and_shared_move_keep_fixed_order(self):
        entries, deferred = definitions(self.profiles, self.receipt)
        entry, = entries
        self.assertEqual([row['skill'] for row in entry['bindings']], list(SLOTS.values()))
        self.assertTrue(entry['bindings'][-1]['shared'])
        self.assertTrue(entry['definition']['require_complete_pool'])
        self.assertFalse(entry['playable'])
        self.assertEqual(deferred, [dict(id='888_ultimateboss', reason='combat_body_identity_unresolved')])

    def test_slot_rejection_never_shifts_later_bindings(self):
        receipt = deepcopy(self.receipt)
        receipt['outcomes'][2]['ability_kind'] = 'subtree'
        entries, deferred = definitions(self.profiles, receipt)
        self.assertEqual(entries, [])
        self.assertEqual(deferred[0]['key'], 'F2')

    def test_reused_alternate_phase_cdo_is_rejected(self):
        receipt = deepcopy(self.receipt)
        receipt['outcomes'][0]['observed_config'] = self.config.replace('_P2', '')
        entries, deferred = definitions(self.profiles, receipt)
        self.assertEqual(entries, [])
        self.assertEqual(deferred[0]['reason'], 'exact_native_character_metadata_unverified')


if __name__ == '__main__':
    unittest.main()
