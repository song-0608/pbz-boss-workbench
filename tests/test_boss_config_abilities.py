import sqlite3
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from boss_config_abilities import (STRATEGY_EVIDENCE_KEY, selector_rows, strategy_tree,
                                  subtree_assignment_sites, verify_strategy_evidence)


class StrategyTreeTests(unittest.TestCase):
    def test_collects_tactic_selector_and_soft_class_without_mutating_frozen_tree(self):
        ability = '/Game/Skills/GA_Example.GA_Example_C'
        issue = 'unserialized_task_ability'
        tree = dict(issues=[issue], nodes=[
            dict(type='BTTask_ActivateAbility', branch=[0], ability_resolution=issue, properties={
                'AbilityActivationMethod': 'EAIAbilityActivationMethod::ByTactic',
                'TacticActionTagRequirements': {'RequireTags': ['Ability.Test']},
                'IsOptionalTactic': True,
            }),
            dict(type='BTTask_ActivateAbility', branch=[1], ability_resolution=issue, properties={
                'AbilityActivationMethod': 'EAIAbilityActivationMethod::BySoftClass',
                'SoftAbilityToActivate': {'AssetPathName': ability, 'SubPathString': ''},
            }),
        ])
        result = strategy_tree(Mock(), tree, {})
        tactic, soft = result['nodes']
        self.assertEqual(tactic['selector'], dict(mode='tactic', requirements={'RequireTags': ['Ability.Test']},
                                                 optional=True))
        self.assertNotIn('ability', tactic)
        self.assertEqual(soft['ability'], ability)
        self.assertEqual(soft['ability_resolution'], 'soft_class')
        self.assertEqual(result['issues'], [])
        self.assertEqual(tree['issues'], [issue])
        self.assertNotIn('ability', tree['nodes'][1])

    def test_preserves_missing_ability_and_keeps_injection_distinct_from_default(self):
        default = dict(ObjectName="BehaviorTree'BT_Default'", ObjectPath='/Game/BT_Default.0')
        injected = dict(ObjectName="BehaviorTree'BT_Injected'", ObjectPath='/Game/BT_Injected.1')
        tag = 'AI.DynamicSubtree.Attack'
        issues = ['dynamic_subtree_selection', 'unserialized_task_ability']
        tree = dict(issues=issues, nodes=[
            dict(type='BTTask_RunBehaviorDynamic', branch=[], decorators=[], properties={
                'DefaultBehaviorAsset': default, 'InjectionTag': {'TagName': tag},
            }),
            dict(type='BTTask_ActivateAbility', branch=[1], ability_resolution=issues[1], properties={}),
        ])
        capture = Mock()
        result = strategy_tree(capture, tree, {tag: injected})
        self.assertEqual(result['issues'], issues)
        selector = result['nodes'][0]
        self.assertEqual(selector['subtree'], ('/Game/BT_Default', 0, 'BehaviorTree', 'BT_Default'))
        self.assertEqual(selector['selector'], dict(mode='dynamic_subtree', injection_tag=tag,
                                                   default=default, configured=injected))
        self.assertEqual(capture.exact.call_count, 2)

    def test_records_exact_tag_assigners_and_requires_sequence_order(self):
        tag = 'AI.DynamicSubtree.DodgeBack'
        node = dict(branch=[2, 1], decorators=[
            dict(type='BTDecorator_SetDynamicSubtree_C', name='Assign', properties={'SubtreesToAssign': [tag]}),
            dict(type='BTDecorator_SetDynamicSubtree_C', name='Other', properties={'SubtreesToAssign': ['Other']}),
        ])
        predecessor = dict(type='BTTask_SetDynamicSubtree_C', export_index=47, branch=[2, 0],
                           properties={'SubtreesToAssign': [tag]})
        branches = {(2,): dict(type='BTComposite_Sequence'), (2, 0): predecessor}
        sites = subtree_assignment_sites(node, branches, tag)
        self.assertEqual(sites, [dict(kind='decorator', name='Assign', branch=[2, 1]),
                                 dict(kind='preceding_sequence_task', export_index=47, branch=[2, 0])])
        branches[(2,)]['type'] = 'BTComposite_Selector'
        self.assertEqual(subtree_assignment_sites(node, branches, tag), sites[:1])

    def test_verify_rejects_selector_changes_with_the_same_row_counts(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.executescript('''
            CREATE TABLE metadata (key, value);
            CREATE TABLE boss_combat_config_index (config_path, folder, ai_config, diagnostics);
            CREATE TABLE boss_config_strategy_selectors (config_path, tree_path, export_index, source_sha256, mode, payload);
            INSERT INTO boss_combat_config_index VALUES ('Config', 'Boss', 'AI', '[]');
        ''')
        db.execute('INSERT INTO metadata VALUES (?, ?)', (STRATEGY_EVIDENCE_KEY, '1'))
        selector = dict(mode='dynamic_subtree', injection_tag='AI.Tag', strategy_path='Strategy')
        selectors = [('Tree', 1, 'sha', dict(selector=selector))]
        db.executemany('INSERT INTO boss_config_strategy_selectors VALUES (?, ?, ?, ?, ?, ?)',
                       selector_rows('Config', selectors))
        with patch('boss_config_abilities.database_capture'), patch('boss_config_abilities.configuration_sources',
                return_value=[('Config', 'Boss', ([], [], 'AI', selectors))]):
            self.assertTrue(verify_strategy_evidence(db))
            db.execute("UPDATE boss_config_strategy_selectors SET source_sha256='other'")
            with self.assertRaisesRegex(ValueError, 'differ from the captured configuration'):
                verify_strategy_evidence(db)


if __name__ == '__main__':
    unittest.main()
