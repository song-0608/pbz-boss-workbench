"""Find and index Boss bodies and dependencies outside the original Mobs mount."""
import argparse
from collections import defaultdict
from contextlib import closing
from functools import lru_cache
import json
from pathlib import Path
import sqlite3

from boss_catalog_assets import ANIMATION_TYPES, CONTROL_TYPES, asset_payload
from boss_catalog_database import (DATABASE, NPC_BASE, NPC_RENEWAL, Catalog, capture_inputs,
                                   check_identity, encode)
from boss_disk_declarations import digest
from boss_disk_dependencies import catalog as indexed_packages, create_plan, native_package, referenced_packages, source_records
from build_boss_disk_combo_index import Capture, Unresolved, split_reference
from research_storage import PROJECT_STORAGE, ROOT


MOBS = '/PBZCombatAsset/ActorData/Mobs/'
PRESTREAM = '/game/cinematics/prestreaming/'
CHARACTER_GROUPS = {'boss', 'eliteboss', 'elitemonster', 'monster'}
ANIMATION_FOLDERS = {'anim', 'anims', 'animation', 'animations', 'montage', 'montages', 'animblueprint'}
INPUT_ROOTS = ('/game/pbzcontent/input/', '/pbzinput/')
TABLES = ('additional_boss_packages', 'additional_boss_exports', 'additional_boss_references',
          'additional_boss_actors', 'additional_boss_gaps', 'boss_actor_configs')
VIEWS = ('boss_native_animation', 'boss_native_control', 'boss_native_actors')
SCHEMA = '''
CREATE TABLE additional_boss_packages (
    package TEXT PRIMARY KEY, declaration TEXT NOT NULL, declaration_sha256 TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE additional_boss_exports (
    package TEXT NOT NULL REFERENCES additional_boss_packages, export_index INTEGER NOT NULL,
    export_type TEXT NOT NULL, name TEXT NOT NULL, domain TEXT, payload TEXT,
    PRIMARY KEY (package, export_index)
) WITHOUT ROWID;
CREATE TABLE additional_boss_references (
    package TEXT NOT NULL REFERENCES additional_boss_packages, mount TEXT NOT NULL, status TEXT NOT NULL,
    PRIMARY KEY (package, mount)
) WITHOUT ROWID;
CREATE TABLE additional_boss_actors (
    class_path TEXT PRIMARY KEY, folder TEXT NOT NULL REFERENCES folders, config_path TEXT NOT NULL,
    package TEXT NOT NULL, export_index INTEGER NOT NULL, class_ancestry TEXT NOT NULL,
    config_source_class TEXT NOT NULL
) WITHOUT ROWID;
CREATE INDEX additional_boss_actor_folder ON additional_boss_actors(folder);
CREATE TABLE additional_boss_gaps (
    package TEXT NOT NULL, reason TEXT NOT NULL, PRIMARY KEY (package, reason)
) WITHOUT ROWID;
CREATE TABLE boss_actor_configs (
    class_path TEXT PRIMARY KEY, config_path TEXT NOT NULL, source_class TEXT NOT NULL,
    config_package TEXT NOT NULL, declaration_sha256 TEXT NOT NULL
) WITHOUT ROWID;
CREATE VIEW boss_native_animation AS
SELECT a.package,a.export_index,e.name,e.export_type,a.payload,p.declaration,p.declaration_sha256
FROM animation_assets a JOIN native_package_exports e USING (package,export_index) JOIN packages p USING (package)
UNION ALL
SELECT e.package,e.export_index,e.name,e.export_type,e.payload,p.declaration,p.declaration_sha256
FROM additional_boss_exports e JOIN additional_boss_packages p USING (package) WHERE e.domain='animation';
CREATE VIEW boss_native_control AS
SELECT c.package,c.export_index,e.name,e.export_type,c.domain,c.payload,p.declaration,p.declaration_sha256
FROM control_declarations c JOIN native_package_exports e USING (package,export_index) JOIN packages p USING (package)
UNION ALL
SELECT e.package,e.export_index,e.name,e.export_type,e.domain,e.payload,p.declaration,p.declaration_sha256
FROM additional_boss_exports e JOIN additional_boss_packages p USING (package)
WHERE e.domain IS NOT NULL AND e.domain<>'animation';
CREATE VIEW boss_native_actors AS
SELECT a.class_path,a.folder,a.package,a.export_index,a.ancestry AS class_ancestry,c.config_path
FROM actor_variants a LEFT JOIN boss_actor_configs c USING (class_path)
UNION ALL
SELECT class_path,folder,package,export_index,class_ancestry,config_path FROM additional_boss_actors;
'''


