"""Review planning reuses metadata while preserving variant and live-grant gates."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import boss_adapter_registry as registry
import boss_adapter_review as review
import boss_metadata_jobs as metadata
import collect_boss_metadata_jobs as collector
import test_boss_metadata_jobs as fixtures
from boss_adaptation_workflow import ROOT, BUILD


def catalog(*candidates):
    return dict(target_build_sha256=BUILD,candidates=list(candidates))


def simulated_receipt(candidate,*,kind='leaf',config=None,reject_ability=False):
    """Pure unit fixture, never written as research evidence."""
    jobs=metadata.jobs_for(candidate)
    manifest=dict(jobs=jobs,batch_fingerprint='a'*20)
    _,lines=fixtures.MetadataTests().manifest(manifest)
    if kind!='leaf':
        lines=[line.replace('|leaf','|'+kind) for line in lines]
    if config:
        lines=[line.replace(job['config_candidates'][0],config) if job['role']=='character' else line
            for job,line in zip(jobs,lines[1:-1])]
        lines=['PBZ_ADAPTER_META:START='+'a'*20,*lines,'PBZ_ADAPTER_META:END='+'a'*20]
    if reject_ability:
        for index,job in enumerate(jobs,1):
            if job['role']=='ability':
                lines[index]='PBZ_ADAPTER_META:REJECTED='+job['key']+'|unavailable'
    return dict(target_build_sha256=BUILD,metadata_only=True,playable=False,
        control_verified=False,runtime_acceptance_current=False,outcomes=metadata.analyze(lines,manifest))


class ReviewTests(unittest.TestCase):
    def test_no_receipts_leave_all_six_real_candidates_pending(self):
        observed=json.loads((ROOT/'research/boss-adaptation/catalog.json').read_bytes())
        ids=json.loads((ROOT/registry.QUEUE).read_bytes())['candidate_ids']
        result=review.plan(observed,ids,{})
        self.assertEqual(len(result['pending_metadata_job_keys']),119)
        self.assertEqual([len(group) for group in result['retry_job_batches']],[50,54,15])
        self.assertEqual(len(result['adapters']),6);self.assertEqual(result['metadata_queries_avoided'],0)

    def test_successful_metadata_never_selects_or_unlocks_a_variant(self):
        candidate=fixtures.candidate()
        result=review.plan(catalog(candidate),['fixture'],{'unit':simulated_receipt(candidate)})
        self.assertEqual(result['pending_metadata_job_keys'],[])
        self.assertEqual(result['metadata_queries_avoided'],2)
        adapter=result['adapters'][0];self.assertIsNone(adapter['selected_variant'])
        self.assertFalse(adapter['enabled']);self.assertFalse(adapter['playable'])
        self.assertTrue(all(not value for value in adapter['capabilities'].values()))
        self.assertFalse(adapter['variants'][0]['selected']);self.assertFalse(adapter['identity_verified'])

    def test_only_rejected_ability_is_retried(self):
        candidate=fixtures.candidate()
        result=review.plan(catalog(candidate),['fixture'],{'unit':simulated_receipt(candidate,reject_ability=True)})
        self.assertEqual(result['pending_metadata_job_keys'],[metadata.jobs_for(candidate)[1]['key']])
        self.assertEqual(result['retry_job_batches'][0][0]['role'],'ability')
        self.assertEqual(result['adapters'][0]['rejected_metadata_jobs'],1)

    def test_later_rejection_does_not_discard_successful_metadata(self):
        candidate=fixtures.candidate()
        result=review.plan(catalog(candidate),['fixture'],{'earlier':simulated_receipt(candidate),
            'later':simulated_receipt(candidate,reject_ability=True)})
        self.assertEqual(result['pending_metadata_job_keys'],[])
        self.assertEqual(len(result['adapters'][0]['skills'][0]['evidence']),2)

    def test_duplicate_successful_observation_is_reused_once(self):
        candidate=fixtures.candidate();receipt=simulated_receipt(candidate)
        result=review.plan(catalog(candidate),['fixture'],{'one':receipt,'two':copy.deepcopy(receipt)})
        self.assertEqual(len(result['verified_metadata_job_keys']),2)
        self.assertEqual(result['conflicting_metadata_job_keys'],[])

    def test_conflicting_config_observations_require_review_without_silent_selection(self):
        candidate=fixtures.candidate()
        result=review.plan(catalog(candidate),['fixture'],{'one':simulated_receipt(candidate),
            'two':simulated_receipt(candidate,config='/Other/ActorC_Other.ActorC_Other')})
        variant=result['adapters'][0]['variants'][0]
        self.assertEqual(variant['status'],'conflicting_metadata');self.assertIsNone(variant['observed_config'])
        self.assertEqual(len(result['conflicting_metadata_job_keys']),1)
        self.assertEqual(result['pending_metadata_job_keys'],[])
        self.assertFalse(variant['selected'])

    def test_conflicting_skill_classification_never_becomes_a_player_skill(self):
        candidate=fixtures.candidate()
        result=review.plan(catalog(candidate),['fixture'],{'one':simulated_receipt(candidate),
            'two':simulated_receipt(candidate,kind='subtree')})
        skill=result['adapters'][0]['skills'][0]
        self.assertEqual(skill['status'],'conflicting_metadata');self.assertIsNone(skill['ability_kind'])
        self.assertIsNone(skill['player_key']);self.assertFalse(skill['granted_to_selected_actor'])

    def test_multiple_variants_remain_separate_even_when_their_config_matches(self):
        candidate=fixtures.candidate(characters=2)
        result=review.plan(catalog(candidate),['fixture'],{'unit':simulated_receipt(candidate)})
        adapter=result['adapters'][0]
        self.assertEqual(len(adapter['variants']),2)
        self.assertEqual(len({v['class_path'] for v in adapter['variants']}),2)
        self.assertTrue(all(v['status']=='awaiting_identity_review' and not v['selected'] for v in adapter['variants']))
        self.assertIsNone(adapter['selected_variant'])

    def test_actual_config_outside_catalog_is_retained_for_review_without_requery(self):
        candidate=fixtures.candidate();config='/Other/ActorC_Other.ActorC_Other'
        result=review.plan(catalog(candidate),['fixture'],{'unit':simulated_receipt(candidate,config=config)})
        variant=result['adapters'][0]['variants'][0]
        self.assertEqual(variant['status'],'config_review_required')
        self.assertEqual(variant['observed_config'],config);self.assertFalse(variant['config_in_observed_candidates'])
        self.assertEqual(result['retry_job_batches'],[])

    def test_subtree_and_child_resources_do_not_receive_keys_or_actor_ownership(self):
        candidate=fixtures.candidate();candidate['assets'][-1]['role']='ability_dependency_clue'
        result=review.plan(catalog(candidate),['fixture'],{'unit':simulated_receipt(candidate,kind='subtree')})
        skill=result['adapters'][0]['skills'][0]
        self.assertEqual(skill['ability_kind'],'subtree');self.assertEqual(skill['resource_role'],'ability_dependency_clue')
        self.assertIsNone(skill['owned_variant_class']);self.assertFalse(skill['live_grant_verified'])
        self.assertFalse(skill['activation_verified']);self.assertIsNone(skill['player_key'])

    def test_cross_candidate_or_promoted_outcome_is_rejected(self):
        candidate=fixtures.candidate();original=simulated_receipt(candidate)
        for field,value in [('id','other'),('role','ability'),('class_path','/Other.Class_C'),('playable',True)]:
            receipt=copy.deepcopy(original);receipt['outcomes'][0][field]=value
            with self.assertRaises(AssertionError):review.plan(catalog(candidate),['fixture'],{'unit':receipt})

    def test_missing_only_batches_keep_full_shared_budgets(self):
        candidates=[fixtures.candidate('c'+str(i),abilities=24) for i in range(6)]
        receipts={'unit':simulated_receipt(candidates[0])}
        result=review.plan(catalog(*candidates),[c['id'] for c in candidates],receipts)
        self.assertEqual(len(result['pending_metadata_job_keys']),125)
        self.assertTrue(all(j['id']!='c0' for group in result['retry_job_batches'] for j in group))
        self.assertTrue(all(len(group)<=64 and len({j['id'] for j in group})<=3 for group in result['retry_job_batches']))

    def test_collected_fixture_is_replayed_before_its_metadata_is_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            session,batch,_,_=fixtures.MetadataTests().collection_fixture(root)
            path=collector.collect(session,batch,root);receipt=collector.verify_receipt(path,root)
            observed=json.loads((root/'research/boss-adaptation/catalog.json').read_bytes())
            result=review.plan(observed,['fixture'],{path.relative_to(root).as_posix():receipt})
            self.assertEqual(result['pending_metadata_job_keys'],[])
            self.assertFalse(result['complete_mod'])

    def test_repository_review_build_is_reproducible_and_independently_verifiable(self):
        registry.build();path=review.build();original=path.read_bytes()
        self.assertEqual(review.build(),path);self.assertEqual(path.read_bytes(),original)
        result=review.verify(path)
        self.assertEqual(result['adapters'],6)
        self.assertEqual(result['pending_metadata_jobs']+result['verified_metadata_jobs']+result['conflicting_metadata_jobs'],119)

    def test_review_report_cannot_claim_selected_variants_or_skip_pending_jobs(self):
        registry.build();original=json.loads(review.build().read_bytes())
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.json'
            for edit in ('selection','pending','sources'):
                changed=copy.deepcopy(original)
                if edit=='selection':changed['plan']['adapters'][0]['selected_variant']='invented'
                elif edit=='pending':changed['plan']['pending_metadata_job_keys']=[]
                else:changed['receipt_files']['invented.json']='0'*64
                path.write_text(json.dumps(changed),encoding='utf-8')
                with self.assertRaises(AssertionError):review.verify(path)

    def test_invalid_receipt_inbox_blocks_planning_before_any_retry_batch_is_built(self):
        report=json.loads(registry.build().read_bytes())
        names=set(report['source_files'])|set(review.SOURCES)|{report['catalog']}
        observed=json.loads((ROOT/report['catalog']).read_bytes())
        names.update(row['path'] for row in observed['sources'])
        for batch in report['batches']:
            manifest=json.loads((ROOT/batch['directory']/'manifest.json').read_bytes())
            names.update(manifest['source_files'])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            for name in names:
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
            registry.build(root)
            inbox=root/review.RECEIPTS;inbox.mkdir(parents=True)
            (inbox/'fake.json').write_text('{"schema_version":2,"batch_fingerprint":"invented"}',encoding='utf-8')
            with self.assertRaises(AssertionError):review.build(root)
            self.assertFalse((root/'runtime/boss-reviews').exists())


if __name__=='__main__':
    unittest.main()
