import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import boss_disk_declarations as disk
import boss_disk_scripts as scripts
import boss_disk_dependencies as dependencies


class ScriptTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.mapping = self.root/'exact.usmap'
        self.mapping.write_bytes(b'test mapping')
        self.scan = self.root/'scan.json'
        self.package = 'ProjectPBZ/Plugins/Secret/PBZCombatAsset/Content/ActorData/Mobs/QiShu/Ability/GA_Test.uasset'
        disk.write_new(self.scan, dict(kind='offline_native_dependency_scan', declaration_contents_verified=True,
            mapping_sha256=disk.digest(self.mapping), packages=[dict(package=self.package,
                function_count=2, declaration_sha256='d'*64)]))
        self.target = self.root/'scripts'
        self.plan = scripts.plan(self.scan, self.mapping, self.target)
        self.batch = self.plan['batches'][0]

    def receipt(self, unresolved=False):
        directory = self.target/self.batch['output']
        directory.mkdir(exist_ok=True)
        path = directory/'script-0000.json'
        functions = [dict(name='Begin', complete=True, statements=[dict(offset=0,
            expression=dict(Token='EX_EndOfScript'))]),
            dict(name='End', complete=not unresolved, statements=None if unresolved else [dict(offset=0,
                expression=dict(Token='EX_EndOfScript'))])]
        path.write_text(json.dumps(functions), encoding='utf-8')
        rows = [dict(package=self.package, passed=True, script_file=path.name,
            sha256=disk.digest(path), bytes=path.stat().st_size, functions=2,
            complete_functions=1 if unresolved else 2, unresolved_functions=1 if unresolved else 0)]
        receipt = dict(schema=1, kind='offline_native_skill_blueprint_scripts',
            job_sha256=self.batch['sha256'], mapping_sha256=disk.digest(self.mapping),
            tool_sha256='a'*64, packages=rows, passed=True, game_started=False,
            installed=False, runtime_behavior_verified=False)
        (directory/'result.json').write_text(json.dumps(receipt), encoding='utf-8')
        return path, receipt

    def test_plan_keeps_exact_counts_and_never_promotes_runtime(self):
        self.assertEqual(self.plan['packages'][0]['functions'], 2)
        self.assertEqual(scripts.checked_plan(self.target)[1], self.plan)
        self.assertFalse(self.plan['all_boss_skills_complete'])
        self.assertFalse(self.plan['runtime_behavior_verified'])
        self.assertEqual(scripts.summarize(self.target)['pending'], 1)
        with self.assertRaises(FileExistsError):
            scripts.plan(self.scan, self.mapping, self.target)

    def test_complete_and_unresolved_decodes_are_separate(self):
        self.receipt()
        result = scripts.summarize(self.target)
        self.assertEqual((result['extracted'], result['complete_functions'], result['unresolved_functions']), (1, 2, 0))
        self.assertTrue(result['all_functions_decoded'])
        self.receipt(unresolved=True)
        result = scripts.summarize(self.target)
        self.assertEqual((result['extracted'], result['complete_functions'], result['unresolved_functions']), (1, 1, 1))
        self.assertFalse(result['all_functions_decoded'])
        self.assertFalse(result['runtime_behavior_verified'])

    def test_script_tamper_and_end_marker_fabrication_rejected(self):
        path, receipt = self.receipt()
        path.write_text('[]', encoding='utf-8')
        with self.assertRaises(ValueError):
            scripts.summarize(self.target)
        path, receipt = self.receipt()
        functions = json.loads(path.read_bytes())
        functions[0]['statements'][0]['expression']['Token'] = 'EX_Nothing'
        path.write_text(json.dumps(functions), encoding='utf-8')
        receipt['packages'][0].update(sha256=disk.digest(path), bytes=path.stat().st_size)
        (path.parent/'result.json').write_text(json.dumps(receipt), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'EndOfScript'):
            scripts.summarize(self.target)

    def test_function_count_must_match_original_declarations(self):
        path, receipt = self.receipt()
        functions = json.loads(path.read_bytes())[:1]
        path.write_text(json.dumps(functions), encoding='utf-8')
        receipt['packages'][0].update(sha256=disk.digest(path), bytes=path.stat().st_size,
                                     functions=1, complete_functions=1)
        (path.parent/'result.json').write_text(json.dumps(receipt), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Declared function coverage'):
            scripts.summarize(self.target)

    def test_job_mapping_and_source_scan_are_immutable(self):
        for path in (self.scan, self.mapping, self.target/self.batch['job']):
            original = path.read_bytes()
            path.write_bytes(original+b' ')
            with self.subTest(path=path), self.assertRaises(ValueError):
                scripts.checked_plan(self.target)
            path.write_bytes(original)

    def test_receipt_cannot_escape_or_substitute_source(self):
        for key, value in [('job_sha256', '0'*64), ('mapping_sha256', '0'*64), ('runtime_behavior_verified', True)]:
            path, receipt = self.receipt()
            receipt[key] = value
            (path.parent/'result.json').write_text(json.dumps(receipt), encoding='utf-8')
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'source or scope'):
                scripts.summarize(self.target)
        path, receipt = self.receipt()
        receipt['packages'][0]['script_file'] = '../outside.json'
        (path.parent/'result.json').write_text(json.dumps(receipt), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'filename'):
            scripts.summarize(self.target)

    def test_existing_failed_batch_is_preserved_without_running_exporter(self):
        path, receipt = self.receipt()
        receipt['passed'] = False
        receipt['packages'][0] = dict(package=self.package, passed=False, error='test preserved failure')
        (path.parent/'result.json').write_text(json.dumps(receipt), encoding='utf-8')
        exporter, crypto, paks = self.root/'exporter.dll', self.root/'private.json', self.root/'paks'
        exporter.write_bytes(b'test'); crypto.write_bytes(b'test'); paks.mkdir()
        with patch.object(scripts.subprocess, 'run') as process:
            with self.assertRaisesRegex(ValueError, 'Preserve failed'):
                scripts.run(self.target, exporter, paks, crypto)
            process.assert_not_called()

    def test_script_dependencies_join_exact_original_declaration(self):
        self.receipt(unresolved=True)
        key = dependencies.native_package(self.package).casefold()
        declarations = {key: dict(declaration_sha256='d'*64)}
        refs, identities, unresolved = dependencies.script_reference_map([self.target], declarations, disk.digest(self.mapping))
        self.assertEqual(refs, {key: set()})
        self.assertEqual(unresolved, 1)
        self.assertEqual(identities[0]['plan_sha256'], disk.digest(self.target/'plan.json'))
        declarations[key]['declaration_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'exact verified declaration'):
            dependencies.script_reference_map([self.target], declarations, disk.digest(self.mapping))


if __name__ == '__main__':
    unittest.main()
