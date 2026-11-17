"""Tests for source freeze, bounded batch selection and quarantined identity requests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import boss_adaptation_workflow as workflow
import build_boss_adaptation_batch as batch
import build_boss_identity_probe as probe


class BatchTests(unittest.TestCase):
    def test_explicit_next_wave_does_not_repeat_first_queue(self):
        work=[{'id':id,'class_candidates':[{}],'config_candidates':['config']} for id in ['057_wanjun','054_zuoshang','066_rentuzi','071_xianzhe']]
        wanted=['054_zuoshang','066_rentuzi','071_xianzhe']
        self.assertEqual(batch.select_batch(work,wanted),wanted)

    def test_default_batch_skips_ambiguous_pairs_instead_of_failing_probe_generation(self):
        work=[{'id':'variants','class_candidates':[{},{}],'config_candidates':['config']},
              {'id':'one','class_candidates':[{}],'config_candidates':['config']}]
        self.assertEqual(batch.select_batch(work),['one'])
        with self.assertRaises(ValueError):batch.select_batch(work,['variants'])

    def test_explicit_queue_rejects_unknown_duplicate_or_excessive_ids(self):
        work=[{'id':'one','class_candidates':[{}],'config_candidates':['config']}]
        for identifiers in [[],['unknown'],['one','one'],['one']*4]:
            with self.subTest(identifiers=identifiers),self.assertRaises(ValueError):batch.select_batch(work,identifiers)

    def test_missing_config_cannot_be_scheduled_as_identity_pair(self):
        work=[{'id':'one','class_candidates':[{}],'config_candidates':[]}]
        self.assertEqual(batch.select_batch(work),[])
        with self.assertRaises(ValueError):batch.select_batch(work,['one'])

    def test_only_observed_class_paths_count(self):
        a={'package':'/P/BP_Test','observations':[{'observed':'/P/BP_Test.Default__BP_Test_C'}]}
        self.assertIsNone(batch.exact_class(a))
        a['observations'].append({'observed':'/P/BP_Test.BP_Test_C'})
        self.assertEqual(batch.exact_class(a),'/P/BP_Test.BP_Test_C')

    def test_candidate_is_not_a_playable_profile(self):
        c={'id':'other','resource_folder':'Other','assets':[
            {'package':'/P/GA_Other','role':'ability_clue','observations':[]}]}
        work=batch.candidate_work(c)
        self.assertFalse(work['enabled'])
        self.assertFalse(work['runtime_session_allowed'])
        self.assertFalse(work['skills'][0]['granted_to_selected_actor'])
        self.assertIsNone(work['skills'][0]['player_key'])

    def candidate(self):
        prefix='/PBZCombatAsset/ActorData/Mobs/057_WanJun/'
        return {'id':'057_wanjun','resource_folder':'057_WanJun',
                'class_candidates':[{'package':prefix+'BP_Monster_WanJun_JinGua'}],
                'config_candidates':[prefix+'ActorData/ActorC_WanJun_JinGua']}

    def test_request_derivation_is_explicit_not_evidence(self):
        rows=probe.requests(self.candidate())
        self.assertEqual(len(rows),2)
        self.assertIn('not verified',rows[0]['lookup_path_derivation'])
        self.assertTrue(rows[0]['lookup_path'].endswith('_C'))

    def test_ambiguous_or_cross_folder_pair_rejected(self):
        c=self.candidate();c['config_candidates'].append(c['config_candidates'][0])
        with self.assertRaises(ValueError): probe.requests(c)
        c=self.candidate();c['config_candidates'][0]='/PBZCombatAsset/ActorData/Mobs/Other/ActorC_Other'
        with self.assertRaises(ValueError): probe.requests(c)
        c=self.candidate();c['class_candidates'][0]['package']+="');SpawnActor('oops"
        with self.assertRaises(ValueError): probe.requests(c)

    def test_freeze_is_idempotent_and_rejects_changed_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); evidence=root/'evidence/captured.json'
            workflow.write_json(evidence,{'at':'old','name':'/PBZCombatAsset/ActorData/Mobs/057_WanJun/BP_Monster_WanJun_JinGua'})
            for name in ('tools/boss_adaptation_workflow.py','tools/collect_boss_resource_names.py',
                'tools/build_boss_adaptation_batch.py','tools/build_boss_identity_probe.py',
                'tools/run_boss_offline_milestone.py',
                'tests/test_boss_adaptation_workflow.py','tests/test_boss_adaptation_batch.py',
                'tests/test_boss_identity_probe.lua'):
                destination=root/name;destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes((workflow.ROOT/name).read_bytes())
            catalog=workflow.collect([evidence],root)
            path=root/'catalog.json';workflow.write_json(path,catalog)
            first=batch.freeze(path,root/'batches',root)
            catalog['at']='new observation time without content changes';workflow.write_json(path,catalog)
            self.assertEqual(first,batch.freeze(path,root/'batches',root))
            evidence.write_text('{}',encoding='utf-8')
            with self.assertRaises(ValueError): batch.freeze(path,root/'batches',root)


if __name__=='__main__':
    unittest.main()
