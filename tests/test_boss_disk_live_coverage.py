from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import boss_disk_live_coverage as coverage

PREFIX='/PBZCombatAsset/ActorData/Mobs/057_WanJun/Ability/'


class CoverageTests(unittest.TestCase):
    def test_disk_only_moves_never_gain_native_permission(self):
        paths=[PREFIX+f'GA_WanJun_Attack_{i}.GA_WanJun_Attack_{i}_C' for i in range(3)]
        index={'packages':[dict(folder='057_WanJun',declaration='raw.json',declaration_sha256='a'*64,
            abilities=[dict(class_path=p,issues=[],timelines=[]) for p in paths])]}
        snapshot={'characters':[dict(folder='057_WanJun',abilities=[
            dict(path=paths[0],route='in_v5_profile',metadata='verified',kind='leaf',receipts=['closed'],grants=[]),
            dict(path=paths[1],route='leaf_with_historical_grant',metadata='verified',kind='leaf',receipts=['closed'],
                 grants=[dict(count=1,actor='exact actor',config='exact config')])])]}
        result=coverage.coverage(index,snapshot)
        self.assertEqual(result['skills'],3)
        self.assertEqual([r['next_action'] for r in result['rows']],
            ['keep_accepted_v5_mapping','review_exact_historical_actor_config_before_candidate',
             'review_disk_parent_and_observe_exact_native_grant'])
        self.assertEqual(result['rows'][2]['native_receipts'],[])
        self.assertTrue(all(not r['activation_allowed'] and not r['playable']
                            and not r['current_process_grant_verified'] for r in result['rows']))

    def test_foreign_native_metadata_cannot_fill_local_identity(self):
        path=PREFIX+'GA_Test.GA_Test_C'
        index={'packages':[dict(folder='057_WanJun',declaration='raw.json',declaration_sha256='a'*64,
            abilities=[dict(class_path=path,issues=[],timelines=[])])]}
        snapshot={'characters':[dict(folder='056_YouLong',abilities=[dict(path=path)])]}
        result=coverage.coverage(index,snapshot)
        self.assertEqual(result['rows'][0]['native_route'],'no_closed_native_record')

    def test_duplicate_native_or_disk_identity_rejected(self):
        path=PREFIX+'GA_Test.GA_Test_C'
        ability=dict(path=path,route='in_v5_profile',metadata='verified',kind='leaf',receipts=[],grants=[])
        snapshot={'characters':[dict(folder='057_WanJun',abilities=[ability,ability])]}
        with self.assertRaisesRegex(ValueError,'Duplicate exact native'):
            coverage.coverage({'packages':[]},snapshot)


if __name__=='__main__':
    unittest.main()
