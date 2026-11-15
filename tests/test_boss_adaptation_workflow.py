"""Offline discovery must preserve provenance and never promote names into playability."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import boss_adaptation_workflow as workflow
from collect_boss_resource_names import parse_block, scan


def entry(text, wide=False):
    data = text.encode('utf-16le' if wide else 'utf-8')
    header = ((len(data)//2 if wide else len(data)) << 6) | int(wide)
    raw = struct.pack('<H', header)+data
    return raw+b'\0'*(len(raw) % 2)


class DiscoveryTests(unittest.TestCase):
    def test_ascii_wide_alignment_and_stop(self):
        first, second = entry('Odd'), entry('测试', True)
        self.assertEqual(list(parse_block(first+second+b'\0\0'+entry('Ignored'))),
                         [(0, 'Odd'), (len(first), '测试')])

    def test_truncated_or_invalid_never_resynchronizes(self):
        self.assertEqual(list(parse_block(b'\xff\xffshort')), [])
        self.assertEqual(list(parse_block(b'\x40\x00\xff\x00'+entry('Wrong'))), [])
        with self.assertRaises(ValueError):
            list(parse_block(b'\0'*65537))

    def test_batch_crosscheck_and_limits(self):
        path='/PBZCombatAsset/ActorData/Mobs/054_ZuoShang/BP_Monster_ZuoShang'
        class Reader:
            base=0
            def u32(self, unused): return 0
            def u64(self, unused): return 0x10000
            def read(self, address, length): return entry(path)+b'\0\0'
            def name(self, comparison): return path
        self.assertEqual(scan(Reader())['resource_name_clues'][0]['name'],path)
        with self.assertRaises(RuntimeError): scan(Reader(),max_hits=0)
        class Wrong(Reader):
            def name(self, unused): return 'wrong'
        with self.assertRaises(RuntimeError): scan(Wrong())

    def test_timeout_and_block_bound(self):
        class Reader:
            base=0
            def u32(self, unused): return 3000
        with self.assertRaises(ValueError): scan(Reader())
        class One(Reader):
            def u32(self,unused): return 0
        times=iter([0,91])
        with self.assertRaises(RuntimeError): scan(One(),clock=lambda:next(times))

    def test_role_does_not_confuse_bullets_with_characters(self):
        self.assertEqual(workflow.role('/Mobs/Test/Bullet/BP_Bullet_Test'),'support_resource_clue')
        self.assertEqual(workflow.role('/Mobs/Test/Child/GA_Test_Skill'),'ability_dependency_clue')

    def test_provenance_dedup_and_no_promotion(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); path=root/'evidence.json'
            bp='/PBZCombatAsset/ActorData/Mobs/054_ZuoShang/BP_Monster_ZuoShang'
            cfg='/PBZCombatAsset/ActorData/Mobs/054_ZuoShang/ActorData/ActorC_ZuoShang'
            path.write_text(json.dumps({'x':[bp+'.BP_Monster_ZuoShang_C',bp+'.Default__BP_Monster_ZuoShang_C',cfg],
                                        'boss_control_verified':True}),encoding='utf-8')
            catalog=workflow.collect([path],root)
            candidate=catalog['candidates'][0]
            self.assertEqual(candidate['counts']['character_blueprint_clue'],1)
            self.assertFalse(candidate['playable'])
            self.assertEqual(catalog['sources'][0]['sha256'],workflow.sha(path))
            self.assertEqual(len(candidate['assets'][1]['observations']),2)
            draft=workflow.dossier(candidate,catalog)
            self.assertFalse(draft['enabled'])
            self.assertTrue(all(g['status']=='not_verified' for g in draft['runtime_gates'].values()))
            out=root/'out'; workflow.prepare(catalog,out)
            dossier=out/'dossiers/054_zuoshang.json'
            reviewed=draft|{'review_note':'keep reviewed edits'}
            workflow.write_json(dossier,reviewed)
            workflow.prepare(catalog,out)
            self.assertEqual(json.loads(dossier.read_text(encoding='utf-8'))['review_note'],'keep reviewed edits')

    def test_partial_or_wrong_build_snapshot_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'boss-resource-names.json'
            workflow.write_json(path,{'complete':False,'target_build_sha256':workflow.BUILD})
            with self.assertRaises(ValueError): workflow.collect([path],root)
            workflow.write_json(path,{'complete':True,'target_build_sha256':'different-build'})
            with self.assertRaises(ValueError): workflow.collect([path],root)


if __name__=='__main__':
    unittest.main()