def candidate_body(package):
    lower = package.casefold()
    return ((lower.startswith('projectpbz/content/renewalcontent/actors/mobs/')
             or Path(lower).stem.startswith('bp_monster_'))
            and not any(excluded in lower for excluded in ('/cinematics/', '/test/', '/developer/')))


def native_asset_root(mount):
    parts = mount.strip('/').split('/')
    return (mount.startswith(INPUT_ROOTS) or
            (len(parts) > 4 and parts[:2] == ['huashira', 'characters']
             and parts[2] in CHARACTER_GROUPS and not ANIMATION_FOLDERS.isdisjoint(parts[4:-1])))


def validated_inputs(index, sources, root, storage):
    catalog = Catalog(root, storage)
    scan, _ = capture_inputs(catalog)
    index_hash = digest(index)
    if index_hash != scan['index_sha256']:
        raise ValueError('Exact frozen native package index required')
    extra, identities, mapping = source_records(sources, index_hash, allow_incomplete=True)
    if sources and (mapping != scan['mapping_sha256'] or any(row['pending_packages'] or row['incomplete_batches']
                                                           for row in identities)):
        raise ValueError('Completed matching extension captures required')
    return catalog, scan, extra, identities


def prepare(index, mapping, target, sources, root=ROOT, storage=PROJECT_STORAGE):
    _, scan, extra, identities = validated_inputs(index, sources, root, storage)
    if digest(mapping) != scan['mapping_sha256']:
        raise ValueError('Exact frozen native type mapping required')
    indexed = indexed_packages(index)
    seen = {native_package(row['package']).casefold() for row in scan['packages']} | set(extra)
    failed_paths = [row['package'] for row in scan['failed_dependencies']]
    failed_paths.extend(package for row in identities for package in row['failed_packages'])
    blocked = {native_package(package).casefold() for package in failed_paths}
    roots = {key for key, row in indexed.items() if candidate_body(row['package']) or native_asset_root(key)}
    added = Capture(extra.values())
    references = {path.casefold() for key in extra for path in referenced_packages(added.exports(key))}
    wanted = (roots | references) & indexed.keys() - seen - blocked
    wanted = sorted((key for key in wanted if not key.startswith(PRESTREAM)),
                    key=lambda key: ('ultimateboss' not in key, key))
    if not wanted:
        return dict(packages=0, failed_references=len(references & blocked), game_started=False)
    rows = [dict(indexed[key], folder='native_character_extension') for key in wanted]
    return create_plan(index, mapping, target, rows, identities, 'native_character_extensions')


def resolve_body(capture, entry):
    classes, config, config_source = [], None, None
    while len(classes) < 64:
        path = entry['Package'] + '.' + entry['Name']
        if path in classes:
            return None
        classes.append(path)
        if path in (NPC_BASE, NPC_RENEWAL):
            return (classes, config, config_source) if config else None
        if config_source is None:
            defaults = capture.defaults(entry)
            if 'Actor Config' in defaults:
                config = capture.resolve(defaults['Actor Config'])
                config_source = path
        entry = capture.resolve(entry.get('Super'))
    return None


