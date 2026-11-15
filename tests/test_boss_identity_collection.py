import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from collect_boss_identity import analyze


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.requests=[{'id':'fixture','role':'character','lookup_path':'/Fixture.Boss_C'},
                       {'id':'fixture','role':'config','lookup_path':'/Fixture.Config'}]
        self.lines=['PBZ_MULTI_ID:START=metadata',
            'PBZ_MULTI_ID:ASSET=fixture|character|BlueprintGeneratedClass /Fixture.Boss_C',
            'PBZ_MULTI_ID:LINEAGE=fixture|0|Class /Script/ProjectPBZ.PBZCharacter_NPC',
            'PBZ_MULTI_ID:LINEAGE=fixture|1|Class /Script/CoreUObject.Object',
            'PBZ_MULTI_ID:CDO_CONFIG=fixture|PDA_ActorConfig_C /Fixture.Config',
            'PBZ_MULTI_ID:DEFAULT_CONFIG_MATCH=fixture',
            'PBZ_MULTI_ID:ASSET=fixture|config|PDA_ActorConfig_C /Fixture.Config',
            'PBZ_MULTI_ID:NAME=fixture|Fixture Boss', 'PBZ_MULTI_ID:END=done']

    def test_verified_identity_does_not_promote_control(self):
        row=analyze(self.lines,self.requests)[0]
        self.assertTrue(row['identity_verified'])
        self.assertFalse(row['playable']);self.assertFalse(row['control_verified'])

    def test_mismatched_default_is_blocked(self):
        lines=[s.replace('CDO_CONFIG=fixture|PDA_ActorConfig_C /Fixture.Config',
                         'CDO_CONFIG=fixture|PDA_ActorConfig_C /Other.Config') for s in self.lines]
        self.assertFalse(analyze(lines,self.requests)[0]['identity_verified'])

    def test_incomplete_or_rejected_does_not_pass(self):
        with self.assertRaises(AssertionError):analyze(self.lines[:-1],self.requests)
        lines=self.lines[:-1]+['PBZ_MULTI_ID:REJECTED=fixture|character|changed',self.lines[-1]]
        self.assertFalse(analyze(lines,self.requests)[0]['identity_verified'])
        self.assertFalse(analyze(self.lines+self.lines[1:2],self.requests)[0]['identity_verified'])


if __name__=='__main__':unittest.main()
