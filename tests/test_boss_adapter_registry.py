"""Independent Boss planning, bounded jobs and source-matched expansion artifacts."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import boss_adapter_registry as registry
from boss_adaptation_workflow import BUILD, ROOT, sha


def candidate(identifier='one',characters=1,configs=1):
    prefix='/PBZCombatAsset/ActorData/Mobs/'+identifier+'/'
    assets=[]
    for role,number,leaf in [('character_blueprint_clue',characters,'BP_Monster_'),('actor_config_clue',configs,'ActorC_'),('ability_clue',2,'GA_')]:
        for index in range(number):
            assets.append(dict(package=prefix+leaf+str(index),role=role,observations=[]))
    return dict(id=identifier,resource_folder=identifier,reference_only=False,assets=assets)


class RegistryTests(unittest.TestCase):
    def catalog(self,*rows):
        return dict(target_build_sha256=BUILD,candidates=list(rows))

    def test_one_pair_prepares_two_requests_without_promoting_profile(self):
        result=registry.plan(self.catalog(candidate()),['one'])
        row=result['adapters'][0]
        self.assertEqual(len(row['identity_requests']),2)
        self.assertFalse(row['identity_verified']);self.assertFalse(row['playable'])
        self.assertIsNone(row['runtime_profile']);self.assertIsNone(row['runtime_policy'])
        self.assertTrue(all(value is False for value in row['capabilities'].values()))
        self.assertTrue(all(skill['player_key'] is None and not skill['granted_to_selected_actor'] for skill in row['skills']))

    def test_multiple_variants_never_pair_a_summon_with_main_body(self):
        row=registry.plan(self.catalog(candidate(characters=2,configs=3)),['one'])['adapters'][0]
        self.assertEqual(row['stage'],'variant_binding_required')
        self.assertEqual(row['identity_requests'],[])
        self.assertIsNotNone(row['variant_blocker'])

    def test_missing_config_remains_blocked(self):
        result=registry.plan(self.catalog(candidate(configs=0)),['one'])
        self.assertEqual(result['next_identity_batches'],[])

    def test_wrong_build_rejected(self):
        catalog=self.catalog(candidate());catalog['target_build_sha256']='other'
        with self.assertRaises(ValueError):registry.plan(catalog,['one'])

    def test_unknown_duplicate_and_oversize_queues_rejected(self):
        for identifiers in [[],['unknown'],['one','one'],['one']*13]:
            with self.subTest(identifiers=identifiers),self.assertRaises(ValueError):
                registry.plan(self.catalog(candidate()),identifiers)

    def test_reference_and_invalid_identifiers_rejected(self):
        row=candidate();row['reference_only']=True
        with self.assertRaises(ValueError):registry.plan(self.catalog(row),['one'])
        with self.assertRaises(ValueError):registry.plan(self.catalog(candidate('../one')),['../one'])

    def test_jobs_preserve_explicit_order_and_are_bounded_to_three_pairs(self):
        identifiers=['c'+str(i) for i in range(7)]
        result=registry.plan(self.catalog(*(candidate(i) for i in identifiers)),identifiers)
        self.assertEqual(result['next_identity_batches'],[identifiers[:3],identifiers[3:6],identifiers[6:]])

    def test_independent_boss_skills_and_untrusted_accepted_flags_do_not_leak(self):
        rows=[candidate('first'),candidate('second')];rows[0]['playable']=True
        result=registry.plan(self.catalog(*rows),['first','second'])
        for row in result['adapters']:
            self.assertFalse(row['playable'])
            self.assertTrue(all('/'+row['resource_folder']+'/' in s['package'] for s in row['skills']))

    def test_canonical_paths_reject_escape_or_windows_reinterpretation(self):
        for name in ['../outside','/absolute','a/../b','a\\b','C:/outside','a//b']:
            with self.subTest(name=name),self.assertRaises(ValueError):registry.safe(ROOT,name)

    def test_repository_queue_builds_reproducibly_and_verifies(self):
        path=registry.build();first=registry.read(path)
        self.assertEqual(registry.build(),path)
        self.assertEqual(registry.read(path),first)
        result=registry.verify(path)
        self.assertEqual((result['adapters'],result['metadata_ready'],result['variant_blocked'],result['metadata_requests']),(6,3,3,6))

    def test_report_cannot_claim_runtime_or_change_source_graph(self):
        original=registry.read(registry.build())
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.json'
            for key in ['game_started','installed','complete_mod','runtime_acceptance_current']:
                changed=copy.deepcopy(original);changed[key]=True;path.write_text(json.dumps(changed),encoding='utf-8')
                with self.assertRaises(AssertionError):registry.verify(path)
            changed=copy.deepcopy(original);changed['source_files']['tools/boss_adapter_registry.py']='0'*64
            path.write_text(json.dumps(changed),encoding='utf-8')
            with self.assertRaises(AssertionError):registry.verify(path)

    def test_rehashed_probe_rewrite_cannot_replace_generated_readonly_code(self):
        report=registry.read(registry.build())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            names=set(report['source_files'])|{report['catalog']}
            catalog=registry.read(ROOT/report['catalog'])
            names.update(row['path'] for row in catalog['sources'])
            for batch in report['batches']:
                manifest=registry.read(ROOT/batch['directory']/'manifest.json')
                names.update(manifest['source_files'])
            for name in names:
                destination=root/name;destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(ROOT/name,destination)
            shutil.copytree(ROOT/report['directory'],root/report['directory'])
            batch=report['batches'][0];folder=root/batch['directory']
            script=folder/'identity-probe.lua';script.write_bytes(script.read_bytes()+b'\nerror("rewritten")\n')
            probe=registry.read(folder/'identity-probe-manifest.json');probe['script_sha256']=sha(script)
            (folder/'identity-probe-manifest.json').write_text(json.dumps(probe),encoding='utf-8')
            batch['script_sha256']=sha(script);batch['probe_manifest_sha256']=sha(folder/'identity-probe-manifest.json')
            path=root/'report.json';path.write_text(json.dumps(report),encoding='utf-8')
            with self.assertRaises(AssertionError):registry.verify(path,root)


if __name__=='__main__':
    unittest.main()
