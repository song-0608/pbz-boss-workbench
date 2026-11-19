from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

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

    def dependency_report(self):
        paths=[PREFIX+f'GA_WanJun_Test_{i}.GA_WanJun_Test_{i}_C' for i in range(2)]
        return dict(schema=1,kind='offline_native_dependency_scan',declaration_contents_verified=True,
            root_packages=1,extracted_roots=1,pending_roots=0,pending_dependency_count=0,
            ability_classes=2,failed_dependency_count=1,unindexed_references=['/Other/Missing'],
            unresolved_script_functions=0,ability_indexing_issues=1,
            timeline_inheritance_resolution={'inherited_declared':1,'own_declared':1},
            packages=[dict(folder='057_WanJun',declaration='raw.json',declaration_sha256='a'*64,
                abilities=[dict(class_path=paths[0],issues=[],declared_timelines=0,
                    timeline_resolution='inherited_declared',effective_timeline_class='/Game/GA_Base.GA_Base_C',
                    effective_declared_actions=7),
                    dict(class_path=paths[1],issues=['original null action'],declared_timelines=1)])])

    def workflow_files(self,root):
        scan=root/'scan-0001.json'
        scan.write_text(json.dumps(self.dependency_report()),encoding='utf-8')
        digest=hashlib.sha256(scan.read_bytes()).hexdigest()
        record=dict(schema=1,kind='offline_boss_dependency_workflow_result',bounded_traversal_completed=True,
            status='converged_with_known_gaps',game_started=False,computer_use_used=False,
            installed=False,live_grant_verified=False,execution_verified=False,all_boss_skills_complete=False,
            ready_for_final_delivery=False,final_scan=str(scan),final_scan_sha256=digest,
            rounds=[dict(scan=scan.name,scan_sha256=digest,terminal=True,
                pending_dependencies=0,new_script_packages=0)])
        result=root/'result.json'
        result.write_text(json.dumps(record),encoding='utf-8')
        return result,scan,record

    def test_dependency_queue_keeps_inheritance_and_quarantines_original_issues(self):
        report=self.dependency_report()
        result=coverage.dependency_coverage(report,{'characters':[]})
        self.assertEqual((result['source_ability_classes'],result['skills'],result['quarantined_skills']),(2,1,1))
        self.assertEqual(result['rows'][0]['effective_declared_actions'],7)
        self.assertEqual(result['quarantined_rows'][0]['issues'],['original null action'])
        self.assertEqual(result['capture_gaps']['failed_dependencies'],1)
        for row in result['rows']+result['quarantined_rows']:
            self.assertFalse(row['activation_allowed'])
            self.assertFalse(row['current_process_grant_verified'])
        self.assertFalse(result['ready_for_final_delivery'])
        report['ability_classes']=3
        with self.assertRaisesRegex(ValueError,'Every serialized ability'):
            coverage.dependency_coverage(report,{'characters':[]})

    def test_workflow_queue_uses_exact_final_scan_and_closed_native_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,scan,record=self.workflow_files(Path(tmp))
            with patch.object(coverage.native,'inputs',return_value=({'characters':[],'sources':{'closed':'b'*64}},)), \
                    patch.object(coverage.disk,'digest',side_effect=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                        if Path(p).is_file() else 'c'*64):
                built=coverage.build_from_workflow(result,Path(tmp))
            self.assertEqual(built['disk_dependency_scan_sha256'],record['final_scan_sha256'])
            self.assertEqual(built['closed_native_sources'],{'closed':'b'*64})
            self.assertEqual(built['capture_status'],'converged_with_known_gaps')

    def test_round_limit_and_unverified_roots_never_enter_adaptation_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,scan,record=self.workflow_files(Path(tmp))
            record['status']='round_limit_reached'
            result.write_text(json.dumps(record),encoding='utf-8')
            with patch.object(coverage.native,'inputs') as native:
                with self.assertRaisesRegex(ValueError,'completed offline dependency'):
                    coverage.build_from_workflow(result)
                native.assert_not_called()
            record['status']='converged_with_known_gaps'
            report=self.dependency_report();report['pending_roots']=1
            scan.write_text(json.dumps(report),encoding='utf-8')
            digest=hashlib.sha256(scan.read_bytes()).hexdigest()
            record['final_scan_sha256']=record['rounds'][0]['scan_sha256']=digest
            result.write_text(json.dumps(record),encoding='utf-8')
            with patch.object(coverage.native,'inputs') as native:
                with self.assertRaisesRegex(ValueError,'Verified root coverage'):
                    coverage.build_from_workflow(result)
                native.assert_not_called()

    def test_changed_terminal_scan_is_rejected_before_reading_native_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,scan,_=self.workflow_files(Path(tmp))
            scan.write_text('{}',encoding='utf-8')
            with patch.object(coverage.native,'inputs') as native:
                with self.assertRaisesRegex(ValueError,'Exact terminal'):
                    coverage.build_from_workflow(result)
                native.assert_not_called()


if __name__=='__main__':
    unittest.main()
