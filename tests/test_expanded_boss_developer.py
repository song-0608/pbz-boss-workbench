import ast
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import expanded_boss_developer_bundle as bundle
import expanded_boss_developer_workflow as workflow


class ExpansionTests(unittest.TestCase):
    def test_real_three_reviewed_identities_and_leaf_pools(self):
        for identifier,review in bundle.REVIEWS.items():
            with self.subTest(identifier=identifier):
                value,evidence=bundle.definition(identifier)
                self.assertEqual(value['display_name'],review['display_name'])
                self.assertEqual([p.rsplit('.',1)[-1]for p in value['ability_pool']],list(review['priority']))
                self.assertGreaterEqual(len(value['ability_pool']),4)
                self.assertTrue(evidence)
                self.assertFalse(any('/BulletData/'in p or '/Retarget/'in p for p in value['ability_pool']))
                self.assertNotIn('playable',value)

    def test_identity_mismatch_and_failed_or_subtree_ability_refused(self):
        original=bundle.verify_receipt
        for mode in ('config','name','lineage','leaf','failed'):
            def changed(path,root):
                data=copy.deepcopy(original(path,root))
                for row in data['outcomes']:
                    if row['id']!='071_xianzhe':continue
                    if row['role']=='character':
                        if mode=='config':row['observed_config']='/wrong.Config'
                        if mode=='name':row['display_name']='None'
                        if mode=='lineage':row['lineage']=[]
                    elif row['class_path'].endswith('.GA_XianZhe_Skill_05_C'):
                        if mode=='leaf':row['ability_kind']='subtree'
                        if mode=='failed':row['metadata_verified']=False
                return data
            with self.subTest(mode=mode),patch.object(bundle,'verify_receipt',side_effect=changed):
                with self.assertRaises((AssertionError,IndexError)):bundle.definition('071_xianzhe')

    def test_workflow_routes_definition_without_mutating_dossiers(self):
        files=workflow.render()
        for name,data in files.items():ast.parse(data.decode('utf-8'),filename=name)
        runner=files['run_control_lifecycle_probe.py'].decode('utf-8')
        for gate in ('v.verify_build',"c.baseline.formal_files()!=s['formal_before']",'issue_expiry',
                     "time.time()>s['deadline_unix']-120"):
            self.assertIn(gate,runner)
        for name in ('test_player_skill_batch.py','run_boss_candidate_milestone.py','collect_boss_candidate_acceptance.py'):
            self.assertIn('expanded_boss_developer_bundle',files[name].decode('utf-8'))
        gate={};exec(files['boss_candidate_gate.py'],gate)
        for identifier in ('071_xianzhe','058_maddoctor','067_motian','066_rentuzi'):
            with self.assertRaises(RuntimeError):gate['validate'](identifier)

    def test_bundle_mutation_and_wrong_boss_refused(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);base=root/'mod/PBZBossControl/Scripts';base.mkdir(parents=True)
            (base/'sentinel.lua').write_bytes(b'return {}')
            for name in bundle.SOURCES:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((bundle.ROOT/name).read_bytes())
            value={'id':'071_xianzhe','identity_receipt_sha256':'a'*64,
                   'ability_metadata_receipt_sha256':'b'*64,'max_local_displacement_cm':3000}
            with patch.object(bundle,'definition',return_value=(value,{})):
                target=bundle.build('071_xianzhe',root)
                self.assertEqual(target,bundle.build('071_xianzhe',root))
                (target/'boss_candidate.lua').write_bytes(b'changed')
                with self.assertRaises(AssertionError):bundle.validate('071_xianzhe',target,root=root)
        with self.assertRaises(AssertionError):bundle.definition('066_rentuzi')


if __name__=='__main__':unittest.main()
