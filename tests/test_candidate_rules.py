"""用途：证明筛选不再误收近似名称和玩家相机；使用假路径，不访问游戏。"""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pbz_candidate_rules import bride_name_match, npc_lineage, useful_character_class


class CandidateRulesTests(unittest.TestCase):
    def test_explicit_tokens(self):
        for path in ('BP_Ahua_SliderFlower_001', '/Mobs/AHua/BP_Monster_Ahua_C',
                     'ActorC_A_Hua.ActorC_A_Hua', '/Boss/Bride.Skill', '\u65b0\u5a18\u963f\u82b1'):
            with self.subTest(path=path): self.assertTrue(bride_name_match(path))

    def test_unrelated_substrings(self):
        for path in ('BP_Dahua_C', '/Guahua/Camera', '/aba321ahua64/Material'):
            with self.subTest(path=path): self.assertFalse(bride_name_match(path))

    def test_true_npc_ancestry(self):
        chain = ['/Game/Unknown.BP_Opaque_C', '/Script/ProjectPBZ.PBZCharacter_NPC', '/Script/Engine.Character']
        self.assertTrue(npc_lineage(chain))
        self.assertTrue(useful_character_class(chain[0], chain))

    def test_character_assets_before_camera_and_abilities(self):
        self.assertTrue(useful_character_class('/PBZCombatAsset/ActorData/Mobs/Luanshi/BP_Monster_LuanShi.BP_Monster_LuanShi_C', []))
        for path in ('/ActorData/Player/BP_Camera_C', '/ActorData/Mobs/Luanshi/GA_Attack.GA_Attack_C'):
            with self.subTest(path=path): self.assertFalse(useful_character_class(path, []))


if __name__ == '__main__': unittest.main()
