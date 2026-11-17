import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import collect_boss_skill_campaign as campaign


class SkillCampaignTests(unittest.TestCase):
    def receipt(self, session, ids):
        return dict(session=session, target_build_sha256=campaign.BUILD,
            formal_postcheck_passed=True, bosses=[dict(id=identifier, all_four_accepted=True,
                accepted_skills=dict.fromkeys(('a', 'b', 'c', 'd'), {}), actions=[{}] * 8,
                owned_cleanup_and_restoration_verified=True, stability=dict(passed=True),
                movement_camera=dict(movement_verified=True, camera_rotation_verified=True))
                for identifier in ids])

    def test_combines_only_whole_closed_assemblies(self):
        first=self.receipt('20261117-140425', ['057_wanjun', '073_yanqiansui'])
        second=self.receipt('20261117-150000', ['056_youlong'])
        before=copy.deepcopy([first,second])
        rows=campaign.combine([first,second])
        self.assertEqual({r['id'] for r in rows}, campaign.EXPECTED)
        self.assertEqual([first,second],before)
        self.assertTrue(all(r['session'] in r['evidence'] for r in rows))

    def test_incomplete_assembly_cannot_contribute_actions(self):
        receipt=self.receipt('20261117-140425', ['057_wanjun'])
        receipt['bosses'][0]['all_four_accepted']=False
        self.assertEqual(campaign.combine([receipt]),[])

    def test_duplicate_accepted_boss_rejected(self):
        first=self.receipt('20261117-140425', ['057_wanjun'])
        second=self.receipt('20261117-150000', ['057_wanjun'])
        with self.assertRaisesRegex(AssertionError,'Duplicate'):
            campaign.combine([first,second])

    def test_wrong_build_or_open_session_rejected(self):
        for field,value in [('target_build_sha256','wrong'),('formal_postcheck_passed',False)]:
            receipt=self.receipt('20261117-140425',['057_wanjun']);receipt[field]=value
            with self.subTest(field=field),self.assertRaises(AssertionError):
                campaign.combine([receipt])

    def test_inconsistent_claim_rejected(self):
        for field,value in [('actions',[{}]*7),('stability',dict(passed=False)),
                            ('owned_cleanup_and_restoration_verified',False)]:
            receipt=self.receipt('20261117-140425',['057_wanjun'])
            receipt['bosses'][0][field]=value
            with self.subTest(field=field),self.assertRaises(AssertionError):
                campaign.combine([receipt])


if __name__ == '__main__':unittest.main()
