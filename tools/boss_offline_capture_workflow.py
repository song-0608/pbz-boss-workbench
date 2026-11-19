"""Converge explicit native disk dependencies without game/editor/computer use."""
import argparse
import json
from pathlib import Path

import boss_disk_declarations as disk
import boss_disk_dependencies as dependencies
import boss_disk_scripts as scripts


def capture(index, mapping, source_dirs, script_dirs, target, exporter, script_exporter,
            paks, crypto, *, max_rounds=12, defer_cinematic_cache=True, reuse_scan=None):
    index, mapping, target = Path(index).resolve(), Path(mapping).resolve(), Path(target).resolve()
    exporter, script_exporter = Path(exporter).resolve(), Path(script_exporter).resolve()
    paks, crypto = Path(paks).resolve(), Path(crypto).resolve()
    if not 1 <= max_rounds <= 16:
        raise ValueError('Expected 1-16 bounded offline rounds')
    if (not all(p.is_file() for p in (index, mapping, exporter, script_exporter, crypto))
            or not paks.is_dir() or target == paks or paks in target.parents):
        raise ValueError('Existing local inputs and new output outside game packages required')
    sources = [Path(p).resolve() for p in source_dirs]
    script_sources = [Path(p).resolve() for p in script_dirs]
    initial_scan=Path(reuse_scan).resolve() if reuse_scan is not None else None
    initial_scan_sha256=disk.digest(initial_scan) if initial_scan is not None else None
    previous_scan=initial_scan
    if not sources:
        raise ValueError('Explicit existing declaration sources required')
    # A separate immutable run never overwrites a failed or unfinished run.
    target.mkdir(parents=True, exist_ok=False)
    identities = {name: disk.digest(path) for name, path in (
        ('index', index), ('mapping', mapping), ('exporter', exporter), ('script_exporter', script_exporter))}
    code = {name: disk.digest(Path(__file__).parent/name) for name in (
        'boss_offline_capture_workflow.py', 'boss_disk_declarations.py',
        'boss_disk_dependencies.py', 'boss_disk_skill_index.py', 'boss_disk_scripts.py','boss_disk_scan_cache.py')}
    disk.write_new(target/'workflow.json', dict(schema=1, kind='offline_boss_dependency_workflow',
        identities=identities, source_sha256=code,
        initial_sources=[str(p) for p in sources], initial_script_sources=[str(p) for p in script_sources],
        max_rounds=max_rounds, defer_cinematic_cache=defer_cinematic_cache,
        initial_scan=str(initial_scan) if initial_scan is not None else None,
        initial_scan_sha256=initial_scan_sha256,
        game_started=False, computer_use_used=False, installed=False))
    rounds = []
    for ordinal in range(1, max_rounds+1):
        for name, path in (('index', index), ('mapping', mapping), ('exporter', exporter), ('script_exporter', script_exporter)):
            if disk.digest(path) != identities[name]:
                raise ValueError('Pinned offline input changed: '+name)
        if any(disk.digest(Path(__file__).parent/name) != sha for name, sha in code.items()):
            raise ValueError('Offline workflow source changed during capture')
        if initial_scan is not None and disk.digest(initial_scan)!=initial_scan_sha256:
            raise ValueError('Pinned initial scan changed during capture')
        report = dependencies.scan(index, sources, script_sources, allow_incomplete=True,
                                   defer_cinematic_cache=defer_cinematic_cache,reuse_scan=previous_scan)
        scan = target/f'scan-{ordinal:04d}.json'
        disk.write_new(scan, report)
        previous_scan=scan
        existing_scripts = set()
        for directory in script_sources:
            _, plan = scripts.checked_plan(directory)
            existing_scripts.update(r['package'].casefold() for r in plan['packages'])
        missing_scripts = [r for r in report['packages'] if r['function_count']
                           and r['package'].casefold() not in existing_scripts]
        row = dict(round=ordinal, scan=scan.name, scan_sha256=disk.digest(scan),
            verified_packages=report['extracted_packages'], pending_dependencies=report['pending_dependency_count'],
            known_failed_dependencies=report['failed_dependency_count'], new_script_packages=len(missing_scripts),
            deferred_dependencies=report.get('deferred_dependency_count',0))
        row.update(reused_parsed_packages=report.get('reused_parsed_packages',0),
                   newly_parsed_packages=report.get('newly_parsed_packages',report['extracted_packages']))
        if not report['pending_dependency_count'] and not missing_scripts:
            status = ('converged_with_known_gaps' if report['failed_dependency_count']
                      or report['unindexed_references'] or report['unresolved_script_functions']
                      or report['ability_indexing_issues'] or report.get('deferred_dependency_count',0)
                      else 'converged_indexed_dependencies')
            row['terminal'] = True
            rounds.append(row)
            disk.write_new(target/f'round-{ordinal:04d}.json', row)
            break
        row['terminal'] = False
        if report['pending_dependency_count']:
            directory = target/f'declarations-{ordinal:04d}'
            dependencies.dependencies(index, mapping, scan, directory)
            extracted = dependencies.collect(directory, exporter, paks, crypto)
            row['declarations'] = dict(directory=directory.name, extracted=extracted['extracted'],
                                       failed=extracted['failed'], pending=extracted['pending'])
            sources.append(directory)
        if missing_scripts:
            directory = target/f'scripts-{ordinal:04d}'
            scripts.plan(scan, mapping, directory, script_sources)
            extracted = scripts.run(directory, script_exporter, paks, crypto)
            row['scripts'] = dict(directory=directory.name, extracted=extracted['extracted'],
                complete_functions=extracted['complete_functions'], unresolved_functions=extracted['unresolved_functions'])
            script_sources.append(directory)
        rounds.append(row)
        disk.write_new(target/f'round-{ordinal:04d}.json', row)
        print(json.dumps(row), flush=True)
    else:
        status = 'round_limit_reached'
    result = dict(schema=1, kind='offline_boss_dependency_workflow_result', status=status,
        bounded_traversal_completed=status != 'round_limit_reached',
        final_scan=str(scan), final_scan_sha256=disk.digest(scan), rounds=rounds,
        declaration_sources=[str(p) for p in sources], script_sources=[str(p) for p in script_sources],
        root_packages=report['root_packages'], extracted_roots=report['extracted_roots'],
        ability_classes=report['ability_classes'], declared_actions=report['declared_actions'],
        known_failed_dependencies=report['failed_dependency_count'],
        deferred_dependencies=report.get('deferred_dependency_count',0),
        dependency_policy=report.get('dependency_policy','all_serialized_references'),
        unindexed_reference_count=len(report['unindexed_references']),
        unresolved_script_functions=report['unresolved_script_functions'],
        ability_indexing_issues=report['ability_indexing_issues'],
        game_started=False, computer_use_used=False, installed=False,
        live_grant_verified=False, execution_verified=False,
        all_boss_skills_complete=False, ready_for_final_delivery=False)
    disk.write_new(target/'result.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('rounds', 'declaration_sources', 'script_sources')}, ensure_ascii=False), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('index', 'mapping', 'target', 'exporter', 'script-exporter', 'paks', 'crypto'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source', type=Path, action='append', required=True)
    parser.add_argument('--script-source', type=Path, action='append', default=[])
    parser.add_argument('--max-rounds', type=int, default=12)
    parser.add_argument('--include-cinematic-cache', action='store_true',
                        help='Explicitly include global cinematic prestream caches in the traversal')
    parser.add_argument('--reuse-scan',type=Path)
    args = parser.parse_args()
    capture(args.index, args.mapping, args.source, args.script_source, args.target,
            args.exporter, args.script_exporter, args.paks, args.crypto, max_rounds=args.max_rounds,
            defer_cinematic_cache=not args.include_cinematic_cache,reuse_scan=args.reuse_scan)
