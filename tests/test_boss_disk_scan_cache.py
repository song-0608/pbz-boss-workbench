import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import boss_disk_scan_cache as cache


class ScanCacheTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'scan.json'
        self.sources={name:digit*64 for name,digit in (
            ('boss_disk_dependencies.py','a'),('boss_disk_declarations.py','b'),
            ('boss_disk_skill_index.py','c'),('boss_disk_scripts.py','d'),('boss_disk_scan_cache.py','e'))}
        self.item=dict(package='ProjectPBZ/Content/A.uasset',declaration_sha256='f'*64,declaration_bytes=12)
        self.declarations={'/game/a':self.item}
        self.script=dict(path=str(self.path.parent/'scripts'),plan_sha256='1'*64)
        self.report=dict(schema=1,kind='offline_native_dependency_scan',declaration_contents_verified=True,
            index_sha256='2'*64,mapping_sha256='3'*64,sources=dict(self.sources),
            script_sources=[self.script],packages=[dict(self.item)],extracted_packages=1,
            export_types={'DataAsset':1})

    def load(self,scripts=None):
        self.path.write_text(json.dumps(self.report),encoding='utf-8')
        return cache.load(self.path,'2'*64,'3'*64,self.sources,
            [self.script] if scripts is None else scripts,self.declarations,lambda p:'/Game/A')

    def test_exact_cache_keeps_content_hash_verification_required(self):
        rows,types,identity=self.load()
        self.assertEqual(set(rows),{'/game/a'})
        self.assertEqual(types,{'DataAsset':1})
        self.assertTrue(identity['contents_still_require_sha256'])
        self.assertFalse(identity['legacy_parser_migration'])

    def test_only_named_legacy_parser_can_migrate_without_helper_identity(self):
        self.report['sources'].pop('boss_disk_scan_cache.py')
        self.report['sources']['boss_disk_dependencies.py']=cache.LEGACY_PARSER
        self.assertTrue(self.load()[2]['legacy_parser_migration'])
        self.report['sources']['boss_disk_dependencies.py']='0'*64
        with self.assertRaisesRegex(ValueError,'parser sources'):
            self.load()

    def test_changed_semantic_parser_sources_are_rejected(self):
        self.report['sources']['boss_disk_skill_index.py']='0'*64
        with self.assertRaisesRegex(ValueError,'parser sources'):
            self.load()

    def test_old_script_inputs_cannot_disappear(self):
        with self.assertRaisesRegex(ValueError,'script sources'):
            self.load(scripts=[])

    def test_changed_declaration_identity_or_missing_row_is_rejected(self):
        self.report['packages'][0]['declaration_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'unchanged declaration'):
            self.load()
        self.report['packages']=[dict(self.item)]
        self.report['extracted_packages']=2
        with self.assertRaisesRegex(ValueError,'coverage mismatch'):
            self.load()


if __name__=='__main__':
    unittest.main()
