import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import youlong_developer_bundle as bundle


class YouLongBundleTests(unittest.TestCase):
    def test_real_harpoon_identity_and_explicit_initial_actions(self):
        value,evidence=bundle.definition()
        self.assertTrue(value['class_path'].endswith('BP_Monster_YouLong_Harpoon_C'))
        self.assertTrue(value['config_path'].endswith('.ActorC_YouLong_Harpoon'))
        self.assertEqual(len(value['ability_pool']),8)
        self.assertEqual(len(value['blocked_scene_abilities']),24)
        self.assertEqual(len(evidence),3)
        self.assertEqual([p.rsplit('.',1)[-1]for p in value['ability_pool']],list(bundle.PRIORITY))
        self.assertFalse(any(x in p for p in value['ability_pool']for x in
            ('TakeSpear','Summon','Hun_','FishingNet','AquaKiller','CACombo','_Mad','_Hard','/Child/')))

    def fixture(self,root):
        for name in bundle.SOURCES:
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((bundle.ROOT/name).read_bytes())
        base=root/'mod/PBZBossControl/Scripts';base.mkdir(parents=True)
        (base/'boss_catalog.lua').write_bytes(b'published sentinel')
        return {'id':bundle.ID,'class_path':'/Fixture.Actor_C','config_path':'/Fixture.Config',
            'display_name':'fixture','identity_receipt_sha256':'a'*64,'ability_metadata_receipt_sha256':'b'*64,
            'ability_pool':['/Fixture.Action_C'],'max_local_displacement_cm':3000}

    def test_frozen_bundle_deterministic_and_scope_or_source_tamper_refused(self):
        for mode in ('valid','payload','source','base','scope','definition','extra'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory()as temp:
                root=Path(temp);value=self.fixture(root)
                with patch.object(bundle,'definition',return_value=(value,{})):
                    target=bundle.build(root);self.assertEqual(target,bundle.build(root))
                    self.assertEqual(bundle.validate(bundle.ID,target,root=root)['boss_candidate'],bundle.ID)
                    if mode=='valid':continue
                    if mode=='payload':(target/'boss_candidate.lua').write_bytes(b'changed')
                    elif mode=='source':(root/bundle.SOURCES[0]).write_bytes(b'changed')
                    elif mode=='base':(root/'mod/PBZBossControl/Scripts/boss_catalog.lua').write_bytes(b'changed')
                    elif mode=='extra':(target/'extra.lua').write_bytes(b'changed')
                    else:
                        m=bundle.read(target/'manifest.json')
                        if mode=='scope':m['playable']=True
                        else:m['definition']['class_path']='/Wrong.Actor_C'
                        (target/'manifest.json').write_text(json.dumps(m),encoding='utf-8')
                    with self.assertRaises(AssertionError):bundle.validate(bundle.ID,target,root=root)

    def test_wrong_candidate_and_transitive_evidence_refused(self):
        with self.assertRaises(AssertionError):bundle.validate('073_yanqiansui',Path('unused'))
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);p=root/'source';p.write_bytes(b'original')
            receipt={'sources':{'source':bundle.sha(p)}};bundle.verify_sources(receipt,root)
            p.write_bytes(b'changed')
            with self.assertRaises(AssertionError):bundle.verify_sources(receipt,root)


if __name__=='__main__':unittest.main()
