import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import boss_disk_declarations as disk

BASE = 'ProjectPBZ/Plugins/Secret/PBZCombatAsset/Content/ActorData/Mobs/057_WanJun/'


class DeclarationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.index = self.root/'index.csv'
        self.mapping = self.root/'exact.usmap'
        self.mapping.write_bytes(b'local test mapping')

    def index_rows(self, entries):
        with self.index.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=['Filename','ChunkType','Hash'])
            writer.writeheader()
            writer.writerows(entries)

    def entry(self, path, **extra):
        return dict(Filename='../../../'+BASE+path, ChunkType='ExportBundleData', Hash='source', **extra)

    def prepare(self, count=1):
        self.index_rows([self.entry(f'Ability/GA_Test_{i:04d}.uasset') for i in range(count)])
        self.target = self.root/'plan'
        return disk.plan(self.index, self.mapping, self.target)

    def receipt(self, batch, passed=True):
        directory = self.target/batch['output']
        directory.mkdir()
        data = directory/'declaration-0000.json'
        data.write_text('[{"Type":"BlueprintGeneratedClass","Properties":{}}]', encoding='utf-8')
        rows = [dict(package=batch['packages'][0], passed=passed,
                     declaration_file=data.name, declaration_sha256=disk.digest(data),
                     declaration_bytes=data.stat().st_size,
                     exports=[dict(name='GA_Test_C',type='BlueprintGeneratedClass')])]
        report = dict(mode='declarations',game_started=False,passed=passed,packages=rows,
                      input_job_sha256=batch['sha256'],mapping_sha256=disk.digest(self.mapping),tool_sha256='a'*64)
        (directory/'conversion-result.json').write_text(json.dumps(report), encoding='utf-8')
        return data, directory/'conversion-result.json', report

    def test_exact_scoped_index_and_duplicates(self):
        keep = [self.entry('Ability/SubTree/ST_Test.uasset'),self.entry('ActorData/ActorC_Test.uasset'),
                self.entry('BP_Monster_Test.uasset'),self.entry('Bullet/GA_Bullet.uasset')]
        reject = [self.entry('Meshes/SK_Body.uasset'), self.entry('Ability/../GA_Bad.uasset'),
                  dict(Filename='../../../Other/Ability/GA_Test.uasset',ChunkType='ExportBundleData',Hash='x'),
                  dict(keep[0], ChunkType='BulkData')]
        self.index_rows(keep+keep+reject)
        actual = disk.selected_packages(self.index)
        self.assertEqual(len(actual),4)
        self.assertEqual(len({r['package'] for r in actual}),4)
        self.assertTrue(all(r['folder']=='057_WanJun' for r in actual))

    def test_conflicting_source_index_rejected(self):
        row = self.entry('Ability/GA_Test.uasset')
        self.index_rows([row,dict(row,Hash='different')])
        with self.assertRaisesRegex(ValueError,'Conflicting'):
            disk.selected_packages(self.index)

    def test_bounded_batches_and_no_clobber(self):
        record = self.prepare(130)
        self.assertEqual([len(b['packages']) for b in record['batches']], [64,64,2])
        self.assertEqual(disk.checked_plan(self.target)[1],record)
        with self.assertRaises(FileExistsError):
            disk.plan(self.index,self.mapping,self.target)
        summary = disk.summarize(self.target)
        self.assertEqual((summary['requested'],summary['pending'],summary['extracted']),(130,130,0))
        self.assertFalse(summary['live_grant_verified'])
        self.assertFalse(summary['execution_verified'])

    def test_exact_receipt_digest_and_still_not_playable(self):
        record = self.prepare()
        data, _, _ = self.receipt(record['batches'][0])
        summary = disk.summarize(self.target)
        self.assertEqual((summary['extracted'],summary['pending']),(1,0))
        self.assertFalse(summary['playable'])
        data.write_text('[]',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'digest/size'):
            disk.summarize(self.target)

    def test_wrong_job_order_or_escaping_filename_rejected(self):
        record = self.prepare()
        _, path, report = self.receipt(record['batches'][0])
        for field,value in [('package',BASE+'Ability/Other.uasset'),('declaration_file','../outside.json')]:
            changed = json.loads(json.dumps(report))
            changed['packages'][0][field] = value
            path.write_text(json.dumps(changed),encoding='utf-8')
            with self.assertRaises(ValueError):
                disk.summarize(self.target)

    def test_mapping_and_job_changes_rejected(self):
        record = self.prepare()
        self.mapping.write_bytes(b'wrong game version')
        with self.assertRaisesRegex(ValueError,'mapping changed'):
            disk.checked_plan(self.target)
        self.mapping.write_bytes(b'local test mapping')
        (self.target/record['batches'][0]['job']).write_text('{}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'job changed'):
            disk.checked_plan(self.target)

    def test_failed_batch_preserved_without_auto_retry(self):
        record = self.prepare()
        self.receipt(record['batches'][0],passed=False)
        exporter,crypto = self.root/'tool.dll',self.root/'private.json'
        exporter.write_bytes(b'test'); crypto.write_bytes(b'not a real key')
        paks=self.root/'paks';paks.mkdir()
        with patch.object(disk.subprocess,'run') as process:
            with self.assertRaisesRegex(ValueError,'Preserve failed'):
                disk.run(self.target,exporter,paks,crypto)
            process.assert_not_called()

    def test_converter_receives_an_empty_output_directory(self):
        record = self.prepare()
        exporter,crypto = self.root/'tool.dll',self.root/'private.json'
        exporter.write_bytes(b'test');crypto.write_bytes(b'not a real key')
        paks=self.root/'paks';paks.mkdir()
        def convert(command, **options):
            directory = Path(command[-1])
            self.assertEqual(list(directory.iterdir()),[], 'converter refuses nonempty output')
            directory.rmdir()
            self.receipt(record['batches'][0])
            return type('Result',(),{'returncode':0})()
        with patch.object(disk.subprocess,'run',side_effect=convert):
            result=disk.run(self.target,exporter,paks,crypto)
        self.assertEqual(result['extracted'],1)
        self.assertTrue((self.target/'batch-0000.log').is_file())

    def test_unfinished_batch_is_pending_and_never_auto_retried(self):
        record=self.prepare()
        (self.target/record['batches'][0]['output']).mkdir()
        summary=disk.summarize(self.target)
        self.assertEqual(summary['pending'],1)
        self.assertEqual(summary['incomplete_batches'],['batch-0000'])
        with self.assertRaisesRegex(ValueError,'Preserve unfinished'):
            disk.checked_batch(self.target,record['batches'][0])

    def test_receipt_cannot_substitute_another_job_or_mapping(self):
        record=self.prepare()
        _,path,report=self.receipt(record['batches'][0])
        for field in ('input_job_sha256','mapping_sha256'):
            changed=dict(report,**{field:'0'*64})
            path.write_text(json.dumps(changed),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'job/mapping mismatch'):
                disk.summarize(self.target)


if __name__=='__main__':
    unittest.main()
