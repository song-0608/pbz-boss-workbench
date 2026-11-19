import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from boss_combo_dependencies import declarations, plan, resolve

BASE = '/PBZCombatAsset/ActorData/Mobs/Fixture/'
PARENT = BASE + 'Ability/GA_Combo.GA_Combo_C'
NESTED = BASE + 'Ability/GA_Nested.GA_Nested_C'
LEAF = BASE + 'Ability/GA_Fixture_Attack_01.GA_Fixture_Attack_01_C'
ACTOR = BASE + 'BP_Fixture.BP_Fixture_C'
CONFIG = BASE + 'ActorC_Fixture.ActorC_Fixture'


def ability(path, kind):
    return dict(path=path, metadata='verified', kind=kind, grants=[])


def graph(*paths):
    return dict(trees=[dict(path=BASE + 'Tree.Tree', weight=100,
                           references=list(paths))], origins=[])


def fixture():
    parent = ability(PARENT, 'subtree')
    parent['grants'] = [dict(actor=ACTOR, config=CONFIG, count=1,
                            session='20261119-010000', grant_count_line=20)]
    character = dict(id='fixture', folder='Fixture', abilities=[parent, ability(LEAF, 'leaf')],
        variants=[dict(path=ACTOR, metadata='verified', receipts=['identity'],
            observation=dict(observed_config=CONFIG,
                lineage=[ACTOR, '/Script/ProjectPBZ.PBZCharacter_NPC', '/Script/Engine.Character']))])
    row = dict(key='key', parent_class=PARENT, mapping_observed=True,
        native_grant_verified=False, activation_verified=False, trees=[dict(path=BASE + 'Tree.Tree',
            weight=100, references=[dict(property='AbilityToActivate', value='Class ' + LEAF)])])
    audit = dict(session='20261119-010000', metadata_only=True, playable=False, outcomes=[row])
    return character, audit


class ComboDependencyTests(unittest.TestCase):
    def test_nested_subtrees_resolve_to_exact_leaves_without_inventing_execution_order(self):
        a = {p: ability(p, k) for p, k in ((PARENT, 'subtree'), (NESTED, 'subtree'), (LEAF, 'leaf'))}
        result = resolve(PARENT, a, {PARENT: graph(NESTED), NESTED: graph(LEAF)})
        self.assertTrue(result['declaration_closure_complete'])
        self.assertEqual(result['leaf_classes'], [LEAF])
        self.assertEqual(set(result['subtree_classes']), {PARENT, NESTED})

    def test_cycles_missing_graphs_and_foreign_or_untyped_refs_stay_unresolved(self):
        a = {PARENT: ability(PARENT, 'subtree'), NESTED: ability(NESTED, 'subtree')}
        foreign = LEAF.replace('/Fixture/', '/Other/')
        for graphs, reason in (({PARENT: graph(PARENT)}, 'cycle'),
                ({PARENT: graph(NESTED)}, 'missing_closed_graph'),
                ({PARENT: graph(LEAF)}, 'unverified_type'),
                ({PARENT: graph(foreign)}, 'foreign_character'),
                ({PARENT: graph()}, 'no_declared_ability_reference')):
            with self.subTest(reason=reason):
                result = resolve(PARENT, a, graphs)
                self.assertFalse(result['declaration_closure_complete'])
                self.assertEqual(result['issues'][0]['reason'], reason)

    def test_closed_parent_grants_do_not_create_child_grants_or_activation_permission(self):
        character, audit = fixture()
        row, = plan([character], [audit])
        self.assertTrue(row['declaration_closure_complete'])
        self.assertEqual(row['exact_parent_variants'][0]['actor'], ACTOR)
        self.assertFalse(row['activation_allowed'] or row['playable'] or row['execution_order_proven'])
        self.assertFalse(character['abilities'][1]['grants'])

    def test_actor_config_lineage_and_duplicate_grants_cannot_be_borrowed(self):
        for mutate in (lambda c: c['abilities'][0]['grants'][0].update(count=2),
                lambda c: c['variants'][0]['observation'].update(observed_config=CONFIG + 'Other'),
                lambda c: c['variants'][0]['observation'].update(lineage=[]),
                lambda c: c['variants'][0].update(metadata='conflict'),
                lambda c: c['variants'][0].update(receipts=[])):
            character, audit = fixture(); mutate(character)
            self.assertFalse(plan([character], [audit])[0]['exact_parent_variants'])

    def test_rejected_or_conflicting_maps_cannot_form_one_combo(self):
        _, audit = fixture()
        rejected = copy.deepcopy(audit)
        rejected['outcomes'][0].update(mapping_observed=False, trees=[])
        self.assertEqual(declarations([rejected]), {})
        rejected['outcomes'][0]['trees'] = audit['outcomes'][0]['trees']
        with self.assertRaises(AssertionError): declarations([rejected])
        other = copy.deepcopy(audit)
        other['outcomes'][0]['trees'][0]['weight'] = 200
        with self.assertRaises(AssertionError): declarations([audit, other])
        other = copy.deepcopy(audit)
        other['outcomes'][0]['trees'][0]['edges'] = ['different topology']
        with self.assertRaises(AssertionError): declarations([audit, other])

    def test_observed_empty_native_map_is_retained_without_inventing_a_tree(self):
        character, audit = fixture()
        audit['outcomes'][0]['trees'] = []
        row, = plan([character], [audit])
        self.assertFalse(row['trees'] or row['declaration_closure_complete'])
        self.assertEqual(row['issues'], [dict(reason='no_declared_ability_reference', path=PARENT)])

    def test_parent_grants_need_an_exact_closed_snapshot_identity(self):
        for field, value in (('session', 'other'), ('grant_count_line', 0), ('grant_count_line', True)):
            character, audit = fixture()
            character['abilities'][0]['grants'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(AssertionError):
                plan([character], [audit])

    def test_context_children_remain_marked_for_review_within_a_complete_graph(self):
        character, audit = fixture()
        child = LEAF.replace('Attack_01', 'CA_01_GEx')
        character['abilities'][1]['path'] = child
        audit['outcomes'][0]['trees'][0]['references'][0]['value'] = 'Class ' + child
        row, = plan([character], [audit])
        self.assertTrue(row['declaration_closure_complete'])
        self.assertEqual(row['context_review'][0]['path'], child)
        self.assertFalse(row['activation_allowed'])

    def test_shared_global_utilities_do_not_merge_character_skill_inventories(self):
        character, audit = fixture()
        global_path = '/SGameLocomotionDriver/Drivers/GA_Utility.GA_Utility_C'
        character['abilities'].append(ability(global_path, 'leaf'))
        other = dict(id='other', folder='Other', variants=[],
                     abilities=[ability(global_path, 'leaf')])
        row, = plan([character, other], [audit])
        self.assertEqual(row['leaf_classes'], [LEAF])
        audit['outcomes'][0]['trees'][0]['references'][0]['value'] = 'Class ' + global_path
        self.assertEqual(plan([character, other], [audit])[0]['issues'][0]['reason'], 'foreign_character')


if __name__ == '__main__':
    unittest.main()
