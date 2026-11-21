"""Expand native NPC declarations and trace exact serialized dependencies offline.

The catalog is an inventory of disk packages, not a roster of playable bosses.
All output is immutable metadata. No game, editor, input, or live grant API is used.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import copy
import csv
import hashlib
from itertools import islice
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

import boss_disk_declarations as disk
import boss_disk_skill_index as skill_index
import boss_disk_scan_cache as scan_cache

MOBS = 'ProjectPBZ/Plugins/Secret/PBZCombatAsset/Content/ActorData/Mobs/'
CINEMATIC_PRESTREAM = '/Game/Cinematics/Prestreaming/'
SOURCES = ('boss_disk_declarations.py', 'boss_disk_dependencies.py', 'boss_disk_skill_index.py',
           'boss_disk_scripts.py', 'boss_disk_scan_cache.py')
PATH_TOKEN = re.compile(r"^(?:(?:/[A-Za-z0-9_/]+\.)?[A-Za-z_][A-Za-z0-9_]*')?(/[A-Za-z0-9_/-]+)(?:\.[A-Za-z0-9_:.-]+)?'?$" )


def native_package(path):
    """Translate a catalog mount, never guess an asset from its short name."""
    parts = PurePosixPath(path).parts
    if ('\\' in path or ':' in path or '..' in parts or not path.endswith('.uasset')
            or path.startswith('/') or 'Content' not in parts):
        raise ValueError('Expected a relative indexed asset path')
    position = parts.index('Content')
    prefix = parts[:position]
    if prefix == ('ProjectPBZ',):
        mount = 'Game'
    elif prefix == ('Engine',):
        mount = 'Engine'
    elif (len(prefix) >= 3 and prefix[0] in ('ProjectPBZ', 'Engine')
          and prefix[1] == 'Plugins'):
        mount = prefix[-1]
    else:
        raise ValueError('Unrecognized native content mount')
    return '/' + mount + '/' + '/'.join(parts[position+1:])[:-7]


def catalog(index):
    result = {}
    with Path(index).open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream, skipinitialspace=True):
            raw = row.get('Filename', '').strip()
            if (not raw.startswith('../../../') or not raw.endswith('.uasset')
                    or row.get('ChunkType', '').strip() != 'ExportBundleData'):
                continue
            path = raw[len('../../../'):]
            try:
                package = native_package(path)
            except ValueError:
                continue
            item = dict(package=path, native_package=package,
                        package_hash=row.get('Hash', '').strip())
            key = package.casefold()
            if key in result and result[key] != item:
                raise ValueError('Ambiguous indexed native package: ' + package)
            result[key] = item
    if not result:
        raise ValueError('Nonempty exact package index required')
    return result


def source_records(sources, index_sha256, *, allow_incomplete=False):
    """Validate jobs and receipt identities before planning reuse.

    Declaration contents are checked when scanning. A roots plan's reuse list
    is deliberately not a certificate that dependencies or extraction are done.
    """
    result, identities = {}, []
    mapping_sha256 = None
    for source in sources:
        source, plan = disk.checked_plan(source)
        if plan['index_sha256'] != index_sha256:
            raise ValueError('Different package index; cannot reuse declarations')
        if mapping_sha256 is not None and mapping_sha256 != plan['mapping_sha256']:
            raise ValueError('Different exact type mappings in sources')
        mapping_sha256 = plan['mapping_sha256']
        identity = dict(path=str(source), plan_sha256=disk.digest(source/'plan.json'),
                        failed_packages=[], pending_packages=[], incomplete_batches=[])
        identities.append(identity)
        for batch in plan['batches']:
            receipt = source/batch['output']/'conversion-result.json'
            if not receipt.is_file():
                if not allow_incomplete:
                    raise ValueError('Complete exact declaration receipt required')
                identity['pending_packages'].extend(batch['packages'])
                if receipt.parent.exists():
                    identity['incomplete_batches'].append(batch['output'])
                continue
            report = json.loads(receipt.read_bytes())
            job = json.loads((source/batch['job']).read_bytes())
            if (report.get('mode') != 'declarations' or report.get('game_started') is not False
                    or report.get('passed') is not all(r.get('passed') is True for r in report['packages'])
                    or report.get('input_job_sha256') != batch['sha256']
                    or report.get('mapping_sha256') != plan['mapping_sha256']
                    or not re.fullmatch('[0-9a-f]{64}', report.get('tool_sha256', ''))
                    or [r['package'] for r in report['packages']] != job['packages']):
                raise ValueError('Complete exact declaration receipt required')
            for row in report['packages']:
                if row.get('passed') is not True:
                    if not allow_incomplete:
                        raise ValueError('Complete exact declaration receipt required')
                    identity['failed_packages'].append(row['package'])
                    continue
                filename = row.get('declaration_file', '')
                if (not re.fullmatch(r'declaration-[0-9]{4}\.json', filename)
                        or not re.fullmatch('[0-9a-f]{64}', row.get('declaration_sha256', ''))):
                    raise ValueError('Complete bounded declaration required')
                path = source/batch['output']/filename
                if (path.is_symlink() or not path.is_file()
                        or not 0 < path.stat().st_size == row['declaration_bytes'] <= disk.MAX_BYTES):
                    raise ValueError('Missing or changed declaration size')
                key = native_package(row['package']).casefold()
                item = dict(package=row['package'], declaration=str(path),
                            declaration_sha256=row['declaration_sha256'],
                            declaration_bytes=row['declaration_bytes'])
                if key in result and result[key]['declaration_sha256'] != item['declaration_sha256']:
                    raise ValueError('Conflicting declaration sources: '+row['package'])
                result.setdefault(key, item)
    return result, identities, mapping_sha256


def collect(target, exporter, paks, crypto):
    """Finish independent batches while preserving failed packages without retry.

    Unlike the strict first-batch runner, one unsupported visual dependency
    does not stop extraction of unrelated skills. Failures remain failures.
    """
    target, record = disk.checked_plan(target)
    exporter, paks, crypto = Path(exporter).resolve(), Path(paks).resolve(), Path(crypto).resolve()
    if (not exporter.is_file() or not paks.is_dir() or not crypto.is_file()
            or target == paks or paks in target.parents):
        raise ValueError('Existing local inputs and separate output required')
    for batch in record['batches']:
        directory = target/batch['output']
        if directory.exists():
            # Includes the original failing receipt; never overwrite/retry it.
            disk.checked_batch(target, batch)
            continue
        directory.mkdir()
        with (target/(batch['output']+'.log')).open('x', encoding='utf-8') as log:
            result = subprocess.run(['dotnet', str(exporter), str(paks), str(crypto),
                str(target/batch['job']), str(directory)], stdout=log, stderr=subprocess.STDOUT, timeout=180)
        rows = disk.checked_batch(target, batch)
        failures = sum(r.get('passed') is not True for r in rows)
        if result.returncode not in (0, 1) or (result.returncode == 0) != (failures == 0):
            raise ValueError('Exporter process status mismatch; preserve local diagnostics')
        print(json.dumps(dict(batch=batch['output'], packages=len(rows), failed=failures)), flush=True)
    return disk.summarize(target)


def create_plan(index, mapping, target, rows, provenance, purpose):
    target, mapping = Path(target).resolve(), Path(mapping).resolve()
    if not rows:
        raise ValueError('No missing indexed packages; do not create an empty plan')
    if not mapping.is_file():
        raise ValueError('Existing exact local mapping required')
    target.mkdir(parents=True, exist_ok=False)
    batches = []
    for offset in range(0, len(rows), 64):
        ordinal = offset//64
        job = f'job-{ordinal:04d}.json'
        packages = [r['package'] for r in rows[offset:offset+64]]
        disk.write_new(target/job, dict(mode='declarations', game='GAME_UE5_7',
                       usmap=str(mapping), packages=packages))
        batches.append(dict(job=job, sha256=disk.digest(target/job), packages=packages,
                            output=f'batch-{ordinal:04d}'))
    record = dict(schema=1, kind='offline_boss_disk_declarations', purpose=purpose,
        index_sha256=disk.digest(index), mapping_sha256=disk.digest(mapping),
        sources={name: disk.digest(Path(__file__).parent/name) for name in SOURCES},
        provenance=provenance, packages=rows, batches=batches,
        disk_metadata_only=True, complete_package_inventory=False,
        all_boss_skills_complete=False, live_grant_verified=False,
        execution_verified=False, playable=False, game_started=False, installed=False)
    disk.write_new(target/'plan.json', record)
    disk.checked_plan(target)
    return record


def roots(index, mapping, sources, target):
    """Include every indexed Mobs directory, including nonnumeric names.

    Do not filter by Ability/Abilities spelling: weapon, bullet, AI, effect,
    montage and actor declarations are needed to explain native skill context.
    """
    assets = catalog(index)
    existing, identities, expected = source_records(sources, disk.digest(index))
    if expected is not None and expected != disk.digest(mapping):
        raise ValueError('Exact source mapping required')
    rows = []
    for key, row in sorted(assets.items()):
        if row['package'].startswith(MOBS) and key not in existing:
            folder = row['package'][len(MOBS):].split('/', 1)[0]
            rows.append(dict(row, folder=folder))
    return create_plan(index, mapping, target, rows,
        dict(source_plans=identities, reused_package_count=len(existing),
             reused_contents_verified=False, selector='all_indexed_mobs_uasset'),
        'all_native_npc_declarations_including_nonnumeric_folders')


def referenced_packages(value):
    """Keep hard and soft serialized paths; never resolve short names.

    References to export indices, subobjects, packages and soft class strings
    all join on the exact mounted package. Malformed paths stay unresolved.
    """
    if isinstance(value, dict):
        for key, child in value.items():
            # Package is the owning package, not a dependency edge. ObjectPath
            # is handled once, without also counting ObjectName's short token.
            if key not in ('Package', 'ObjectName'):
                yield from referenced_packages(child)
    elif isinstance(value, list):
        for child in value:
            yield from referenced_packages(child)
    elif isinstance(value, str):
        match = PATH_TOKEN.fullmatch(value)
        if match and '..' not in PurePosixPath(match[1]).parts:
            yield match[1]


def ability_summaries(exports, package):
    result = []
    for ability in skill_index.abilities(exports, package, include_native_types=True):
        properties = ability['serialized_class_properties']
        override = properties.get('AbilityTimelines')
        override_kind = ('missing_inherits' if 'AbilityTimelines' not in properties else
                         'invalid' if not isinstance(override, list) else
                         'explicit_empty' if not override else 'declared')
        actions = [action for timeline in ability['timelines'] for action in timeline['actions']]
        result.append(dict(class_path=ability['class_path'],
            export_index=ability['export_index'], export_type=exports[ability['export_index']]['Type'],
            serialized_super=ability['serialized_super'], timeline_override=override_kind,
            cdo_resolved=ability['serialized_cdo_properties'] is not None,
            declared_timelines=len(ability['timelines']), declared_actions=len(actions),
            action_types=dict(Counter(a['action_type'] for a in actions if a['action_type'])),
            issues=ability['issues'], live_grant_verified=False, playable=False))
    return result


def parent_class_summaries(exports, package):
    """Keep plain BP ancestors as context, without labeling actors as abilities."""
    result = []
    for ordinal, obj in enumerate(exports):
        if ('BlueprintGeneratedClass' not in obj.get('Type', '')
                or not isinstance(obj.get('Package'), str)
                or obj['Package'].casefold() != package.casefold()):
            continue
        props = obj.get('Properties', {})
        timelines = props.get('AbilityTimelines')
        override = ('missing_inherits' if 'AbilityTimelines' not in props else
                    'invalid' if not isinstance(timelines, list) else
                    'explicit_empty' if not timelines else 'parent_timeline_not_indexed')
        result.append(dict(class_path=obj['Package']+'.'+obj['Name'],
            export_index=ordinal, export_type=obj['Type'], serialized_super=obj.get('Super'),
            timeline_override=override, declared_actions=0 if override == 'explicit_empty' else None))
    return result


def resolve_timeline_inheritance(packages):
    """Resolve only exact disk class/export identities, preserving empty overrides."""
    abilities = [a for row in packages for a in row['abilities'] if a['class_path']]
    classes = {a['class_path'].casefold(): a for row in packages for a in row.get('parent_classes', [])}
    classes.update({a['class_path'].casefold(): a for a in abilities})
    memo = {}

    def resolve(key, trail):
        if key in memo:
            return memo[key]
        if key in trail:
            return 'inheritance_cycle', None
        if len(trail) >= 128:
            return 'inheritance_depth_limit', None
        ability = classes[key]
        override = ability['timeline_override']
        if override in ('declared', 'explicit_empty'):
            value = ('own_declared' if override == 'declared' else 'own_empty', key)
        elif override == 'invalid':
            value = 'invalid_override', None
        elif override == 'parent_timeline_not_indexed':
            value = 'parent_timeline_not_indexed', None
        else:
            parent = ability.get('serialized_super')
            path = parent.get('ObjectPath', '') if isinstance(parent, dict) else ''
            name = skill_index.OBJECT_NAME.fullmatch(parent.get('ObjectName', '')) if isinstance(parent, dict) else None
            if path.startswith('/Script/'):
                value = 'native_default_unobserved', None
            elif not name or '.' not in path:
                value = 'super_identity_unresolved', None
            else:
                package, ordinal = path.rsplit('.', 1)
                parent_key = (package + '.' + name[2]).casefold()
                match = classes.get(parent_key)
                if match is None:
                    value = 'parent_declaration_missing', None
                elif (not ordinal.isdigit() or int(ordinal) != match['export_index']
                      or name[1] != match['export_type']):
                    value = 'super_identity_mismatch', None
                else:
                    status, origin = resolve(parent_key, trail | {key})
                    value = ('inherited_declared' if status in ('own_declared', 'inherited_declared') else
                             'inherited_empty' if status in ('own_empty', 'inherited_empty') else status, origin)
        memo[key] = value
        return value

    counts = Counter()
    for ability in abilities:
        key = ability['class_path'].casefold()
        status, origin = resolve(key, set())
        ability['timeline_resolution'] = status
        ability['effective_timeline_class'] = classes[origin]['class_path'] if origin else None
        ability['effective_declared_actions'] = classes[origin]['declared_actions'] if origin else None
        counts[status] += 1
    return dict(sorted(counts.items()))


def script_reference_map(sources, declarations, mapping_sha256):
    # Delayed import keeps the extraction planner usable without a script run.
    import boss_disk_scripts as scripts
    result, identities, unresolved = {}, [], 0
    for source in sources:
        source, plan = scripts.checked_plan(source)
        if plan['mapping_sha256'] != mapping_sha256:
            raise ValueError('Script and declaration mappings differ')
        expected = {r['package']: r['functions'] for r in plan['packages']}
        expected_sha = {r['package']: r['declaration_sha256'] for r in plan['packages']}
        identities.append(dict(path=str(source), plan_sha256=disk.digest(source/'plan.json')))
        for batch in plan['batches']:
            for row in scripts.checked_batch(source, batch, expected):
                key = native_package(row['package']).casefold()
                if (row.get('passed') is not True or key not in declarations
                        or declarations[key]['declaration_sha256'] != expected_sha[row['package']]):
                    raise ValueError('Scripts must join the exact verified declaration')
                functions = json.loads((source/batch['output']/row['script_file']).read_bytes())
                result.setdefault(key, set()).update(referenced_packages(functions))
                unresolved += row['unresolved_functions']
    return result, identities, unresolved


def checked_declaration(entry, cached):
    key, item = entry
    data = Path(item['declaration']).read_bytes()
    if hashlib.sha256(data).hexdigest() != item['declaration_sha256']:
        raise ValueError('Declaration digest changed: '+item['package'])
    return key, item, None if cached else data


def verified_declarations(declarations, cache):
    """Overlap bounded disk reads without relaxing per-file digest checks."""
    entries = iter(sorted(declarations.items()))
    with ThreadPoolExecutor(max_workers=8) as readers:
        while batch := list(islice(entries, 32)):
            yield from readers.map(checked_declaration, batch, (key in cache for key, _ in batch))


def scan(index, sources, script_sources=(), *, allow_incomplete=False, defer_cinematic_cache=False,
         reuse_scan=None):
    """One verified read per package; return a reusable local dependency graph."""
    assets = catalog(index)
    existing, identities, mapping = source_records(sources, disk.digest(index), allow_incomplete=allow_incomplete)
    failed_sources = {native_package(p).casefold() for i in identities for p in i['failed_packages']} - existing.keys()
    script_refs, script_identities, unresolved_scripts = script_reference_map(script_sources, existing, mapping)
    source_identities={name:disk.digest(Path(__file__).parent/name) for name in SOURCES}
    cached,cache_identity,reused={},None,0
    types=Counter()
    if reuse_scan is not None:
        cached,types,cache_identity=scan_cache.load(reuse_scan,disk.digest(index),mapping,
            source_identities,script_identities,existing,native_package)
    edges, missing, native, unindexed, deferred = [], set(), set(), set(), set()
    by_folder = Counter()
    ability_count = timeline_count = action_count = issue_count = 0
    for ordinal, (key, item, data) in enumerate(verified_declarations(existing, cached)):
        previous=cached.get(key)
        if previous is not None:
            # Hashing remains mandatory; only parsing is reused.
            abilities=copy.deepcopy(previous['abilities'])
            parents=previous['parent_classes']
            function_count=previous['function_count']
            declared_refs={r['reference'] for r in previous['references']}
            reused+=1
        else:
            exports = json.loads(data)
            if not isinstance(exports, list) or not exports or not all(isinstance(o, dict) for o in exports):
                raise ValueError('Nonempty serialized object list required')
            for obj in exports:
                package = obj.get('Package')
                if package is not None and (not isinstance(package, str) or package.casefold() != key):
                    raise ValueError('Serialized export belongs to a different package')
            types.update(o.get('Type', '') for o in exports)
            abilities = ability_summaries(exports, native_package(item['package']))
            parents=parent_class_summaries(exports,native_package(item['package']))
            function_count=sum(o.get('Type')=='Function' for o in exports)
            declared_refs=set(referenced_packages(exports))
        folder = item['package'][len(MOBS):].split('/', 1)[0] if item['package'].startswith(MOBS) else 'native_support'
        by_folder[folder] += len(abilities)
        ability_count += len(abilities)
        timeline_count += sum(a['declared_timelines'] for a in abilities)
        action_count += sum(a['declared_actions'] for a in abilities)
        issue_count += sum(len(a['issues']) for a in abilities)
        refs = sorted(declared_refs | script_refs.get(key, set()), key=str.casefold)
        dependencies = []
        for ref in refs:
            target = ref.casefold()
            if target == key:
                continue
            if ref.startswith('/Script/'):
                status = 'native_code'; native.add(ref)
            elif target not in assets:
                status = 'not_in_uasset_index'; unindexed.add(ref)
            elif target in existing:
                status = 'extracted'
            elif target in failed_sources:
                status = 'extraction_failed'
            elif defer_cinematic_cache and target.startswith(CINEMATIC_PRESTREAM.casefold()):
                status = 'deferred_cinematic_prestream_cache'; deferred.add(target)
            else:
                status = 'pending_extraction'; missing.add(target)
            dependencies.append(dict(reference=ref, status=status))
        edges.append(dict(item, folder=folder, abilities=abilities, references=dependencies,
                          parent_classes=parents,function_count=function_count))
        if (ordinal+1) % 1000 == 0:
            print(json.dumps(dict(scanned=ordinal+1, total=len(existing))), flush=True)
    all_roots = {k for k, r in assets.items() if r['package'].startswith(MOBS)}
    inheritance = resolve_timeline_inheritance(edges)
    return dict(schema=1, kind='offline_native_dependency_scan',
        index_sha256=disk.digest(index), mapping_sha256=mapping, source_plans=identities,
        script_sources=script_identities, unresolved_script_functions=unresolved_scripts,
        sources=source_identities,scan_cache=cache_identity,
        reused_parsed_packages=reused,newly_parsed_packages=len(existing)-reused,
        extracted_packages=len(existing), root_packages=len(all_roots),
        extracted_roots=len(all_roots & existing.keys()),
        pending_roots=len(all_roots - existing.keys()),
        pending_dependencies=[dict(assets[k], folder='native_dependency') for k in sorted(missing)],
        pending_dependency_count=len(missing), native_code_packages=sorted(native),
        deferred_dependencies=[dict(assets[k], folder='cinematic_prestream_cache') for k in sorted(deferred)],
        deferred_dependency_count=len(deferred),
        dependency_policy='defer_global_cinematic_prestream_cache' if defer_cinematic_cache else 'all_serialized_references',
        failed_dependencies=[dict(assets[k], folder='failed_native_dependency') for k in sorted(failed_sources)],
        failed_dependency_count=len(failed_sources),
        unindexed_references=sorted(unindexed), export_types=dict(sorted(types.items())),
        ability_classes=ability_count, ability_classes_by_folder=dict(sorted(by_folder.items())),
        ability_selector='named_GA_generated_or_native_LegoAbilityBlueprintGeneratedClass',
        timeline_inheritance_resolution=inheritance,
        declared_timelines=timeline_count, declared_actions=action_count, ability_indexing_issues=issue_count,
        packages=edges, disk_metadata_only=True, serialized_overrides_only=True,
        declaration_contents_verified=True,
        indexed_package_closure_complete=not deferred and not failed_sources and not missing and not (all_roots-existing.keys()),
        serialized_package_closure_complete=not deferred and not unindexed and not failed_sources and not missing and not (all_roots-existing.keys()),
        complete_package_inventory=False, all_boss_skills_complete=False,
        live_grant_verified=False, execution_verified=False, playable=False,
        game_started=False, installed=False)


def dependencies(index, mapping, scan_path, target):
    report = json.loads(Path(scan_path).read_bytes())
    if (report.get('kind') != 'offline_native_dependency_scan'
            or report.get('declaration_contents_verified') is not True
            or report['index_sha256'] != disk.digest(index)
            or report['mapping_sha256'] != disk.digest(mapping)):
        raise ValueError('Verified scan of the same index and mapping required')
    assets = catalog(index)
    rows = report['pending_dependencies']
    if len(rows) != report['pending_dependency_count'] or len({r['package'] for r in rows}) != len(rows):
        raise ValueError('Unique pending dependency list required')
    for row in rows:
        if dict(assets.get(row['native_package'].casefold(), {}), folder='native_dependency') != row:
            raise ValueError('Exact indexed pending dependency required')
    return create_plan(index, mapping, target, rows,
                       dict(dependency_scan=str(Path(scan_path).resolve()),
                            dependency_scan_sha256=disk.digest(scan_path)),
                       'serialized_native_dependency_frontier')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    for name in ('roots', 'scan', 'dependencies', 'collect'):
        command = commands.add_parser(name)
        if name == 'collect':
            command.add_argument('target', type=Path)
            for field in ('exporter', 'paks', 'crypto'):
                command.add_argument('--'+field, type=Path, required=True)
            continue
        command.add_argument('--index', type=Path, required=True)
        if name in ('roots', 'scan'):
            command.add_argument('--source', type=Path, action='append', required=True)
        if name in ('roots', 'dependencies'):
            command.add_argument('--mapping', type=Path, required=True)
            command.add_argument('--target', type=Path, required=True)
        if name == 'scan':
            command.add_argument('--output', type=Path, required=True)
            command.add_argument('--script-source', type=Path, action='append', default=[])
            command.add_argument('--allow-incomplete-sources', action='store_true')
            command.add_argument('--defer-cinematic-cache', action='store_true')
            command.add_argument('--reuse-scan', type=Path)
        if name == 'dependencies':
            command.add_argument('--scan', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'roots':
        result = roots(args.index, args.mapping, args.source, args.target)
    elif args.action == 'dependencies':
        result = dependencies(args.index, args.mapping, args.scan, args.target)
    elif args.action == 'collect':
        result = collect(args.target, args.exporter, args.paks, args.crypto)
    else:
        result = scan(args.index, args.source, args.script_source, allow_incomplete=args.allow_incomplete_sources,
                      defer_cinematic_cache=args.defer_cinematic_cache,reuse_scan=args.reuse_scan)
        disk.write_new(args.output, result)
    if 'batches' in result:
        print(json.dumps(dict(requested_packages=len(result['packages']), batches=len(result['batches']))))
    print(json.dumps({k: v for k, v in result.items() if k not in (
        'packages', 'batches', 'pending_dependencies', 'native_code_packages',
        'unindexed_references', 'export_types', 'sources', 'source_plans', 'failed_dependencies',
        'deferred_dependencies')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
