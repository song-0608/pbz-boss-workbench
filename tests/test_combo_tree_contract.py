"""用途：验证诊断导出完整性和资产边界；不依赖游戏进程。"""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from inspect_ahua_combo_tree import parse_contract, TREE, PREFIX

START = PREFIX + 'CLASS=BlueprintGeneratedClass /PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/New/GA_AHua_Attack_01.GA_AHua_Attack_01_C\n'
NODE = 'BTTask_ActivateAbility ' + TREE + ':Task_0'
LEAF = '/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/New/GA_AHua_Skill_08.GA_AHua_Skill_08_C'
VALID = START + PREFIX + 'COMBO_TREE=BehaviorTree ' + TREE + '|weight=100.0\n' + PREFIX + 'TREE_NODE=' + NODE + '\n' + PREFIX + 'NODE_REF=' + NODE + '|AbilityToActivate|LegoAbilityBlueprintGeneratedClass ' + LEAF + '\n' + PREFIX + 'READY=classes only; no ability activation\n'


class ContractTests(unittest.TestCase):
    def test_valid_references_do_not_claim_execution(self):
        result = parse_contract(VALID)
        self.assertEqual(result['leaf_abilities'], [LEAF])
        self.assertFalse(result['execution_order_proven'])

    def test_incomplete_latest_block_cannot_reuse_prior_success(self):
        with self.assertRaises(ValueError):
            parse_contract(VALID + START)

    def test_foreign_node_rejected(self):
        with self.assertRaises(ValueError):
            parse_contract(VALID.replace(NODE, 'BTTask /Other.Other:Task_0'))

    def test_foreign_leaf_rejected(self):
        with self.assertRaises(ValueError):
            parse_contract(VALID.replace(LEAF, '/Other.Other_C'))


if __name__ == '__main__':
    unittest.main()
