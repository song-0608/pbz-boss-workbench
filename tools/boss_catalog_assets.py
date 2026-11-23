"""Index typed animation and control declarations from the closed disk capture."""
import argparse
from collections import defaultdict
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from contextlib import closing
import sqlite3

from boss_catalog_database import DATABASE, Catalog, check_identity, connect_readonly, encode
from boss_disk_dependencies import native_package
from build_boss_disk_combo_index import Unresolved, split_reference
from research_storage import PROJECT_STORAGE, ROOT


TABLES = ('native_package_exports', 'animation_assets', 'skill_animation_links', 'animation_asset_links',
          'control_declarations', 'actor_control_sources', 'asset_import_gaps')
SCHEMA = '''
CREATE TABLE native_package_exports (
    package TEXT NOT NULL REFERENCES packages, export_index INTEGER NOT NULL,
    mount TEXT NOT NULL, name TEXT NOT NULL, export_type TEXT NOT NULL,
    PRIMARY KEY (package, export_index)
) WITHOUT ROWID;
CREATE INDEX native_export_identity ON native_package_exports(mount, export_index, export_type, name);
CREATE INDEX native_export_type ON native_package_exports(export_type);
CREATE TABLE animation_assets (
    package TEXT NOT NULL, export_index INTEGER NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (package, export_index),
    FOREIGN KEY (package, export_index) REFERENCES native_package_exports
) WITHOUT ROWID;
CREATE TABLE skill_animation_links (
    owner TEXT NOT NULL, timeline INTEGER NOT NULL, ordinal INTEGER NOT NULL,
    target_mount TEXT NOT NULL, target_index INTEGER NOT NULL, target_type TEXT NOT NULL, target_name TEXT NOT NULL,
    package TEXT, export_index INTEGER,
    PRIMARY KEY (owner, timeline, ordinal, target_mount, target_index, target_type, target_name),
    FOREIGN KEY (owner, timeline, ordinal) REFERENCES timeline_actions,
    FOREIGN KEY (package, export_index) REFERENCES animation_assets
) WITHOUT ROWID;
CREATE TABLE animation_asset_links (
    source_package TEXT NOT NULL, source_index INTEGER NOT NULL,
    target_mount TEXT NOT NULL, target_index INTEGER NOT NULL, target_type TEXT NOT NULL, target_name TEXT NOT NULL,
    target_package TEXT, target_export_index INTEGER,
    PRIMARY KEY (source_package, source_index, target_mount, target_index, target_type, target_name),
    FOREIGN KEY (source_package, source_index) REFERENCES animation_assets,
    FOREIGN KEY (target_package, target_export_index) REFERENCES animation_assets
) WITHOUT ROWID;
CREATE TABLE control_declarations (
    package TEXT NOT NULL, export_index INTEGER NOT NULL, domain TEXT NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (package, export_index),
    FOREIGN KEY (package, export_index) REFERENCES native_package_exports
) WITHOUT ROWID;
CREATE TABLE actor_control_sources (
    class_path TEXT NOT NULL REFERENCES actor_variants, depth INTEGER NOT NULL, source_class TEXT NOT NULL,
    package TEXT REFERENCES packages, PRIMARY KEY (class_path, depth)
) WITHOUT ROWID;
CREATE INDEX actor_control_source_package ON actor_control_sources(package);
CREATE TABLE asset_import_gaps (
    package TEXT PRIMARY KEY, reason TEXT NOT NULL, typed_exports TEXT NOT NULL
) WITHOUT ROWID;
'''

ANIMATION_TYPES = {
    'AnimSequence', 'AnimMontage', 'AnimComposite', 'AnimBlueprintGeneratedClass', 'BlendSpace',
    'BlendSpace1D', 'AimOffsetBlendSpace', 'AimOffsetBlendSpace1D', 'PoseAsset', 'Skeleton',
    'IKRigDefinition', 'IKRetargeter', 'MotionMatchingDatabase', 'PoseSearchDatabase',
}
ANIMATION_FIELDS = {'Skeleton', 'SequenceLength', 'RateScale', 'Interpolation', 'NumFrames',
                    'NumberOfSampledKeys', 'SamplingFrameRate', 'bEnableRootMotion',
                    'RootMotionRootLock', 'bForceRootLock', 'RetargetSource', 'Notifies', 'AuthoredSyncMarkers'}
