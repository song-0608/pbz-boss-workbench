"""Exercise the catalog join and parent fallback without game files."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import boss_disk_declarations as disk
import boss_disk_dependencies as dep
import build_boss_disk_repertoire as repertoire


class RepertoireTests(unittest.TestCase):
    def test_superstruct_only_child_resolves_the_verified_shared_timeline(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scans = []
            paths = ('ProjectPBZ/Content/GA_Shared.uasset', dep.MOBS + 'Fixture/GA_Child.uasset')
            class_type = 'LegoAbilityBlueprintGeneratedClass'
            for path, leaf, folder in zip(paths, ('GA_Shared', 'GA_Child'), ('native_support', 'Fixture')):
                package = dep.native_package(path)
                name = leaf + '_C'
                original = dict(Type=class_type, Name=name, Package=package,
                                ClassDefaultObject=dict(ObjectName=f"{name}'Default__{name}'", ObjectPath=package + '.1'))
                exports = [original, dict(Type=name, Name='Default__' + name)]
                if folder == 'Fixture':
                    original['SuperStruct'] = dict(ObjectName=f"{class_type}'GA_Shared_C'", ObjectPath='/Game/GA_Shared.0')
                else:
                    original['Properties'] = dict(AbilityTimelines=[dict(ObjectName="LGATimeline'Timeline'",
                                                                           ObjectPath=package + '.2')])
                    exports.append(dict(Type='LGATimeline', Name='Timeline', Properties={'Actions': []}))
                file = root / f'{leaf}.json'
                disk.write_new(file, exports)
                scans.append(dict(package=path, folder=folder, declaration=str(file), declaration_sha256=disk.digest(file),
                                  parent_classes=dep.parent_class_summaries(exports, package),
                                  abilities=dep.ability_summaries(exports, package), references=[], function_count=0))
            scans[1]['references'] = [dict(reference='/Example/FX', status='not_in_uasset_index')]
            scan = root / 'scan-0001.json'
            disk.write_new(scan, dict(kind='offline_native_dependency_scan', declaration_contents_verified=True,
                                     root_packages=1, extracted_roots=1, pending_roots=0, pending_dependency_count=0,
                                     ability_classes=2, packages=scans, script_sources=[], unresolved_script_functions=0))
            result = root / 'result.json'
            sha = disk.digest(scan)
            disk.write_new(result, dict(kind='offline_boss_dependency_workflow_result', bounded_traversal_completed=True,
                                       game_started=False, final_scan=str(scan), final_scan_sha256=sha,
                                       rounds=[dict(scan=scan.name, scan_sha256=sha, pending_dependencies=0,
                                                    new_script_packages=0, terminal=True)]))
            queue = root / 'queue.json'
            disk.write_new(queue, dict(kind='dependency_disk_and_closed_native_skill_coverage',
                                       dependency_workflow_sha256=disk.digest(result), disk_dependency_scan_sha256=sha,
                                       capture_gaps={}, quarantined_rows=[], rows=[
                                           dict(class_path=p['abilities'][0]['class_path'],
                                                disk_declaration_sha256=p['declaration_sha256'], native_route='unverified',
                                                next_action='review', historical_unique_grants=[],
                                                current_process_grant_verified=False, activation_allowed=False, playable=False)
                                           for p in scans]))
            report = repertoire.build(result, queue, root / 'catalog')
            self.assertEqual(report['parent_fields_recovered'], 1)
            self.assertEqual(report['timeline_inheritance'], {'inherited_declared': 1, 'own_declared': 1})
            path = root / 'catalog/Fixture.json'
            catalog = repertoire.read_verified(path, report['files'][path.name])
            self.assertEqual(catalog['root_packages'], 1)
            skill, = catalog['skills']
            self.assertEqual(skill['timeline_owner'], '/Game/GA_Shared.GA_Shared_C')
            self.assertTrue(skill['timeline_available'])
            self.assertFalse(skill['playable'])
            path = root / 'catalog/root-reference-gaps.json'
            gap, = repertoire.read_verified(path, report['files'][path.name])
            self.assertEqual(gap['reference'], '/Example/FX')
            self.assertTrue(gap['has_ability'])
            Path(scans[0]['declaration']).write_text('[]', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
                repertoire.build(result, queue, root / 'tampered')
