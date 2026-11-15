from pathlib import Path
import sys
import unittest
import json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from collect_performance_comparison import compare,summarize,windows
from collect_performance_hotfix import active_duration


class PerformanceTests(unittest.TestCase):
    def test_endurance_rejects_heartbeat_gaps_and_off_intervals(self):
        def log(at,state='ACTIVE'):
            return 'PBZ_PLAYER_UI:STATUS='+json.dumps({'at':at,'text':'新娘阿花 | '+state+'\n'})+'\n'
        self.assertEqual(active_duration(''.join(log(i)for i in range(301))),300)
        self.assertEqual(active_duration(log(0)+log(301)),0)
        self.assertEqual(active_duration(log(0)+log(1)+log(2,'OFF')+log(3)+log(4)),1)

    def sample(self,frames=400,ms=2):
        return {'state':'ACTIVE','wall':5,'frames':frames,'callback_ms':ms,'max_ms':ms+1,'at':100,
                'costs':{'bridge.world_boundary':{'calls':frames},'bridge.context':{'calls':frames}}}

    def test_mixed_or_idle_windows_cannot_pass(self):
        for state,count in [('OFF',400),('ACTIVE',399)]:
            row=self.sample();row['state']=state;row['costs']['bridge.context']['calls']=count
            with self.assertRaises(RuntimeError):summarize([row]*3)

    def test_three_complete_windows_are_required(self):
        with self.assertRaises(RuntimeError):summarize([self.sample()]*2)
        self.assertEqual(summarize([self.sample()]*3)['game_thread_ticks_per_second'],80)

    def test_different_gameplay_source_is_rejected(self):
        before={'module_source_sha256':{'a':'1'},'assembly_source_sha256':'2','summary':summarize([self.sample(14,350)]*3)}
        after=dict(before,module_source_sha256={'a':'3'})
        with self.assertRaises(RuntimeError):compare(before,after)
        after=dict(before,summary=summarize([self.sample()]*3));self.assertTrue(compare(before,after)['passed'])
        after['summary']['game_thread_ticks_per_second']=10;self.assertFalse(compare(before,after)['passed'])

    def test_probe_parsing_does_not_merge_windows(self):
        text='PBZ_PERF:WINDOW=state=OFF|wall=5.010000|frames=400|callback_ms=0.200000|max_ms=2.000000|at=100\nPBZ_PERF:COST=find_exact|calls=10|ms=20.000000\nPBZ_PERF:WINDOW=state=ACTIVE|wall=5.020000|frames=14|callback_ms=350.000000|max_ms=400.000000|at=105\n'
        rows=windows(text);self.assertEqual(rows[0]['costs']['find_exact']['calls'],10);self.assertEqual(rows[1]['costs'],{})

    def test_other_loader_changes_cannot_borrow_cache_comparison(self):
        before={'module_source_sha256':{},'assembly_source_sha256':'a',
                'summary':summarize([self.sample(14,350)]*3),
                'loader_settings':'bUseUObjectArrayCache = false\nchecks = true\n'}
        after=dict(before,summary=summarize([self.sample()]*3),
                   loader_settings='bUseUObjectArrayCache = true\nchecks = true\n')
        self.assertTrue(compare(before,after)['passed'])
        after['loader_settings']=after['loader_settings'].replace('checks = true','checks = false')
        with self.assertRaises(RuntimeError):compare(before,after)


if __name__=='__main__':unittest.main()
