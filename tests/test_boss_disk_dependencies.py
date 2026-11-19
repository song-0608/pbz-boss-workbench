import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import boss_disk_declarations as disk
import boss_disk_dependencies as dep


class DependencyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.mapping = self.root/'native.usmap'
        self.mapping.write_bytes(b'exact test mapping')
        self.index = self.root/'index.csv'
        self.paths = [dep.MOBS+'042_AHua/Ability/GA_Attack.uasset',
                      dep.MOBS+'QiShu/Abilites/GA_Magic.uasset',
                      dep.MOBS+'Common/WeaponData/Weapon_Shared.uasset',
                      'ProjectPBZ/Plugins/Secret/PBZDeflectSystem/Content/Actions/Guard.uasset',
                      'ProjectPBZ/Content/Animations/Attack.uasset']
        with self.index.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=['Filename', 'ChunkType', 'Hash'])
            writer.writeheader()
            for path in self.paths:
                writer.writerow(dict(Filename='../../../'+path, ChunkType='ExportBundleData', Hash='hash'))
        self.source = self.root/'source'
        row = dict(package=self.paths[0], folder='042_AHua')
        self.plan = dep.create_plan(self.index, self.mapping, self.source, [row], {}, 'test')
        self.batch = self.plan['batches'][0]
        self.directory = self.source/self.batch['output']
        self.directory.mkdir()
        self.declaration = self.directory/'declaration-0000.json'
        native = dep.native_package(self.paths[0])
        self.exports = [dict(Type='LegoAbilityBlueprintGeneratedClass', Name='GA_Attack_C', Package=native,
            Super=dict(ObjectName="Class'Native'", ObjectPath='/Script/Engine'),
            Properties=dict(
                self_reference=dict(ObjectName="Class'GA_Attack_C'", ObjectPath=native+'.1'),
                guard=dict(ObjectName="Class'Guard_C'", ObjectPath='/PBZDeflectSystem/Actions/Guard.0'),
                soft="/Script/Engine.AnimMontage'/Game/Animations/Attack.Attack'",
                unresolved='/Other/Missing.Missing', short_name='Guard_C'))]
        self.write_receipt()

    def write_receipt(self):
        self.declaration.write_text(json.dumps(self.exports), encoding='utf-8')
        self.receipt = dict(mode='declarations', game_started=False, passed=True,
            input_job_sha256=self.batch['sha256'], mapping_sha256=disk.digest(self.mapping), tool_sha256='a'*64,
            packages=[dict(package=self.paths[0], passed=True,
                declaration_file=self.declaration.name, declaration_sha256=disk.digest(self.declaration),
                declaration_bytes=self.declaration.stat().st_size)])
        (self.directory/'conversion-result.json').write_text(json.dumps(self.receipt), encoding='utf-8')

    def test_catalog_exact_mounts_and_no_short_name_resolution(self):
        self.assertEqual(dep.native_package(self.paths[0]), '/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GA_Attack')
        self.assertEqual(dep.native_package('Engine/Plugins/FX/Niagara/Content/Default.uasset'), '/Niagara/Default')
        self.assertEqual(dep.native_package('Engine/Content/Default.uasset'), '/Engine/Default')
        for bad in ('../Game/Content/X.uasset', '/ProjectPBZ/Content/X.uasset',
                    'C:/Game/Content/X.uasset', 'Unknown/Content/X.uasset'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                dep.native_package(bad)

    def test_roots_include_nonnumeric_typo_and_nonability_context(self):
        target = self.root/'expanded'
        plan = dep.roots(self.index, self.mapping, [self.source], target)
        self.assertEqual([r['package'] for r in plan['packages']], sorted(self.paths[1:3], key=str.casefold))
        self.assertEqual(plan['provenance']['reused_package_count'], 1)
        self.assertFalse(plan['provenance']['reused_contents_verified'])
        self.assertFalse(plan['all_boss_skills_complete'])
        self.assertFalse(plan['playable'])
        self.assertEqual(disk.checked_plan(target)[1], plan)
        with self.assertRaises(FileExistsError):
            dep.roots(self.index, self.mapping, [self.source], target)

    def test_hard_soft_native_unindexed_and_local_edges(self):
        result = dep.scan(self.index, [self.source])
        self.assertEqual(result['root_packages'], 3)
        self.assertEqual(result['pending_roots'], 2)
        self.assertEqual(result['pending_dependency_count'], 2)
        self.assertEqual(result['native_code_packages'], ['/Script/Engine'])
        self.assertEqual(result['unindexed_references'], ['/Other/Missing'])
        refs = result['packages'][0]['references']
        self.assertEqual(len(refs), 4)
        self.assertNotIn('Guard_C', str(refs))
        self.assertTrue(result['declaration_contents_verified'])
        self.assertFalse(result['serialized_package_closure_complete'])

    def test_scan_rejects_same_size_content_tamper(self):
        original = self.declaration.read_bytes()
        self.declaration.write_bytes(original.replace(b'GA_Attack', b'GA_Broken'))
        self.assertEqual(self.declaration.stat().st_size, len(original))
        with self.assertRaisesRegex(ValueError, 'digest changed'):
            dep.scan(self.index, [self.source])

    def test_scan_rejects_wrong_serialized_owner(self):
        self.exports[0]['Package'] = '/Other/Impostor'
        self.write_receipt()
        with self.assertRaisesRegex(ValueError, 'different package'):
            dep.scan(self.index, [self.source])

    def test_reuse_requires_same_index_mapping_receipt_and_files(self):
        for field in ('input_job_sha256', 'mapping_sha256'):
            changed = dict(self.receipt, **{field: 'f'*64})
            (self.directory/'conversion-result.json').write_text(json.dumps(changed), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'receipt'):
                dep.source_records([self.source], disk.digest(self.index))
        self.write_receipt()
        with self.assertRaisesRegex(ValueError, 'Different package index'):
            dep.source_records([self.source], '0'*64)
        self.declaration.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing or changed'):
            dep.source_records([self.source], disk.digest(self.index))

    def test_dependency_plan_exact_frontier_and_no_silent_substitution(self):
        result = dep.scan(self.index, [self.source])
        scan = self.root/'scan.json'
        disk.write_new(scan, result)
        target = self.root/'frontier'
        plan = dep.dependencies(self.index, self.mapping, scan, target)
        self.assertEqual({r['package'] for r in plan['packages']}, set(self.paths[3:]))
        self.assertEqual(plan['provenance']['dependency_scan_sha256'], disk.digest(scan))
        result['pending_dependencies'][0]['package'] = 'ProjectPBZ/Content/Impostor.uasset'
        scan.write_text(json.dumps(result), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Exact indexed'):
            dep.dependencies(self.index, self.mapping, scan, self.root/'bad-frontier')

    def test_empty_plan_and_path_traversal_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'empty plan'):
            dep.create_plan(self.index, self.mapping, self.root/'empty', [], {}, 'empty')
        self.assertEqual(list(dep.referenced_packages(['ClassOnly', '/Game/../Secret.Asset',
            '/Game/Folder/Thing.0', "BlueprintGeneratedClass'/Game/BP_Test.BP_Test_C'"])),
            ['/Game/Folder/Thing', '/Game/BP_Test'])

    def test_absent_timeline_and_explicit_empty_are_distinct(self):
        package = dep.native_package(self.paths[0])
        exports = [dict(Type='GA_Attack_C', Name='Default__GA_Attack_C', Properties={}),
            dict(Type='LegoAbilityBlueprintGeneratedClass', Name='GA_Attack_C', Package=package,
                 ClassDefaultObject=dict(ObjectName="GA_Attack_C'Default__GA_Attack_C'", ObjectPath=package+'.0'))]
        missing, = dep.ability_summaries(exports, package)
        self.assertEqual(missing['timeline_override'], 'missing_inherits')
        self.assertTrue(missing['cdo_resolved'])
        self.assertEqual(missing['issues'], [])
        exports[1]['Properties'] = dict(AbilityTimelines=[])
        empty, = dep.ability_summaries(exports, package)
        self.assertEqual(empty['timeline_override'], 'explicit_empty')
        self.assertFalse(empty['playable'])

    def test_partial_source_keeps_failure_out_of_verified_packages(self):
        self.receipt['passed'] = False
        self.receipt['packages'][0] = dict(package=self.paths[0], passed=False, error='oversized test dependency')
        receipt = self.directory/'conversion-result.json'
        receipt.write_text(json.dumps(self.receipt), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Complete exact'):
            dep.source_records([self.source], disk.digest(self.index))
        verified, identities, _ = dep.source_records([self.source], disk.digest(self.index), allow_incomplete=True)
        self.assertEqual(verified, {})
        self.assertEqual(identities[0]['failed_packages'], [self.paths[0]])
        result = dep.scan(self.index, [self.source], allow_incomplete=True)
        self.assertEqual(result['failed_dependency_count'], 1)
        self.assertFalse(result['indexed_package_closure_complete'])

    def test_collector_preserves_failed_batch_and_continues_independent_batch(self):
        self.receipt['passed'] = False
        self.receipt['packages'][0] = dict(package=self.paths[0], passed=False, error='preserved test failure')
        receipt = self.directory/'conversion-result.json'
        receipt.write_text(json.dumps(self.receipt), encoding='utf-8')
        before = receipt.read_bytes()
        filename = 'job-0001.json'
        disk.write_new(self.source/filename, dict(mode='declarations', game='GAME_UE5_7',
            usmap=str(self.mapping), packages=[self.paths[1]]))
        batch = dict(job=filename, sha256=disk.digest(self.source/filename), packages=[self.paths[1]], output='batch-0001')
        self.plan['batches'].append(batch)
        self.plan['packages'].append(dict(package=self.paths[1], folder='QiShu'))
        (self.source/'plan.json').write_text(json.dumps(self.plan), encoding='utf-8')
        exporter, crypto, paks = self.root/'tool.dll', self.root/'private.json', self.root/'paks'
        exporter.write_bytes(b'test'); crypto.write_bytes(b'test'); paks.mkdir()
        def convert(command, **options):
            directory = Path(command[-1])
            declaration = directory/'declaration-0000.json'
            declaration.write_text('[{"Type":"DataAsset"}]', encoding='utf-8')
            disk.write_new(directory/'conversion-result.json', dict(mode='declarations', game_started=False,
                passed=True, input_job_sha256=batch['sha256'], mapping_sha256=disk.digest(self.mapping),
                tool_sha256='a'*64, packages=[dict(package=self.paths[1], passed=True,
                declaration_file=declaration.name, declaration_sha256=disk.digest(declaration),
                declaration_bytes=declaration.stat().st_size, exports=[dict(type='DataAsset', name='Test')])]))
            return type('Result', (), {'returncode': 0})()
        with patch.object(dep.subprocess, 'run', side_effect=convert) as process:
            result = dep.collect(self.source, exporter, paks, crypto)
        self.assertEqual((result['extracted'], result['failed'], result['pending']), (1, 1, 0))
        self.assertEqual(process.call_count, 1)
        self.assertEqual(receipt.read_bytes(), before)

    def test_inherited_timeline_requires_exact_export_identity_and_honors_empty(self):
        base = dict(class_path='/Game/GA_Base.GA_Base_C', export_index=4,
            export_type='LegoAbilityBlueprintGeneratedClass', timeline_override='declared', declared_actions=7)
        child = dict(class_path='/Game/GA_Child.GA_Child_C', export_index=2,
            export_type='LegoAbilityBlueprintGeneratedClass', timeline_override='missing_inherits', declared_actions=0,
            serialized_super=dict(ObjectName="LegoAbilityBlueprintGeneratedClass'GA_Base_C'", ObjectPath='/Game/GA_Base.4'))
        rows = [dict(abilities=[base, child])]
        counts = dep.resolve_timeline_inheritance(rows)
        self.assertEqual(counts, dict(inherited_declared=1, own_declared=1))
        self.assertEqual(child['effective_declared_actions'], 7)
        base['timeline_override'] = 'explicit_empty'; base['declared_actions'] = 0
        dep.resolve_timeline_inheritance(rows)
        self.assertEqual(child['timeline_resolution'], 'inherited_empty')
        self.assertEqual(child['effective_declared_actions'], 0)
        child['serialized_super']['ObjectPath'] = '/Game/GA_Base.99'
        dep.resolve_timeline_inheritance(rows)
        self.assertEqual(child['timeline_resolution'], 'super_identity_mismatch')
        self.assertIsNone(child['effective_declared_actions'])

    def test_native_defaults_and_inheritance_cycles_remain_unresolved(self):
        ability = dict(class_path='/Game/GA_Loop.GA_Loop_C', export_index=0,
            export_type='BlueprintGeneratedClass', timeline_override='missing_inherits', declared_actions=0,
            serialized_super=dict(ObjectName="BlueprintGeneratedClass'GA_Loop_C'", ObjectPath='/Game/GA_Loop.0'))
        rows = [dict(abilities=[ability])]
        self.assertEqual(dep.resolve_timeline_inheritance(rows), dict(inheritance_cycle=1))
        self.assertIsNone(ability['effective_timeline_class'])
        ability['serialized_super'] = dict(ObjectName="Class'LegoAbility'", ObjectPath='/Script/LegoAbility')
        self.assertEqual(dep.resolve_timeline_inheritance(rows), dict(native_default_unobserved=1))


if __name__ == '__main__':
    unittest.main()
