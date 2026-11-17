from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from expanded_boss_world import proof


class ExpandedWorldTests(unittest.TestCase):
    def fixture(self):
        text = (ROOT / 'tests/fixtures/auto-world-success.log').read_text(encoding='utf-8')
        text = text.replace('PLAYER_ENTRY_READY=ahua_guitoudao', 'PLAYER_ENTRY_READY=071_xianzhe')
        before = '/PBZCombatAsset/ActorData/Mobs/042_AHua/BP_Monster_AHua_GuiTouDao.BP_Monster_AHua_GuiTouDao_C'
        cls = '/PBZCombatAsset/ActorData/Mobs/071_XianZhe/BP_Monster_XianZhe.BP_Monster_XianZhe_C'
        text = text.replace(before, cls).replace('health_after=8750.0', 'health_after=9000.0')
        ability = '/PBZCombatAsset/ActorData/Mobs/071_XianZhe/Ability/GA_XianZhe_Dodge_B.GA_XianZhe_Dodge_B_C'
        tokens = ('KEY_SKILL_BEGIN=skill_01|class=GA_XianZhe_Dodge_B_C|active=1\n'
                  'SKILL_INSTANCE=skill_01|active=true|cancelable=true|object=GA_XianZhe_Dodge_B_C /Game/Test.Ability_1\n'
                  'KEY_SKILL_END=skill_01|')
        text = text.replace('KEY_SKILL_END=skill_01|', tokens)
        return text, cls, ability

    def test_native_movement_is_truthful_effect_without_damage_claim(self):
        text, cls, ability = self.fixture()
        result = proof(text, '071_xianzhe', cls, ability)
        self.assertTrue(result['passed'], result)
        self.assertFalse(result['skill_natural_damage'])
        self.assertTrue(result['native_primary_effect'])

    def test_requires_real_effect_and_exact_classes(self):
        text, cls, ability = self.fixture()
        for modified in (text.replace('distance=528.18391831445', 'distance=0'),
                         text.replace('distance=528.18391831445', 'distance=4000'),
                         text.replace('SKILL_INSTANCE=', 'MISSING_INSTANCE='),
                         text.replace('KEY_SKILL_BEGIN=skill_01|', 'KEY_SKILL_BEGIN=other|')):
            self.assertFalse(proof(modified, '071_xianzhe', cls, ability)['passed'])
        self.assertFalse(proof(text, '071_xianzhe', '/Foreign.Class_C', ability)['passed'])
        self.assertFalse(proof(text, '071_xianzhe', cls, '/Foreign.Ability_C')['passed'])

    def test_lifecycle_gates_cannot_be_replaced_by_motion(self):
        text, cls, ability = self.fixture()
        for token in ('CAMERA_CLEANUP_ENGINE_VERIFIED=true', 'WORLD_REASSEMBLY_AWAITING_GAMEPLAY=true',
                      'ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0'):
            self.assertFalse(proof(text.replace(token, 'REMOVED='), '071_xianzhe', cls, ability)['passed'])
        for extra in ('PBZ_REARM_RETIRE:PASS=true', 'WORKBENCH_BOSS_SELECTED=071_xianzhe'):
            self.assertFalse(proof(text + extra, '071_xianzhe', cls, ability)['passed'])
        self.assertFalse(proof(text, '067_motian', cls, ability)['passed'])


if __name__ == '__main__': unittest.main()
