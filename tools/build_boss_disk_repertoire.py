"""Build a local Boss skill catalog from frozen disk declarations and historical evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import boss_disk_declarations as disk
import boss_disk_dependencies as dependencies
import boss_disk_scripts as scripts
from boss_disk_skill_index import abilities


def read_verified(path, expected):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f'Frozen input changed: {path}')
    return json.loads(data)


def superclass(export):
    first, second = export.get('Super'), export.get('SuperStruct')
    if first and second and first != second:
        raise ValueError(f"Conflicting parent fields for {export['Name']}")
    return first or second


def script_index(scan):
    """Bind each script receipt to the same declaration used by the catalog."""
    expected = {row['package']: row for row in scan['packages'] if row['function_count']}
    result = {}
    for source in scan['script_sources']:
        directory, plan = scripts.checked_plan(source['path'])
        if (disk.digest(directory/'plan.json') != source['plan_sha256']
                or plan['mapping_sha256'] != scan['mapping_sha256']):
            raise ValueError('Script source changed after terminal scan')
        planned = {row['package']: row for row in plan['packages']}
        counts = {name: row['functions'] for name, row in planned.items()}
        for batch in plan['batches']:
            for row in scripts.checked_batch(directory, batch, counts):
                name = row['package']
                declaration = expected.get(name)
                if (declaration is None or name in result or row['passed'] is not True
                        or declaration['function_count'] != row['functions']
                        or declaration['declaration_sha256'] != planned[name]['declaration_sha256']):
                    raise ValueError(f'Script does not match verified declaration: {name}')
                result[name] = dict(path=str(directory/batch['output']/row['script_file']),
                                    sha256=row['sha256'], functions=row['functions'],
                                    complete_functions=row['complete_functions'],
                                    unresolved_functions=row['unresolved_functions'])
    if result.keys() != expected.keys():
        raise ValueError('Terminal scan has missing script receipts')
    if sum(row['unresolved_functions'] for row in result.values()) != scan['unresolved_script_functions']:
        raise ValueError('Terminal scan and script receipts disagree on decode gaps')
    return result


def build(workflow_path, queue_path, output):
    workflow_path, queue_path, output = map(Path, (workflow_path, queue_path, output))
    workflow_sha = disk.digest(workflow_path)
    workflow = read_verified(workflow_path, workflow_sha)
    last = workflow['rounds'][-1]
    scan_path = Path(workflow['final_scan'])
    if (workflow['kind'] != 'offline_boss_dependency_workflow_result'
            or workflow['bounded_traversal_completed'] is not True
            or workflow['game_started'] is not False or not last['terminal']
            or last['pending_dependencies'] or last['new_script_packages']
            or scan_path.resolve().parent != workflow_path.resolve().parent
            or last['scan'] != scan_path.name or last['scan_sha256'] != workflow['final_scan_sha256']):
        raise ValueError('Completed offline capture required')
    scan = read_verified(scan_path, workflow['final_scan_sha256'])
    if (scan['kind'] != 'offline_native_dependency_scan' or not scan['declaration_contents_verified']
            or scan['root_packages'] != scan['extracted_roots'] or scan['pending_roots']
            or scan['pending_dependency_count']):
        raise ValueError('Verified Boss roots and completed dependency traversal required')
    queue_sha = disk.digest(queue_path)
    queue = read_verified(queue_path, queue_sha)
    if (queue['kind'] != 'dependency_disk_and_closed_native_skill_coverage'
            or queue['dependency_workflow_sha256'] != workflow_sha
            or queue['disk_dependency_scan_sha256'] != workflow['final_scan_sha256']):
        raise ValueError('Adaptation queue belongs to a different capture')
    indexed = {row['class_path']: row for row in queue['rows']}
    if len(indexed) != len(queue['rows']):
        raise ValueError('Duplicate ability in adaptation queue')
    if any(row[key] is not False for row in queue['rows'] + queue['quarantined_rows']
           for key in ('current_process_grant_verified', 'activation_allowed', 'playable')):
        raise ValueError('Offline-only ability rows required')

    catalog = {}
    root_counts = Counter()
    root_gaps = []
    parent_fields_recovered = 0
    all_rows = {}
    quarantined = Counter()
    for package in scan['packages']:
        native_root = package['package'].startswith(dependencies.MOBS)
        if native_root:
            folder = package['folder']
            catalog.setdefault(folder, [])
            root_counts[folder] += 1
            root_gaps.extend(dict(reference, package=package['package'], folder=folder,
                                  has_ability=bool(package['abilities']))
                             for reference in package['references']
                             if reference['status'] not in ('native_code', 'extracted'))
        missing_parent = any(row['serialized_super'] is None for row in package['parent_classes'])
        if not package['abilities'] and not missing_parent:
            continue
        exports = read_verified(package['declaration'], package['declaration_sha256'])
        package_id = dependencies.native_package(package['package'])
        parent_by_index = {}
        for row in package['parent_classes']:
            export = exports[row['export_index']]
            identity = export['Package'] + '.' + export['Name']
            if identity != row['class_path'] or export['Type'] != row['export_type']:
                raise ValueError(f'Native export identity mismatch: {identity}')
            parent = superclass(export)
            if row['serialized_super'] is None and parent is not None:
                parent_fields_recovered += 1
            row['serialized_super'] = parent
            parent_by_index[row['export_index']] = parent
        if not package['abilities']:
            continue
        parsed = {row['export_index']: row for row in abilities(exports, package_id, include_native_types=True)}
        for row in package['abilities']:
            original = parsed[row['export_index']]
            if (original['class_path'] != row['class_path'] or original['issues'] != row['issues']
                    or sum(len(timeline['actions']) for timeline in original['timelines']) != row['declared_actions']):
                raise ValueError(f'Skill declaration differs from scan: {package_id}')
            if row['issues'] or not row['class_path']:
                quarantined[row['class_path'], package['declaration_sha256']] += 1
                continue
            row['serialized_super'] = parent_by_index[row['export_index']]
            path = row['class_path']
            if path in all_rows or indexed[path]['disk_declaration_sha256'] != package['declaration_sha256']:
                raise ValueError(f'Skill evidence differs from queue: {path}')
            all_rows[path] = (package, row, original['timelines'])
            if native_root:
                catalog[package['folder']].append(path)

    quarantined_in_queue = Counter((row['class_path'], row['disk_declaration_sha256'])
                                   for row in queue['quarantined_rows'])
    if (sum(root_counts.values()) != scan['root_packages'] or 'native_support' in catalog
            or all_rows.keys() != indexed.keys() or quarantined != quarantined_in_queue
            or len(all_rows) + len(queue['quarantined_rows']) != scan['ability_classes']):
        raise ValueError('Skill catalog does not cover the frozen capture')
    inheritance = dependencies.resolve_timeline_inheritance(scan['packages'])
    scripts_by_package = script_index(scan)
    summary = dict(schema=1, kind='offline_boss_disk_repertoire', workflow_sha256=workflow_sha,
                   scan_sha256=workflow['final_scan_sha256'], queue_sha256=queue_sha,
                   tool_sha256=disk.digest(__file__), root_packages=scan['root_packages'],
                   folders=len(catalog), boss_npc_abilities=sum(map(len, catalog.values())),
                   ability_classes=scan['ability_classes'], timeline_inheritance=inheritance,
                   parent_fields_recovered=parent_fields_recovered, quarantined=len(queue['quarantined_rows']),
                   script_packages=len(scripts_by_package),
                   function_exports=sum(row['functions'] for row in scripts_by_package.values()),
                   complete_functions=sum(row['complete_functions'] for row in scripts_by_package.values()),
                   unresolved_functions=sum(row['unresolved_functions'] for row in scripts_by_package.values()),
                   capture_gaps=queue['capture_gaps'], files={}, game_started=False,
                   computer_use_used=False, installed=False, activation_allowed=False,
                   playable=False, all_boss_skills_complete=False, ready_for_mod_delivery=False)
    output.mkdir(parents=True, exist_ok=False)
    timelines = {path: dict(declaration_sha256=package['declaration_sha256'], timelines=declared)
                 for path, (package, row, declared) in sorted(all_rows.items())
                 if row['timeline_override'] in ('declared', 'explicit_empty')}
    disk.write_new(output/'timelines.json', timelines)
    summary['files']['timelines.json'] = disk.digest(output/'timelines.json')
    disk.write_new(output/'scripts.json', scripts_by_package)
    summary['files']['scripts.json'] = disk.digest(output/'scripts.json')

    support = [path for path, (package, _, _) in all_rows.items()
               if not package['package'].startswith(dependencies.MOBS)]
    for folder, paths in sorted({**catalog, 'native_support': support}.items()):
        if not folder or not folder.replace('_', '').isalnum():
            raise ValueError(f'Unexpected Boss folder: {folder}')
        skills = []
        for path in sorted(paths):
            package, row, _ = all_rows[path]
            evidence = indexed[path]
            owner = row['effective_timeline_class']
            skills.append(dict(class_path=path, package=package['package'], declaration=package['declaration'],
                               declaration_sha256=package['declaration_sha256'], export_index=row['export_index'],
                               serialized_super=row['serialized_super'],
                               timeline_resolution=row['timeline_resolution'], timeline_owner=owner,
                               timeline_available=owner in timelines, declared_actions=row['effective_declared_actions'],
                               direct_script_available=package['package'] in scripts_by_package,
                               native_route=evidence['native_route'], next_action=evidence['next_action'],
                               historical_unique_grants=evidence['historical_unique_grants'],
                               activation_allowed=False, playable=False))
        name = f'{folder}.json'
        disk.write_new(output/name, dict(folder=folder, root_packages=root_counts[folder], skills=skills,
                                         native_routes=dict(Counter(row['native_route'] for row in skills))))
        summary['files'][name] = disk.digest(output/name)
    summary['boss_npc_direct_reference_gaps'] = dict(Counter(row['status'] for row in root_gaps))
    disk.write_new(output/'root-reference-gaps.json', root_gaps)
    summary['files']['root-reference-gaps.json'] = disk.digest(output/'root-reference-gaps.json')
    disk.write_new(output/'quarantined.json', queue['quarantined_rows'])
    summary['files']['quarantined.json'] = disk.digest(output/'quarantined.json')
    disk.write_new(output/'summary.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workflow', type=Path)
    parser.add_argument('queue', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = build(args.workflow, args.queue, args.output)
    print(json.dumps({key: value for key, value in result.items() if key != 'files'}, ensure_ascii=False))