CONTROL_TYPES = {
    'CharacterMovementComponent': 'movement', 'PBZCharacterMovementComponent': 'movement',
    'CameraComponent': 'camera', 'NBCameraComponent': 'camera', 'SpringArmComponent': 'camera',
    'InputAction': 'input', 'InputMappingContext': 'input', 'InputActionBinding': 'input',
    'EnhancedInputActionDelegateBinding': 'input', 'InputKeyDelegateBinding': 'input',
    'InputAxisDelegateBinding': 'input', 'BP_BaseCameraModeData_C': 'camera',
    'ATPCCameraModeDataAsset': 'camera', 'NBGroupCombatCameraMode': 'camera',
    'ATPCCameraModeScript_ChangeMovementSpeed': 'camera', 'ATPCCameraModeScript_PawnUseControllerRotation': 'camera',
    'TargetingComponent': 'targeting', 'BP_TargetingComponent_C': 'targeting',
    'NBLockOnTargetLocationComponent': 'targeting', 'ATPCLockOnTargetLocationComponent': 'targeting',
    'PBZ_TargetingHandler_CombatLock_C': 'targeting', 'PDA_ActorConfig_C': 'character',
}


@lru_cache(maxsize=12)
def receipt_rows(path):
    raw = path.read_bytes()
    report = json.loads(raw)
    if report['mode'] != 'declarations' or report['game_started'] is not False:
        raise ValueError(f'Unexpected declaration receipt: {path}')
    return {row['package']: row for row in report['packages']}


def asset_payload(obj):
    # The exact declaration is available via packages.declaration. Keep the
    # sequence summary in SQLite without duplicating compressed track data.
    if obj['Type'] == 'SkeletalMesh':
        result = {k: v for k, v in obj.items() if k in ('Type', 'Name', 'Class', 'Package')}
        result['Properties'] = {k: v for k, v in obj.get('Properties', {}).items()
                                if k in ('Skeleton', 'PhysicsAsset', 'PostProcessAnimBlueprint')}
        result['declaration_fields'] = list(obj)
        return result
    if obj['Type'] != 'AnimSequence':
        return obj
    result = {k: v for k, v in obj.items() if k in ('Type', 'Name', 'Class', 'Package', 'SkeletonGuid')}
    result['Properties'] = {k: v for k, v in obj.get('Properties', {}).items() if k in ANIMATION_FIELDS}
    result['declaration_fields'] = list(obj)
    return result


def append_exports(db, packages, actor_classes, log):
    for count, (package, declaration, checksum) in enumerate(packages, 1):
        path = Path(declaration)
        receipt = receipt_rows(path.parent / 'conversion-result.json')[package]
        if (receipt['passed'] is not True or receipt['declaration_file'] != path.name
                or receipt['declaration_sha256'] != checksum or receipt['declaration_bytes'] != path.stat().st_size):
            raise ValueError(f'Declaration differs from the verified catalog: {package}')
        mount = native_package(package)
        actor_cdos = actor_classes.get(mount.casefold(), set())
        exports = [(i, obj['name'], obj['type']) for i, obj in enumerate(receipt['exports'])]
        db.executemany('INSERT INTO native_package_exports VALUES (?,?,?,?,?)',
                       ((package, i, mount, name, kind) for i, name, kind in exports))
        selected = []
        for i, name, kind in exports:
            domain = CONTROL_TYPES.get(kind)
            if actor_cdos and (name in actor_cdos or 'SkeletalMeshComponent' in kind):
                domain = domain or 'character'
            if kind in ANIMATION_TYPES or domain:
                selected.append((i, name, kind, domain))
        if selected:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != checksum:
                raise ValueError(f'Declaration content changed: {package}')
            objects = json.loads(raw)
            for i, name, kind, domain in selected:
                obj = objects[i]
                if (obj['Name'], obj['Type']) != (name, kind):
                    raise ValueError(f'Export identity changed: {package}.{i}')
                if kind in ANIMATION_TYPES:
                    db.execute('INSERT INTO animation_assets VALUES (?,?,?)', (package, i, encode(asset_payload(obj))))
                if domain:
                    db.execute('INSERT INTO control_declarations VALUES (?,?,?,?)', (package, i, domain, encode(obj)))
        if log and count % 10000 == 0:
            log(f'已索引 {count:,} 个资源包')


def animation_refs(value):
    if isinstance(value, dict):
        if 'ObjectName' in value and 'ObjectPath' in value:
            try:
                mount, index, kind, name = split_reference(value)
            except Unresolved:
                pass
            else:
                if kind in ANIMATION_TYPES:
                    yield mount, index, kind, name
        for child in value.values():
            yield from animation_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from animation_refs(child)


