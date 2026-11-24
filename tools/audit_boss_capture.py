"""Audit offline Boss capture coverage against source receipts and local files."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from itertools import chain
import json
from pathlib import Path

from boss_animation_sources import load_records
from boss_asset_extensions import candidate_body, native_asset_root, validated_inputs
from boss_catalog_database import DATABASE, capture_inputs, check_identity, connect_readonly, verify
from boss_disk_declarations import digest, write_new
from boss_disk_dependencies import MOBS, catalog as package_index, native_package
from boss_encounter_sources import verified_records
from build_boss_disk_repertoire import read_verified
from research_storage import PROJECT_STORAGE, ROOT


def metadata(db, key):
    value, = db.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()
    return json.loads(value)


def verify_declarations(records, log):
    ordered = sorted(records, key=lambda item: item['declaration'])
    batch_size = 128

    def check_batch(start):
        batch = ordered[start:start + batch_size]
        for row in batch:
            if digest(row['declaration']) != row['declaration_sha256']:
                raise ValueError(f'Captured declaration changed: {row["package"]}')
        return len(batch)

    checked = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for count in pool.map(check_batch, range(0, len(ordered), batch_size)):
            if log and checked // 15000 != (checked + count) // 15000:
                log(f'声明摘要已复核 {checked + count:,} 个包')
            checked += count
    return checked


def scan_animation_files(db, log):
    frozen = metadata(db, 'boss_editable_clip_plans')
    if set(frozen) != {'skills', 'actor', 'catalog'}:
        raise ValueError('Skill, actor and catalog animation receipts are required')
    formats, total, bytes_verified = Counter(), 0, 0
    for scope, info in frozen.items():
        path = Path(info['path'])
        if digest(path / 'plan.json') != info['sha256']:
            raise ValueError(f'Frozen animation plan changed: {scope}')
        current = load_records(db, path)
        stored = {package: json.loads(payload) for package, payload in db.execute(
            'SELECT package,payload FROM boss_editable_clips WHERE scope=?', (scope,))}
        if current != stored:
            raise ValueError(f'Animation sources or database records changed: {scope}')
        for row in current.values():
            if row['status'] == 'exported':
                formats[row['format']] += 1
                bytes_verified += row['size']
        total += len(current)
        if log:
            log(f'动画已复核 {scope}：{len(current):,} 段')
    return dict(files_verified=sum(formats.values()), planned=total, formats=dict(formats), bytes_verified=bytes_verified)


def verify_actions_and_scripts(db, catalog):
    timelines = read_verified(catalog.repertoire / 'timelines.json', catalog.files['timelines.json'])
    expected_actions = sum(len(timeline['actions']) for row in timelines.values() for timeline in row['timelines'])
    actual_actions = 0
    for owner, timeline, ordinal, raw in db.execute('SELECT owner,timeline,ordinal,payload FROM timeline_actions'):
        action = timelines[owner]['timelines'][timeline]['actions'][ordinal]
        if json.loads(raw) != action:
            raise ValueError(f'Database action differs from the frozen timeline: {owner}')
        actual_actions += 1
    if expected_actions != actual_actions:
        raise ValueError('Frozen timeline action coverage differs from the database')
    scripts = read_verified(catalog.repertoire / 'scripts.json', catalog.files['scripts.json'])
    actual = {package: (path, sha) for package, path, sha in db.execute('SELECT package,path,sha256 FROM scripts')}
    if actual != {package: (row['path'], row['sha256']) for package, row in scripts.items()}:
        raise ValueError('Native script package records differ from the frozen script index')
    for _, (path, sha) in actual.items():
        if digest(path) != sha:
            raise ValueError(f'Captured script changed: {path}')
    return actual_actions, len(actual)


def verify_skill_class_coverage(db, quarantines):
    catalogued = {(path.casefold(), package): path for path, package in db.execute('SELECT class_path,package FROM skills')}
    base = db.execute('''SELECT mount,name,package,export_type FROM native_package_exports
        WHERE export_type IN ('LegoAbilityBlueprintGeneratedClass','BlueprintGeneratedClass')''')
    extra = ((native_package(package), name, package, kind) for name, package, kind in db.execute('''
        SELECT name,package,export_type FROM additional_boss_exports
        WHERE export_type IN ('LegoAbilityBlueprintGeneratedClass','BlueprintGeneratedClass')'''))
    native, indexed, unindexed = set(), set(), []
    for mount, name, package, kind in chain(base, extra):
        path = mount + '.' + name
        key = (path.casefold(), package)
        if key in catalogued:
            if key in indexed:
                raise ValueError(f'Duplicate captured skill export: {path}')
            indexed.add(key)
        if kind == 'LegoAbilityBlueprintGeneratedClass':
            if key in native:
                raise ValueError(f'Duplicate native ability class identity: {path}')
            native.add(key)
            if key not in catalogued:
                unindexed.append((path, package))
    if indexed != catalogued.keys():
        raise ValueError('Skill catalog contains entries without an exact captured class export')
    quarantine_by_class = {row['class_path'].casefold(): row for row in quarantines}
    unindexed_classes = []
    for path, package in sorted(unindexed):
        disposition = 'unindexed'
        if quarantine := quarantine_by_class.get(path.casefold()):
            captured = db.execute('SELECT declaration,declaration_sha256 FROM packages WHERE package=? '
                                  'UNION ALL SELECT declaration,declaration_sha256 FROM additional_boss_packages WHERE package=?',
                                  (package, package)).fetchone()
            if captured != (quarantine['disk_declaration'], quarantine['disk_declaration_sha256']):
                raise ValueError(f'Quarantine source differs from captured class: {path}')
            disposition = 'quarantined'
        unindexed_classes.append(dict(class_path=path, package=package, disposition=disposition))
    return dict(captured_lego_classes=len(native), indexed_lego_classes=len(native & indexed),
                indexed_blueprint_classes=len(indexed - native), unindexed=unindexed_classes)


def combat_body_coverage(db, encounters, quarantines):
    encounter_skills = defaultdict(set)
    for entry in encounters:
        if entry['actor']['config_path']:
            encounter_skills[entry['ability_folder']].add(entry['ability_class'])
    quarantined_folders = {entry['folder'] for entry in quarantines}
    missing, shared = [], []
    for folder, status, config_exports in db.execute('''
        SELECT folder,body_status,config_exports FROM boss_group_coverage
        WHERE actor_count=0 AND folder NOT IN ('Common','Vessel_Common','native_support') ORDER BY folder'''):
        expected = {path for path, in db.execute('SELECT class_path FROM skills WHERE folder=?', (folder,))}
        linked = encounter_skills[folder]
        if not config_exports and expected and expected == linked and folder not in quarantined_folders:
            shared.append(dict(folder=folder, status='all_skills_linked_to_authored_encounter_body',
                               skill_classes=sorted(linked)))
        else:
            missing.append(dict(folder=folder, status=status))
    return missing, shared


def check_mounted_references(directory, expected, mapping_sha):
    job_path = directory / 'job.json'
    job = json.loads(job_path.read_bytes())
    path = directory / 'result/conversion-result.json'
    receipt = json.loads(path.read_bytes())
    rows = receipt['packages']
    if (job['mode'] != 'inspect' or receipt['mode'] != 'inspect' or receipt['game_started'] is not False
            or receipt['input_job_sha256'] != digest(job_path) or receipt['mapping_sha256'] != mapping_sha
            or [row['package'] for row in rows] != job['packages']):
        raise ValueError('Mounted package check receipt does not match its offline inputs')
    checked = {native_package(row['package']).casefold(): 'present' if row['passed'] else row.get('error_type') for row in rows}
    if checked.keys() != {row['reference'].casefold() for row in expected if row['current_status'] == 'not_in_local_index'}:
        raise ValueError('Mounted check does not cover the exact index-external root references')
    return dict(receipt=str(path), receipt_sha256=digest(path), results=checked)


def configuration_gaps(db):
    dynamic_trees, missing, authored, unresolved = set(), [], [], []
    for config, tree, ordinal, sha, raw in db.execute('''
        SELECT config_path,tree_path,export_index,source_sha256,payload FROM boss_config_strategy_selectors
        WHERE mode='dynamic_subtree' ORDER BY config_path,tree_path,export_index'''):
        selector = json.loads(raw)['selector']
        dynamic_trees.add((config, tree))
        if not (selector.get('default') or selector.get('configured')):
            missing.append(dict(config_path=config, tree_path=tree, export_index=ordinal,
                                tree_sha256=sha, **selector))
    for config, raw in db.execute('SELECT config_path,diagnostics FROM boss_combat_config_index ORDER BY config_path'):
        for issue in json.loads(raw):
            reason = issue['reason']
            if (reason == 'dynamic_subtree_selection' and (config, issue['source']) in dynamic_trees
                    or reason in ('authored_tactic_separator', 'authored_null_subpool_slot')
                    or reason == 'strategy_tree_cycle_or_depth_limit' and issue.get('cycle')):
                authored.append(dict(config_path=config, **issue))
            else:
                unresolved.append(dict(config_path=config, **issue))
    return missing, authored, unresolved


def audit(index, root=ROOT, storage=PROJECT_STORAGE, log=None, mounted_check=None):
    database = Path(storage) / DATABASE
    with closing(connect_readonly(database)) as db:
        data_version, = db.execute('PRAGMA data_version').fetchone()
        provenance = metadata(db, 'native_extension_sources')
        catalog, scan, extensions, _ = validated_inputs(index, provenance['sources'], root, storage)
        check_identity(db, catalog)
        indexed = package_index(index)
        original = {native_package(row['package']).casefold(): row for row in scan['packages']}
        known = {**original, **extensions}
        rows = {package: (declaration, sha) for package, declaration, sha in db.execute('''
            SELECT package,declaration,declaration_sha256 FROM packages
            UNION ALL SELECT package,declaration,declaration_sha256 FROM additional_boss_packages''')}
        if rows != {r['package']: (r['declaration'], r['declaration_sha256']) for r in known.values()}:
            raise ValueError('Package rows differ from the verified declaration receipts')
        mob_roots = {key for key, row in indexed.items() if row['package'].startswith(MOBS)}
        other_roots = {key for key, row in indexed.items()
                       if candidate_body(row['package']) or native_asset_root(key)}
        missing = sorted((mob_roots | other_roots) - known.keys())
        verified_packages = verify_declarations(known.values(), log)

        _, queue = capture_inputs(catalog)
        expected_skills = {row['class_path']: row for row in queue['rows']}
        actual_skills = {path: json.loads(raw) for path, raw in db.execute('SELECT class_path,adaptation FROM skills')}
        if expected_skills != actual_skills:
            raise ValueError('Native skills differ from the frozen adaptation queue')
        actions, script_packages = verify_actions_and_scripts(db, catalog)

        root_references = []
        for raw, in db.execute("SELECT payload FROM capture_gaps WHERE category='root-reference-gaps' ORDER BY ordinal"):
            row = json.loads(raw)
            target = row['reference'].casefold()
            root_references.append(dict(row, current_status='captured' if target in known else
                                        'indexed_without_declaration' if target in indexed else 'not_in_local_index'))
        stored_root_status = db.execute('SELECT package,mount,status FROM boss_root_reference_status').fetchall()
        expected_status = [(row['package'], row['reference'], row['current_status']) for row in root_references]
        if sorted(stored_root_status) != sorted(expected_status):
            raise ValueError('Current root reference statuses do not match the audited inventory')
        probe = check_mounted_references(mounted_check, root_references, scan['mapping_sha256']) if mounted_check else None
        quarantines = [json.loads(raw) for raw, in db.execute(
            "SELECT payload FROM capture_gaps WHERE category='quarantined'")]
        class_coverage = verify_skill_class_coverage(db, quarantines)
        encounter_links = verified_records(db)
        actor_gaps, shared_bodies = combat_body_coverage(db, encounter_links, quarantines)
        effective_dependency_gaps = dict(Counter(status for _, status in db.execute('SELECT package,reason FROM additional_boss_gaps')))
        animation = scan_animation_files(db, log)
        if log:
            log('开始核对数据库记录、完整性和外键')
        verified = verify(database, catalog)
        if not verified.get('strategy_evidence_verified'):
            raise ValueError('Reindex native strategy evidence with boss_config_abilities.py before the capture audit')
        dynamic_targets_missing, authored_diagnostics, unresolved_diagnostics = configuration_gaps(db)
        if db.execute('PRAGMA data_version').fetchone() != (data_version,):
            raise ValueError('Boss database changed during the audit')
    config = verified['config_abilities']
    unresolved_root_references = [row for row in root_references if row['current_status'] != 'captured']
    native_scope_complete = not (missing or effective_dependency_gaps or unresolved_root_references or actor_gaps
                                 or quarantines or class_coverage['unindexed'] or dynamic_targets_missing
                                 or config['unresolved_links'] or unresolved_diagnostics
                                 or animation['planned'] != animation['files_verified'])
    return dict(mobs_indexed_roots=len(mob_roots), other_indexed_roots=len(other_roots),
                declaration_files_verified=verified_packages, missing_root_packages=missing,
                root_references=root_references, root_reference_blockers=unresolved_root_references,
                missing_combat_bodies=actor_gaps, encounter_backed_resource_groups=shared_bodies,
                quarantined=quarantines, extension_gaps=effective_dependency_gaps,
                native_skill_class_coverage=class_coverage, authored_encounter_links=len(encounter_links),
                dynamic_selectors_without_static_target=len(dynamic_targets_missing),
                dynamic_selector_gaps=dynamic_targets_missing,
                authored_configuration_diagnostics=dict(Counter(row['reason'] for row in authored_diagnostics)),
                authored_configuration_details=[row for row in authored_diagnostics
                                                if row['reason'] != 'dynamic_subtree_selection'],
                unresolved_configuration_diagnostics=unresolved_diagnostics,
                animation_sources=animation, config_abilities=config, mounted_reference_probe=probe,
                skills=verified['counts']['skills'], actions=actions, script_files_verified=script_packages,
                historical_failed_dependency_packages=scan['failed_dependency_count'],
                historical_deferred_dependency_packages=scan['deferred_dependency_count'],
                historical_unindexed_dependency_references=len(scan['unindexed_references']),
                native_scope_complete=native_scope_complete, ready_for_delivery=False,
                game_started=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mounted-check', type=Path)
    args = parser.parse_args()
    result = audit(args.index, log=lambda message: print(message, flush=True), mounted_check=args.mounted_check)
    write_new(args.output, result)
    print(json.dumps({key: value for key, value in result.items() if key != 'root_references'},
                     ensure_ascii=False, indent=2))
