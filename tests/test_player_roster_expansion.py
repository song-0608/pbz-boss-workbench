import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import player_roster_expansion as roster


class RosterTests(unittest.TestCase):
    def test_observed_six_are_previews_and_jobs_are_bounded(self):
        result=roster.plan()
        self.assertEqual(len(result['previews']),6)
        self.assertEqual(sum(len(j) for j in result['jobs']),119)
        self.assertEqual([len(j) for j in result['jobs']],[50,54,15])
        self.assertTrue(all(not row['playable'] for row in result['previews']))
        self.assertEqual(sum(row['stage']=='variant_binding_required' for row in result['previews']),3)
        self.assertEqual(result['new_playable_bosses'],0)

    def test_jobs_do_not_grant_activate_or_spawn_actors(self):
        for jobs in roster.plan()['jobs']:
            script=roster.metadata.render(jobs,'0'*20)
            for dangerous in ('BeginDeferredActorSpawnFromClass','TryActivateAbility','GiveAbility','SetLockTarget'):
                self.assertNotIn(dangerous,script)
            self.assertLessEqual(len(jobs),64)
            self.assertLessEqual(len({j['id'] for j in jobs}),3)


if __name__=='__main__':unittest.main()
