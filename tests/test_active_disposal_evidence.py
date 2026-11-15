from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from collect_active_disposal import proof


class DisposalEvidenceTests(unittest.TestCase):
    text=('CONTROL_PARTICIPANT=boss|FixtureBoss /Game/Owned.Boss|address=42|class=Fixture\n'
          'SKILL_INSTANCE=skill_08|active=true|cancelable=true|object=FixtureSkill08 /Game/Owned.Skill08\n'
          'OWNED_DISPOSAL_ACTIVE_INSTANCE=skill_08|active=1|object=FixtureSkill08 /Game/Owned.Skill08\n'
          'OWNED_DISPOSAL_REQUEST=FixtureBoss /Game/Owned.Boss|address=42\n'
          'OWNED_DISPOSAL_ENGINE_UNUSABLE=true\nPBZ_CONTROL_RESTORE:OWNED_DISPOSAL_VERIFIED=true\n'
          '[PBZBossControl] auto_exit success=true state=OFF reason=owned boss disposed\n'
          'CONTROLLED_BOSS_DISPOSED=true\nORIGINAL_PLAYER_POSITION_DELTA=0.0\n'
          'ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0\nCAMERA_CLEANUP_ENGINE_VERIFIED=true\n')

    def test_exact_instance_and_actor_with_complete_restoration(self):
        result=proof(self.text)
        self.assertTrue(result['passed'])
        self.assertFalse(result['post_disposal_spec_reads_claimed'])

    def test_unrelated_ability_actor_or_old_restore_cannot_supply_proof(self):
        for text in (self.text.replace('active=1','active=0'),
                     self.text.replace('OWNED_DISPOSAL_REQUEST=FixtureBoss /Game/Owned.Boss|address=42',
                                       'OWNED_DISPOSAL_REQUEST=FixtureBoss /Game/Other.Boss|address=43'),
                     self.text.replace('object=FixtureSkill08 /Game/Owned.Skill08', 'object=Other /Game/Other.Skill',1),
                     self.text.replace('CAMERA_CLEANUP_ENGINE_VERIFIED=true','CAMERA_REMOVED'),
                     self.text+'state=FAULTED'):
            self.assertFalse(proof(text)['passed'])

    def test_native_kill_request_alone_is_not_synchronous_disposal(self):
        text=self.text.replace('OWNED_DISPOSAL_ENGINE_UNUSABLE=true','OWNED_DEATH_TRIAL_KILL_REQUESTED=true')
        self.assertFalse(proof(text)['passed'])


if __name__=='__main__':unittest.main()
