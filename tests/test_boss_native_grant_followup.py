from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from boss_native_grant_followup import observations, expected


class FollowupTests(unittest.TestCase):
    def raw(self):
        return ('PBZ_CONTROL_LIFECYCLE:CANDIDATE_IDENTITY_READY=071_xianzhe|'
                '/PBZCombatAsset/ActorData/Mobs/071_XianZhe/BP.BP_C|'
                '/PBZCombatAsset/ActorData/Mobs/071_XianZhe/C.C\n'
                'PBZ_CONTROL_LIFECYCLE:GRANTED_ABILITY=Class /Game/A.A_C\n')

    def test_actual_closed_grants_create_only_four_metadata_jobs(self):
        record, script = expected()
        self.assertEqual(len(record['jobs']), 4)
        self.assertFalse(record['playable'])
        self.assertFalse(record['ability_activation_allowed'])
        self.assertTrue(all(not j['activation_allowed'] and not j['current_leaf_verified'] for j in record['jobs']))
        self.assertNotIn(b'GiveAbility', script)
        self.assertNotIn(b'TryActivate', script)
        self.assertEqual({r['id'] for r in record['roles']}, {'071_xianzhe', '067_motian'})

    def test_grants_cannot_cross_assembly_or_binding_boundary(self):
        for boundary in ('SPAWN_ATTEMPT=2', 'CANDIDATE_LIVE_BINDING=x', 'ISSUE_READY=failed'):
            raw = self.raw() + 'PBZ_CONTROL_LIFECYCLE:' + boundary + '\n'
            raw += 'PBZ_CONTROL_LIFECYCLE:GRANTED_ABILITY=Class /Game/Foreign.Foreign_C\n'
            self.assertEqual(observations(raw, '071_xianzhe', '071_XianZhe')[2], ['/Game/A.A_C'])

    def test_ambiguous_identity_or_duplicate_grants_rejected(self):
        for raw in (self.raw() * 2, self.raw() + 'PBZ_CONTROL_LIFECYCLE:GRANTED_ABILITY=Class /Game/A.A_C\n',
                    self.raw().replace('071_XianZhe/BP', '067_MoTian/BP')):
            with self.assertRaises(AssertionError):
                observations(raw, '071_xianzhe', '071_XianZhe')


if __name__ == '__main__': unittest.main()