def populate(db, scan, extra, identities, index):
    base = {native_package(row['package']).casefold(): row for row in scan['packages']}
    if set(base) & set(extra):
        raise ValueError('Additional captures overlap the frozen base inventory')
    capture = Capture([*base.values(), *extra.values()])
    all_packages = base.keys() | extra.keys()
    indexed = indexed_packages(index)
    failures = {native_package(row['package']).casefold() for row in scan['failed_dependencies']}
    failures.update(native_package(p).casefold() for source in identities for p in source['failed_packages'])
    for name in VIEWS:
        db.execute(f'DROP VIEW IF EXISTS {name}')
    for name in reversed(TABLES):
        db.execute(f'DROP TABLE IF EXISTS {name}')
    for statement in SCHEMA.strip().split(';'):
        if statement.strip():
            db.execute(statement)
    folders = {folder.casefold(): folder for folder, in db.execute('SELECT folder FROM folders')}
    known = dict(db.execute('SELECT class_path,package FROM actor_variants'))
    known_packages = set(known.values())
    actor_config_sources = {package for package, in db.execute('''
        SELECT DISTINCT p.package FROM package_references p JOIN native_package_exports e ON e.package=p.package
        WHERE e.export_type='BlueprintGeneratedClass'
          AND p.reference LIKE '/PBZCombatAsset/ActorData/Mobs/%/ActorC_%' ''')}
    missing = set()
    scoped_roots = {key for key, row in indexed.items() if candidate_body(row['package']) or native_asset_root(key)}
    gaps = {(indexed[key]['package'], 'root_export_failed' if key in failures else 'root_pending')
            for key in scoped_roots - all_packages}
    gaps.update((package, 'extension_export_failed') for source in identities for package in source['failed_packages'])
    for mount, item in sorted(extra.items()):
        package = item['package']
        exports = capture.exports(mount)
        db.execute('INSERT INTO additional_boss_packages VALUES (?,?,?)',
                   (package, item['declaration'], item['declaration_sha256']))
        records = []
        for i, obj in enumerate(exports):
            kind, name = obj['Type'], obj['Name']
            domain = 'animation' if kind in ANIMATION_TYPES else CONTROL_TYPES.get(kind)
            if obj['Name'].startswith('Default__') or 'SkeletalMeshComponent' in kind:
                domain = domain or 'character'
            records.append((package, i, kind, name, domain, encode(asset_payload(obj)) if domain else None))
        db.executemany('INSERT INTO additional_boss_exports VALUES (?,?,?,?,?,?)', records)
        for ref in set(referenced_packages(exports)):
            key = ref.casefold()
            if key == mount:
                continue
            status = ('declared' if key in all_packages else 'native_code' if key.startswith('/script/') else
                      'failed' if key in failures else 'deferred_cache' if key.startswith(PRESTREAM) else
                      'pending' if key in indexed else 'not_indexed')
            db.execute('INSERT INTO additional_boss_references VALUES (?,?,?)', (package, ref, status))
            if status == 'pending':
                missing.add(key)
            if status in ('failed', 'pending', 'not_indexed', 'deferred_cache'):
                label = indexed[key]['package'] if key in indexed else ref
                gaps.add((label, 'dependency_' + status))

    for mount, item in sorted({**base, **extra}.items()):
        # Base candidates outside Mobs were retained as context, even though
        # they were previously excluded from the folder-based actor index.
        if mount in base and not (candidate_body(item['package']) or item['package'] in actor_config_sources
                                  or item['package'] in known_packages):
            continue
        for i, obj in enumerate(capture.exports(mount)):
            if obj['Type'] != 'BlueprintGeneratedClass' or (obj.get('Package') or '').casefold() != mount:
                continue
            path = obj['Package'] + '.' + obj['Name']
            try:
                body = resolve_body(capture, obj)
            except Unresolved:
                continue
            if not body:
                continue
            ancestry, config, source = body
            config_mount = config['Package']
            if config['Type'] != 'PDA_ActorConfig_C' or not config_mount.startswith(MOBS):
                continue
            folder = folders.get(config_mount[len(MOBS):].split('/', 1)[0].casefold())
            if not folder:
                continue
            config_path = config_mount + '.' + config['Name']
            config_package = capture.packages[config_mount.casefold()]
            db.execute('INSERT INTO boss_actor_configs VALUES (?,?,?,?,?)',
                       (path, config_path, source, config_package['package'], config_package['declaration_sha256']))
            if path not in known:
                db.execute('INSERT INTO additional_boss_actors VALUES (?,?,?,?,?,?,?)',
                           (path, folder, config_path, item['package'], i, encode(ancestry), source))
    db.executemany('INSERT INTO additional_boss_gaps VALUES (?,?)', sorted(gaps))
    report = dict(counts={name: db.execute(f'SELECT count(*) FROM {name}').fetchone()[0] for name in (*TABLES, *VIEWS)},
                  scoped_roots=len(scoped_roots), indexed_roots_without_declaration=len(scoped_roots - all_packages),
                  pending_indexed_references=len(missing), extension_source_count=len(identities), game_started=False)
    db.execute("INSERT OR REPLACE INTO metadata VALUES ('native_extension_counts',?)", (encode(report),))
    db.execute("INSERT OR REPLACE INTO metadata VALUES ('native_extension_sources',?)",
               (encode(dict(index=str(index), sources=[row['path'] for row in identities])),))
    return report


def build(index, sources, root=ROOT, storage=PROJECT_STORAGE):
    catalog, scan, extra, identities = validated_inputs(index, sources, root, storage)
    path = (Path(storage) / DATABASE).resolve()
    with closing(sqlite3.connect(path.as_uri() + '?mode=rw', uri=True)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        check_identity(db, catalog)
        result = populate(db, scan, extra, identities, index)
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Character extension import contains dangling database references')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--source', type=Path, action='append', default=[])
    parser.add_argument('--target', type=Path)
    parser.add_argument('--mapping', type=Path)
    args = parser.parse_args()
    if bool(args.target) != bool(args.mapping):
        parser.error('--target and --mapping must be provided together for a capture plan')
    if args.target:
        result = prepare(args.index, args.mapping, args.target, args.source)
        result = dict(packages=len(result['packages']) if isinstance(result['packages'], list) else result['packages'],
                      game_started=False)
    else:
        result = build(args.index, args.source)
    print(json.dumps(result, ensure_ascii=False, indent=2))
