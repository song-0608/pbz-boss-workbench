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
