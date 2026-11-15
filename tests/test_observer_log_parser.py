"""用途：回归热重载版本、稳定实例关联及未就绪状态，不启动游戏。"""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from observer_log_parser import parse_observation


def parse(*values):
    return parse_observation(['[Lua] PBZ_AI_OBSERVE:' + x for x in values])


class LogParserTests(unittest.TestCase):
    def test_latest_version_does_not_borrow_previous_pass(self):
        result=parse('START_V2','PLAYER=old','PLAYER_ABILITY_COLLECTED=140',
                     'START_V3','NPC_9=world.new','NPC_9_PENDING_AI=attempt=1')
        self.assertEqual(result['starts'],2)
        self.assertEqual(result['version'],3)
        self.assertEqual(result['counts'],{})
        self.assertEqual(result['per_instance']['world.new']['stages']['AI'],'pending')

    def test_ninth_npc_and_issues_link_to_instance(self):
        result=parse('START_V3','NPC_9=world.boss','ISSUE_NPC_9_AI=not ready',
                     'NPC_9_READY_AI=true','NPC_9_ABILITY_1=Ability1',
                     'NPC_9_ABILITY_COLLECTED=1','NPC_9_OBSERVED=ready')
        item=result['per_instance']['world.boss']
        self.assertEqual(item['stages']['AI'],'ready')
        self.assertEqual(len(item['issues']),1)
        self.assertEqual(result['rows'][0]['实例'],'world.boss')

    def test_exhausted_is_unresolved(self):
        result=parse('START_V3','NPC_1=world.unready','NPC_1_RETRY_EXHAUSTED_ABILITIES=unresolved')
        self.assertEqual(result['per_instance']['world.unready']['stages']['ABILITIES'],'unresolved')
        self.assertFalse(result['per_instance']['world.unready'].get('observation_recorded',False))

    def test_legacy_v2_and_unsupported_logs(self):
        self.assertEqual(parse('START_V2','PLAYER=world.hun')['version'],2)
        with self.assertRaises(ValueError): parse('START_V99')


if __name__ == '__main__': unittest.main()
