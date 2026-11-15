"""A rebuilt loader cannot reuse an older binary's successful runtime evidence."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import pbz_ue4ss_baseline as baseline


class BuildRecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.setup=self.root/'evidence/setup';self.setup.mkdir(parents=True)
        self.project=self.root/'Project';self.project.mkdir()
        self.artifacts=[]
        for name in ('UE4SS.dll','dwmapi.dll'):
            path=self.root/name;path.write_bytes(name.encode())
            self.artifacts.append({'path':str(path),'sha256':baseline.digest(path)})
        self.record={'compiled_from_source':True,'artifacts':self.artifacts,
            'practice_test':{'passed':True,'dll_sha256':self.artifacts[0]['sha256'],
                             'proxy_sha256':self.artifacts[1]['sha256']}}
        self.legacy=self.setup/'selfbuilt-ue4ss-verification.json'
        self.write(self.legacy,self.record)

    def write(self,path,value):path.write_text(json.dumps(value),encoding='utf-8')

    def load(self):
        with patch.object(baseline.v,'ROOT',self.project):return baseline.verified_build_record()

    def point(self,path):
        self.write(self.setup/'selfbuilt-ue4ss-current.json',
            {'verification_file':str(path),'sha256':baseline.digest(path)})

    def test_legacy_and_new_build_records(self):
        self.assertEqual(self.load()[1],self.legacy)
        new=self.setup/'new.json';self.write(new,self.record);self.point(new)
        self.assertEqual(self.load()[1],new)

    def test_changed_dll_cannot_borrow_runtime_pass(self):
        (self.root/'UE4SS.dll').write_bytes(b'new untested build')
        with self.assertRaisesRegex(RuntimeError,'differs'):self.load()

    def test_relabelled_artifact_still_must_match_smoke(self):
        (self.root/'UE4SS.dll').write_bytes(b'new untested build')
        self.record['artifacts'][0]['sha256']=baseline.digest(self.root/'UE4SS.dll')
        self.write(self.legacy,self.record)
        with self.assertRaisesRegex(RuntimeError,'do not match'):self.load()

    def test_pointer_integrity_and_scope(self):
        self.point(self.legacy);self.legacy.write_text('{}',encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError,'not intact'):self.load()
        outside=self.root/'outside.json';self.write(outside,self.record);self.point(outside)
        with self.assertRaisesRegex(RuntimeError,'not intact'):self.load()

    def test_input_source_and_regression_must_match(self):
        source=self.root/'source.cpp';source.write_bytes(b'tested input source')
        self.record['input_regression']={'passed':True,'source_sha256':{'source.cpp':baseline.digest(source)}}
        self.write(self.legacy,self.record);self.load()
        source.write_bytes(b'changed source')
        with self.assertRaisesRegex(RuntimeError,'source differs'):self.load()
        self.record['input_regression']['passed']=False;self.write(self.legacy,self.record)
        with self.assertRaisesRegex(RuntimeError,'did not pass'):self.load()


if __name__=='__main__':unittest.main()