def append_animation_links(db):
    lookup = {(mount.casefold(), index, kind, name): (package, index)
              for package, mount, index, kind, name in db.execute('''
                  SELECT e.package,e.mount,e.export_index,e.export_type,e.name
                  FROM native_package_exports e JOIN animation_assets a USING(package,export_index)''')}
    rows = db.execute('''SELECT owner,timeline,ordinal,payload FROM timeline_actions
                         WHERE instr(payload, 'ObjectName') > 0''')
    for owner, timeline, ordinal, payload in rows:
        refs = set(animation_refs(json.loads(payload).get('serialized_action_properties')))
        db.executemany('INSERT INTO skill_animation_links VALUES (?,?,?,?,?,?,?,?,?)',
            ((owner, timeline, ordinal, mount, i, kind, name, *lookup.get((mount.casefold(), i, kind, name), (None, None)))
             for mount, i, kind, name in sorted(refs)))
    for package, index, payload in db.execute('SELECT package,export_index,payload FROM animation_assets'):
        refs = set(animation_refs(json.loads(payload)))
        db.executemany('INSERT INTO animation_asset_links VALUES (?,?,?,?,?,?,?,?)', (
            (package, index, mount, i, kind, name, *lookup.get((mount.casefold(), i, kind, name), (None, None)))
            for mount, i, kind, name in sorted(refs)
            if lookup.get((mount.casefold(), i, kind, name)) != (package, index)))


def actor_sources(db, packages):
    mount_packages = {native_package(package).casefold(): package for package, *_ in packages}
    classes = defaultdict(set)
    for path, ancestry in db.execute('SELECT class_path,ancestry FROM actor_variants'):
        for depth, ancestor in enumerate(json.loads(ancestry)):
            mount, name = ancestor.rsplit('.', 1)
            key = mount.casefold()
            classes[key].add('Default__' + name)
            db.execute('INSERT INTO actor_control_sources VALUES (?,?,?,?)',
                       (path, depth, ancestor, mount_packages.get(key)))
    return classes


def failed_typed_exports(scan):
    wanted = {row['package'] for row in scan['failed_dependencies']}
    for source in scan['source_plans']:
        root = Path(source['path'])
        for batch in root.glob('batch-*/conversion-result.json'):
            for package, row in receipt_rows(batch).items():
                if package in wanted and row['passed'] is False:
                    wanted.remove(package)
                    yield package, row.get('error_type', 'export_failed'), encode(row.get('exports', []))
    for package in sorted(wanted):
        yield package, 'declaration_missing', '[]'


def summarize(db):
    counts = {name: db.execute(f'SELECT count(*) FROM {name}').fetchone()[0] for name in TABLES}
    return dict(counts=counts, animation_types=dict(db.execute('''
        SELECT export_type,count(*) FROM animation_assets JOIN native_package_exports USING(package,export_index)
        GROUP BY export_type ORDER BY export_type''')), control_domains=dict(db.execute('''
        SELECT domain,count(*) FROM control_declarations GROUP BY domain ORDER BY domain''')),
        unresolved_animation_links=db.execute('SELECT count(*) FROM skill_animation_links WHERE package IS NULL').fetchone()[0],
        unresolved_asset_links=db.execute('SELECT count(*) FROM animation_asset_links WHERE target_package IS NULL').fetchone()[0],
        game_started=False)


def populate(db, scan, log=None):
    packages = db.execute('SELECT package,declaration,declaration_sha256 FROM packages ORDER BY declaration').fetchall()
    for name in reversed(TABLES):
        db.execute(f'DROP TABLE IF EXISTS {name}')
    for statement in SCHEMA.strip().split(';'):
        if statement.strip():
            db.execute(statement)
    append_exports(db, packages, actor_sources(db, packages), log)
    append_animation_links(db)
    db.executemany('INSERT INTO asset_import_gaps VALUES (?,?,?)', failed_typed_exports(scan))
    result = summarize(db)
    db.execute("INSERT OR REPLACE INTO metadata VALUES ('native_asset_counts',?)", (encode(result),))
    return result


def build(root=ROOT, storage=PROJECT_STORAGE, *, log=None):
    from boss_catalog_database import capture_inputs
    catalog = Catalog(root, storage)
    scan, _ = capture_inputs(catalog)
    path = Path(storage) / DATABASE
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        check_identity(db, catalog)
        result = populate(db, scan, log)
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Native asset import contains dangling database references')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        with closing(connect_readonly(PROJECT_STORAGE / DATABASE)) as db:
            result = summarize(db)
            expected, = db.execute("SELECT value FROM metadata WHERE key='native_asset_counts'").fetchone()
            if result != json.loads(expected) or db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Native asset database rows differ from their import receipt')
    else:
        result = build(log=lambda message: print(message, flush=True))
    print(json.dumps(result, ensure_ascii=False, indent=2))
