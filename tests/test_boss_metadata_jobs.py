"""Metadata planning and closed-result collection cannot promote playable profiles."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import boss_metadata_jobs as jobs
import collect_boss_metadata_jobs as collector
from boss_adaptation_workflow import ROOT, BUILD, sha


def candidate(identifier='fixture',characters=1,abilities=1):
    prefix='/PBZCombatAsset/ActorData/Mobs/'+identifier+'/'
    assets=[dict(package=prefix+'ActorConfig/ActorC_'+identifier,role='actor_config_clue')]
    assets.extend(dict(package=prefix+'BP_Monster_'+str(i),role='character_blueprint_clue') for i in range(characters))
    assets.extend(dict(package=prefix+'Ability/GA_'+str(i),role='ability_clue') for i in range(abilities))
    return dict(id=identifier,resource_folder=identifier,assets=assets)


class MetadataTests(unittest.TestCase):
    def manifest(self):
        rows=jobs.jobs_for(candidate())
        manifest=dict(jobs=rows,batch_fingerprint='a'*20,script_sha256='b'*64)
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
        manifest,lines=self.manifest();session='20261117-000000';fingerprint=manifest['batch_fingerprint']
        batch=root/'runtime'/('metadata-'+fingerprint);batch.mkdir(parents=True)
        script=b'-- fixture metadata only\n';(batch/'metadata-probe.lua').write_bytes(script)
        manifest['script_sha256']=sha(batch/'metadata-probe.lua')
        metadata=batch/'metadata-probe-manifest.json';metadata.write_text(json.dumps(manifest),encoding='utf-8')
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
            batch_manifest_sha256=sha(metadata),lines=lines)
        (work/(fingerprint+'-adapter-metadata-results.json')).write_text(json.dumps(action),encoding='utf-8')
        return session,batch,manifest,state_path

    def test_collector_requires_closed_restored_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);session,batch,manifest,state_path=self.collection_fixture(root)
            state=json.loads(state_path.read_bytes());state['restored']=False;state_path.write_text(json.dumps(state),encoding='utf-8')
            with patch.object(collector,'ROOT',root),patch.object(collector,'OUT',root/'research/boss-adaptation'),patch.object(collector,'verify_batch',return_value=manifest):
                with self.assertRaises(AssertionError):collector.collect(session,batch)
            self.assertFalse((root/'research/boss-adaptation/adapter-metadata-receipts').exists())

    def test_collector_freezes_exact_batch_sources_and_never_updates_playable_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);session,batch,manifest,state_path=self.collection_fixture(root)
            with patch.object(collector,'ROOT',root),patch.object(collector,'OUT',root/'research/boss-adaptation'),patch.object(collector,'verify_batch',return_value=manifest):
                target=collector.collect(session,batch)
                self.assertEqual(collector.collect(session,batch),target)
            receipt=json.loads(target.read_bytes())
            self.assertFalse(receipt['playable']);self.assertFalse(receipt['control_verified'])
            self.assertEqual(receipt['batch_fingerprint'],manifest['batch_fingerprint'])
            self.assertEqual(len(receipt['outcomes']),2)
            self.assertFalse((root/'mod').exists())


if __name__=='__main__':
    unittest.main()
