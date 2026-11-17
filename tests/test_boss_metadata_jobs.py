"""Metadata planning and closed-result collection cannot promote playable profiles."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import boss_metadata_jobs as jobs
import collect_boss_metadata_jobs as collector
from boss_adaptation_workflow import ROOT, BUILD, sha


def candidate(identifier='fixture',characters=1,abilities=1):
    prefix='/PBZCombatAsset/ActorData/Mobs/'+identifier+'/'
    assets=[dict(package=prefix+'ActorConfig/ActorC_'+identifier,role='actor_config_clue')]
    assets.extend(dict(package=prefix+'BP_Monster_'+str(i),role='character_blueprint_clue') for i in range(characters))
    assets.extend(dict(package=prefix+'Ability/GA_'+str(i),role='ability_clue') for i in range(abilities))
    for asset in assets:
        asset['observations']=[]
    return dict(id=identifier,resource_folder=identifier,reference_only=False,assets=assets)


class MetadataTests(unittest.TestCase):
    def manifest(self,manifest=None):
        rows=jobs.jobs_for(candidate())
        manifest=manifest or dict(jobs=rows,batch_fingerprint='a'*20,script_sha256='b'*64)
        rows=manifest['jobs']
        lines=['PBZ_ADAPTER_META:START='+manifest['batch_fingerprint']]
        for job in rows:
            prefix='PBZ_ADAPTER_META:OUTCOME='+job['key']+'|'+job['role']+'|'+job['lookup_path']
            if job['role']=='character':
                lines.append(prefix+'|'+job['config_candidates'][0]+'|Fixture name|'+job['lookup_path']
                    +',/Script/ProjectPBZ.PBZCharacter_NPC,/Script/CoreUObject.Object')
            else:
                lines.append(prefix+'|leaf')
        lines.append('PBZ_ADAPTER_META:END='+manifest['batch_fingerprint'])
        return manifest,lines

    def test_variants_have_independent_class_jobs_without_selecting_a_config(self):
        rows=jobs.jobs_for(candidate(characters=2))
        characters=[row for row in rows if row['role']=='character']
        self.assertEqual(len(characters),2)
        self.assertNotEqual(characters[0]['key'],characters[1]['key'])
        self.assertTrue(all('expected_config' not in row for row in rows))

    def test_dependency_abilities_remain_metadata_queries(self):
        row=candidate();row['assets'][-1]['role']='ability_dependency_clue'
        self.assertEqual(jobs.jobs_for(row)[-1]['role'],'ability')
        self.assertNotIn('binding_verified',jobs.jobs_for(row)[-1])

    def test_batches_bound_requests_and_number_of_bosses(self):
        result=jobs.batches([candidate('c'+str(i),abilities=30) for i in range(6)])
        self.assertTrue(all(1<=len(batch)<=64 and len({j['id'] for j in batch})<=3 for batch in result))
        keys=[j['key'] for batch in result for j in batch]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertEqual(len(keys),6*31)
        grouped=[identifier for batch in result for identifier in {j['id'] for j in batch}]
        self.assertEqual(len(grouped),len(set(grouped)),'Keep one Boss together whenever it fits the batch budget')
        large=jobs.batches([candidate('large',abilities=80)])
        self.assertEqual([len(batch) for batch in large],[64,17])

    def test_unobserved_cross_folder_or_duplicate_paths_are_rejected(self):
        row=candidate();row['assets'][0]['package']='/PBZCombatAsset/ActorData/Mobs/other/ActorC_Other'
        with self.assertRaises(ValueError):jobs.jobs_for(row)
        row=candidate();row['assets'].append(row['assets'][-1])
        with self.assertRaises(ValueError):jobs.jobs_for(row)

    def test_complete_metadata_does_not_grant_identity_control_or_playability(self):
        manifest,lines=self.manifest();outcomes=jobs.analyze(lines,manifest)
        self.assertTrue(all(row['metadata_verified'] for row in outcomes))
        self.assertTrue(outcomes[0]['config_in_observed_candidates'])
        for row in outcomes:
            self.assertTrue(all(row[key] is False for key in ['identity_verified','live_grant_verified','activation_verified','playable']))

    def test_actual_cdo_reference_is_recorded_without_inventing_a_pair(self):
        manifest,lines=self.manifest()
        lines[1]=lines[1].replace(manifest['jobs'][0]['config_candidates'][0],'/Shared/ActorC_Other.ActorC_Other')
        row=jobs.analyze(lines,manifest)[0]
        self.assertEqual(row['observed_config'],'/Shared/ActorC_Other.ActorC_Other')
        self.assertFalse(row['config_in_observed_candidates']);self.assertFalse(row['identity_verified'])

    def test_leaf_subtree_and_rejection_are_separate_metadata_outcomes(self):
        manifest,lines=self.manifest();lines[2]=lines[2].replace('|leaf','|subtree')
        self.assertEqual(jobs.analyze(lines,manifest)[1]['ability_kind'],'subtree')
        lines[2]='PBZ_ADAPTER_META:REJECTED='+manifest['jobs'][1]['key']+'|asset unavailable'
        self.assertFalse(jobs.analyze(lines,manifest)[1]['metadata_verified'])

    def test_unknown_duplicate_or_mismatched_outcomes_cannot_pass(self):
        manifest,lines=self.manifest()
        changed=lines.copy();changed[2]=changed[2].replace('|leaf','|unknown')
        wrong=lines.copy();wrong[1]=wrong[1].replace(manifest['jobs'][0]['lookup_path'],'/Wrong.Boss_C',1)
        malformed=lines.copy();malformed[1]=malformed[1].replace(manifest['jobs'][0]['config_candidates'][0],'/Invalid Config')
        long_name=lines.copy();long_name[1]=long_name[1].replace('Fixture name','x'*513)
        for trial in [lines[:-1]+[lines[1],lines[-1]],changed,wrong,malformed,long_name]:
            with self.assertRaises(AssertionError):jobs.analyze(trial,manifest)

    def test_expired_incomplete_or_replayed_batch_is_rejected(self):
        manifest,lines=self.manifest()
        for trial in [lines[:-1],lines[1:],lines+[lines[1]],
                [lines[0],'PBZ_ADAPTER_META:STOP=deadline',lines[-1]],
                [lines[0].replace('a'*20,'c'*20),*lines[1:]]]:
            with self.assertRaises(AssertionError):jobs.analyze(trial,manifest)

    def test_real_catalog_jobs_are_frozen_and_unobserved_jobs_are_refused(self):
        catalog=json.loads((ROOT/'research/boss-adaptation/catalog.json').read_bytes())
        row=next(c for c in catalog['candidates'] if c['id']=='054_zuoshang')
        selected=jobs.jobs_for(row)[:2]
        with tempfile.TemporaryDirectory() as directory:
            batch=jobs.freeze(selected,Path(directory))
            self.assertEqual(jobs.verify_batch(batch)['jobs'],selected)
            modified=copy.deepcopy(selected);modified[0]['lookup_path']='/Unknown/Class.Class_C'
            with self.assertRaises(AssertionError):jobs.freeze(modified,Path(directory))
            script=batch/'metadata-probe.lua';script.write_bytes(script.read_bytes()+b'\nerror("tampered")\n')
            with self.assertRaises(AssertionError):jobs.verify_batch(batch)

    def collection_fixture(self,root):
        root=root.resolve()
        for name in jobs.SOURCES:
            destination=root/name;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/name,destination)
        source=root/'evidence/adaptation/fixture.json';source.parent.mkdir(parents=True)
        source.write_text('{"fixture_only":true}',encoding='utf-8')
        catalog=root/'research/boss-adaptation/catalog.json';catalog.parent.mkdir(parents=True)
        catalog.write_text(json.dumps(dict(target_build_sha256=BUILD,candidates=[candidate()],
            sources=[dict(path=source.relative_to(root).as_posix(),sha256=sha(source))])),encoding='utf-8')
        batch=jobs.freeze(jobs.jobs_for(candidate()),root/'runtime',root)
        manifest,lines=self.manifest(jobs.verify_batch(batch,root))
        session='20261117-000000';fingerprint=manifest['batch_fingerprint']
        script=(batch/'metadata-probe.lua').read_bytes();metadata=batch/'metadata-probe-manifest.json'
        work=root/'evidence/official-validation'/session;work.mkdir(parents=True)
        state_path=root/'runtime'/('official-validation-'+session)/'state.json';state_path.parent.mkdir()
        state=dict(restored=True,work=str(work));state_path.write_text(json.dumps(state),encoding='utf-8')
        post=dict(validation_state=str(state_path),research_box_empty=True,research_loader_removed=True,
            host_registry_unchanged=True,formal_files_changed=[],host_config_files_changed=[])
        (work/'postcheck.json').write_text(json.dumps(post),encoding='utf-8')
        (work/(fingerprint+'-adapter-metadata.lua')).write_bytes(script)
        (work/'UE4SS.log').write_text('\n'.join(lines),encoding='utf-8')
        action=dict(state_file=str(state_path),metadata_only=True,metadata_kind='adapter_metadata_jobs',
            batch_fingerprint=fingerprint,script_sha256=manifest['script_sha256'],
            batch_manifest_sha256=sha(metadata),lines=lines,boss_control_verified=False,
            all_metadata_requests_passed=True)
        (work/(fingerprint+'-adapter-metadata-results.json')).write_text(json.dumps(action),encoding='utf-8')
        return session,batch,manifest,state_path

    def test_collector_requires_closed_restored_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);session,batch,manifest,state_path=self.collection_fixture(root)
            state=json.loads(state_path.read_bytes());state['restored']=False;state_path.write_text(json.dumps(state),encoding='utf-8')
            with self.assertRaises(AssertionError):collector.collect(session,batch,root)
            self.assertFalse((root/'research/boss-adaptation/adapter-metadata-receipts').exists())

    def test_collector_freezes_exact_batch_sources_and_never_updates_playable_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);session,batch,manifest,state_path=self.collection_fixture(root)
            target=collector.collect(session,batch,root)
            self.assertEqual(collector.collect(session,batch,root),target)
            receipt=json.loads(target.read_bytes())
            self.assertFalse(receipt['playable']);self.assertFalse(receipt['control_verified'])
            self.assertEqual(receipt['batch_fingerprint'],manifest['batch_fingerprint'])
            self.assertEqual(len(receipt['outcomes']),2)
            self.assertFalse((root/'mod').exists())

    def test_receipt_replays_real_frozen_fixture_without_mocking_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();session,batch,_,_=self.collection_fixture(root)
            target=collector.collect(session,batch,root)
            receipt=collector.verify_receipt(target,root)
            self.assertEqual(receipt['schema_version'],2)
            self.assertEqual(receipt['batch_directory'],batch.relative_to(root).as_posix())
            self.assertTrue(all(row['metadata_verified'] for row in receipt['outcomes']))

    def test_edited_flags_outcomes_and_source_graph_cannot_pass_receipt_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();session,batch,_,_=self.collection_fixture(root)
            target=collector.collect(session,batch,root);original=json.loads(target.read_bytes())
            for field in ('playable','control_verified','runtime_acceptance_current'):
                changed=copy.deepcopy(original);changed[field]=True;target.write_text(json.dumps(changed),encoding='utf-8')
                with self.assertRaises(AssertionError):collector.verify_receipt(target,root)
            changed=copy.deepcopy(original);changed['outcomes'][0]['observed_config']='/Other.Config'
            target.write_text(json.dumps(changed),encoding='utf-8')
            with self.assertRaises(AssertionError):collector.verify_receipt(target,root)
            changed=copy.deepcopy(original);changed['sources'].pop(next(iter(changed['sources'])))
            target.write_text(json.dumps(changed),encoding='utf-8')
            with self.assertRaises(AssertionError):collector.verify_receipt(target,root)

    def test_receipt_paths_cannot_escape_or_be_relocated(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();session,batch,_,_=self.collection_fixture(root)
            target=collector.collect(session,batch,root);original=json.loads(target.read_bytes())
            renamed=target.with_name('renamed.json');renamed.write_bytes(target.read_bytes())
            with self.assertRaises(AssertionError):collector.verify_receipt(renamed,root)
            for path in ('../outside','C:/outside','runtime/../outside','/outside','runtime\\outside'):
                changed=copy.deepcopy(original);changed['batch_directory']=path
                target.write_text(json.dumps(changed),encoding='utf-8')
                with self.assertRaises(AssertionError):collector.verify_receipt(target,root)

    def test_raw_attempt_cannot_hide_additional_results_or_repeat_start(self):
        manifest,lines=self.manifest();fingerprint=manifest['batch_fingerprint']
        for changed in (lines+[lines[0],*lines[1:]],lines[:-1]+[lines[1],lines[-1]],
                lines[:-1]+['PBZ_ADAPTER_META:START='+'c'*20,lines[-1]],
                lines+[lines[1]],[lines[1],*lines]):
            with self.assertRaises(AssertionError):
                extracted=collector.batch_lines('\n'.join(changed),fingerprint)
                jobs.analyze(extracted,manifest)

    def test_raw_batch_selection_ignores_complete_independent_batches(self):
        manifest,lines=self.manifest();other=[line.replace('a'*20,'c'*20) for line in lines]
        self.assertEqual(collector.batch_lines('\n'.join(other+lines+other),manifest['batch_fingerprint']),lines)

    def test_stored_action_cannot_omit_or_shorten_a_raw_line(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();session,batch,manifest,state_path=self.collection_fixture(root)
            work=Path(json.loads(state_path.read_bytes())['work'])
            action_path=work/(manifest['batch_fingerprint']+'-adapter-metadata-results.json')
            original=json.loads(action_path.read_bytes())
            for lines in (original['lines'][:1]+original['lines'][2:],
                    ['prefix '+line for line in original['lines']]):
                changed=copy.deepcopy(original);changed['lines']=lines
                action_path.write_text(json.dumps(changed),encoding='utf-8')
                with self.assertRaises(AssertionError):collector.collect(session,batch,root)

    def test_replay_rejects_changed_raw_log_even_after_updating_its_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();session,batch,manifest,_=self.collection_fixture(root)
            target=collector.collect(session,batch,root);receipt=json.loads(target.read_bytes())
            log=root/'evidence/official-validation'/session/'UE4SS.log'
            lines=log.read_text(encoding='utf-8').splitlines()
            log.write_text('\n'.join(lines[:-1]+[lines[1],lines[-1]]),encoding='utf-8')
            receipt['sources'][log.relative_to(root).as_posix()]=sha(log)
            target.write_text(json.dumps(receipt),encoding='utf-8')
            with self.assertRaises(AssertionError):collector.verify_receipt(target,root)

    def test_replay_checks_closed_session_and_current_probe_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();session,batch,_,state_path=self.collection_fixture(root)
            target=collector.collect(session,batch,root)
            original=state_path.read_bytes();state=json.loads(original);state['restored']=False
            state_path.write_text(json.dumps(state),encoding='utf-8')
            with self.assertRaises(AssertionError):collector.verify_receipt(target,root)
            state_path.write_bytes(original)
            source=root/jobs.SOURCES[0];source.write_bytes(source.read_bytes()+b'\n# changed\n')
            with self.assertRaises(AssertionError):collector.verify_receipt(target,root)

    def test_retry_batches_keep_only_requested_jobs_and_preserve_boss_grouping(self):
        candidates=[candidate('c'+str(i),abilities=25) for i in range(5)]
        selected=[job['key'] for c in candidates for job in jobs.jobs_for(c)[::2]]
        result=jobs.batches(candidates,selected)
        self.assertEqual([job['key'] for group in result for job in group],selected)
        self.assertTrue(all(len(group)<=64 and len({j['id'] for j in group})<=3 for group in result))
        self.assertEqual(jobs.batches(candidates,[]),[])

    def test_retry_batch_rejects_unknown_job_keys(self):
        with self.assertRaises(AssertionError):jobs.batches([candidate()],['unobserved'])


if __name__=='__main__':
    unittest.main()
