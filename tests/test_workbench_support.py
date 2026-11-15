"""Workbench actions cannot use an older, preview-only or mismatched carrier."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import workbench_support as support


class CapabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.state_path=self.root/'state.json'
        self.sources={name:'a'*64 for name in support.MODULES}
        self.cap=support.capability(self.sources,True)
        self.owner={'phase':'armed','state_file':str(self.state_path),'player_entry':True,'workbench':self.cap}
        self.state={'work':str(self.root),'ue4ss_loader_manifest':[
            {'physical_path':'C:/research/PBZObserveAI/Scripts/'+name,'sha256':digest}for name,digest in self.sources.items()]}
        self.deployment={'player_entry':True,'module_source_sha256':self.sources,'workbench':self.cap}
        self.write()

    def write(self):
        self.state_path.write_text(json.dumps(self.state),encoding='utf-8')
        (self.root/'control-lifecycle-deployment.json').write_text(json.dumps(self.deployment),encoding='utf-8')

    def check(self,owner=None):return support.validate_dispatch(self.root,self.state_path,owner or self.owner)

    def test_exact_ready_carrier_passes_and_legacy_has_no_capability(self):
        self.assertEqual(self.check(),self.cap)
        self.assertIsNone(support.capability({},True));self.assertIsNone(support.capability(self.sources,False))

    def test_stale_or_developer_owner_refused(self):
        for changes in ({'phase':'game_launched'},{'state_file':'old'},{'skill_lab':True},
                        {'player_entry':False},{'workbench':None}):
            with self.subTest(changes=changes),self.assertRaises(RuntimeError):self.check(dict(self.owner,**changes))

    def test_declared_hash_or_deployment_changes_refused(self):
        self.state['ue4ss_loader_manifest'][0]['sha256']='b'*64;self.write()
        with self.assertRaisesRegex(RuntimeError,'differs'):self.check()
        self.state['ue4ss_loader_manifest'][0]['sha256']='a'*64
        self.deployment['workbench']=copy.deepcopy(self.cap);self.deployment['workbench']['schema']=2;self.write()
        with self.assertRaisesRegex(RuntimeError,'readiness'):self.check()


if __name__=='__main__':unittest.main()
