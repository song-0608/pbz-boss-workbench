"""Store verified offline Boss declarations and expose their mechanism and skill indexes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
from itertools import islice
import json
from pathlib import Path
import sqlite3
import tempfile
import zlib

from boss_catalog_database import DATABASE, Catalog, check_identity, connect_readonly, encode
from boss_disk_dependencies import native_package
from build_boss_disk_combo_index import Unresolved, split_reference
from build_boss_disk_repertoire import superclass
from research_storage import PROJECT_STORAGE, ROOT


VERSION_KEY = 'boss_mechanism_declarations_version'
SUPPLEMENT_PREFIX = 'boss_mechanism_supplement:'
TABLE = '''CREATE TABLE boss_mechanism_declarations (
    package TEXT PRIMARY KEY,
    source_sha256 TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK(source_kind IN ('asset','encounter_map')),
    raw_bytes INTEGER NOT NULL CHECK(raw_bytes > 0),
    declaration_zlib BLOB NOT NULL CHECK(length(declaration_zlib) > 0)
)'''

SOURCE = '''SELECT package,declaration,declaration_sha256,'asset' FROM packages
UNION ALL SELECT package,declaration,declaration_sha256,'asset' FROM additional_boss_packages
UNION ALL SELECT DISTINCT json_extract(value,'$.map_package'),json_extract(value,'$.declaration'),
    json_extract(value,'$.declaration_sha256'),'encounter_map'
    FROM metadata WHERE key GLOB 'boss_encounter_source:*'
UNION ALL SELECT json_extract(value,'$.package'),json_extract(value,'$.declaration'),
    json_extract(value,'$.declaration_sha256'),json_extract(value,'$.kind')
    FROM metadata WHERE key GLOB 'boss_mechanism_supplement:*' '''

ENCOUNTER_EXPORTS = '''CREATE TABLE boss_mechanism_encounter_exports (
    package TEXT NOT NULL REFERENCES boss_mechanism_declarations,
    export_index INTEGER NOT NULL,
    mount TEXT,
    name TEXT NOT NULL,
    export_type TEXT NOT NULL,
    PRIMARY KEY(package,export_index)
) WITHOUT ROWID'''

ABILITY_ANCESTRY = '''CREATE TABLE boss_mechanism_ability_ancestry (
    class_path TEXT PRIMARY KEY,
    folder TEXT NOT NULL,
    package TEXT NOT NULL REFERENCES boss_mechanism_declarations,
    export_index INTEGER NOT NULL,
    ancestry TEXT NOT NULL
) WITHOUT ROWID'''

EXPORTS = '''CREATE VIEW boss_mechanism_exports AS
SELECT e.package,e.export_index,e.mount,e.name,e.export_type,p.folder,a.source_sha256
    FROM native_package_exports e JOIN packages p USING(package)
    JOIN boss_mechanism_declarations a USING(package)
UNION ALL
SELECT e.package,e.export_index,NULL,e.name,e.export_type,'native_support',a.source_sha256
    FROM additional_boss_exports e JOIN boss_mechanism_declarations a USING(package)
UNION ALL
SELECT e.package,e.export_index,e.mount,e.name,e.export_type,'native_support',a.source_sha256
    FROM boss_mechanism_encounter_exports e JOIN boss_mechanism_declarations a USING(package)'''

MECHANISMS = '''CREATE VIEW boss_mechanisms AS
SELECT * FROM (
    SELECT e.*, CASE
        WHEN export_type='BehaviorTree' OR export_type GLOB 'BT*' THEN 'behavior_tree'
        WHEN export_type GLOB '*StateMachine*' OR export_type GLOB '*StateTree*'
            OR export_type GLOB 'STTask_*' OR export_type GLOB '*ActionPhase*' THEN 'state_and_phase'
        WHEN export_type GLOB '*StrategyConfig*' OR export_type GLOB '*AbilityPool*'
            OR export_type GLOB 'AIScript_*' OR export_type GLOB 'AITask_*' THEN 'ai_strategy'
        WHEN export_type GLOB '*Bullet*' OR export_type GLOB '*Projectile*' THEN 'hitbox_and_projectile'
        WHEN export_type GLOB '*GameplayEffect*' OR export_type GLOB '*DamageCalculator*'
            OR export_type GLOB '*AttributeSet*' OR export_type GLOB '*CombatConfig*' THEN 'damage_and_effect'
        WHEN export_type GLOB '*Deflect*' OR export_type GLOB '*Endure*'
            OR export_type GLOB '*HitState*' THEN 'defense_and_reaction'
        WHEN export_type='LGATimeline' OR export_type GLOB 'LGAAction_*' OR export_type GLOB 'GAA_*'
            OR export_type GLOB 'GAAction_*' THEN 'skill_timeline'
        WHEN export_type GLOB '*ActorConfig*' OR export_type GLOB '*AIConfig*'
            OR export_type GLOB '*WeaponConfig*' THEN 'actor_and_equipment'
        WHEN export_type GLOB '*Condition_*' OR export_type GLOB 'SGameAICondition*' THEN 'condition'
        WHEN export_type GLOB '*FlowNode*' OR export_type GLOB '*FlowAsset*' OR name GLOB 'BPF_*'
            OR export_type GLOB '*AISpawner*' THEN 'encounter_flow'
    END AS mechanism_type
    FROM boss_mechanism_exports e
) WHERE mechanism_type IS NOT NULL'''

SKILLS = '''CREATE VIEW boss_skill_inventory AS
SELECT class_path,folder,package,native_route,timeline_owner,'indexed' AS capture_status,NULL AS issues
    FROM skills
UNION ALL
SELECT json_extract(g.payload,'$.class_path'),json_extract(g.payload,'$.folder'),e.package,
    NULL,NULL,'quarantined',json_extract(g.payload,'$.issues')
    FROM capture_gaps g JOIN native_package_exports e
    ON e.name=substr(g.identifier,instr(g.identifier,'.')+1) AND e.mount || '.' || e.name=g.identifier
    WHERE g.category='quarantined' AND e.export_type='LegoAbilityBlueprintGeneratedClass'
UNION ALL
SELECT class_path,folder,package,NULL,NULL,'ancestry_verified',NULL FROM boss_mechanism_ability_ancestry'''


def sources(db):
    return db.execute(SOURCE + ' ORDER BY 2,1')


def pack(source):
    package, path, expected, kind = source
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f'Frozen declaration changed: {package}')
    return package, expected, kind, len(raw), zlib.compress(raw, level=1)


def collect(source_db, destination, log=None):
    destination.execute(TABLE)
    records = sources(source_db)
    count = 0
    with ThreadPoolExecutor(max_workers=4) as workers:
        while batch := list(islice(records, 32)):
            destination.executemany('INSERT INTO boss_mechanism_declarations VALUES (?,?,?,?,?)',
                                    workers.map(pack, batch))
            if log and count // 10000 != (count + len(batch)) // 10000:
                log(f'已入库 {count + len(batch):,} 份冻结原生声明')
            count += len(batch)


def install_views(db):
    db.execute(ENCOUNTER_EXPORTS)
    index_encounter_exports(db)
    db.execute(ABILITY_ANCESTRY)
    for statement in (EXPORTS, MECHANISMS, SKILLS):
        db.execute(statement)
    index_abilities(db)
    db.execute('INSERT INTO metadata VALUES (?,?)', (VERSION_KEY, '1'))


def verify_inventory(db):
    version = db.execute('SELECT value FROM metadata WHERE key=?', (VERSION_KEY,)).fetchone()
    if version is None:
        return None
    if version != ('1',):
        raise ValueError('Unknown Boss declaration archive format')
    expected = {(package, sha, kind) for package, _, sha, kind in sources(db)}
    actual = set(db.execute('SELECT package,source_sha256,source_kind FROM boss_mechanism_declarations'))
    if actual != expected:
        raise ValueError('Archived Boss declarations differ from the frozen package inventory')
    if db.execute("""SELECT 1 FROM sqlite_master WHERE type='table' AND name='boss_mechanism_encounter_exports'""").fetchone():
        stored = db.execute('SELECT * FROM boss_mechanism_encounter_exports ORDER BY package,export_index').fetchall()
        if stored != sorted(encounter_export_rows(db)):
            raise ValueError('Encounter export index differs from the archived declarations')
    if db.execute("""SELECT 1 FROM sqlite_master WHERE type='table' AND name='boss_mechanism_ability_ancestry'""").fetchone():
        stored = db.execute('SELECT * FROM boss_mechanism_ability_ancestry ORDER BY class_path').fetchall()
        if stored != sorted(ability_ancestry_rows(db)):
            raise ValueError('Boss ability ancestry index differs from the archived classes')
    skills = dict(db.execute('SELECT capture_status,count(*) FROM boss_skill_inventory GROUP BY capture_status'))
    quarantines, = db.execute("SELECT count(*) FROM capture_gaps WHERE category='quarantined'").fetchone()
    if skills.get('quarantined', 0) != quarantines:
        raise ValueError('Boss skill inventory omitted a quarantined native class')
    count, raw_bytes, compressed_bytes = db.execute('''SELECT count(*),sum(raw_bytes),sum(length(declaration_zlib))
        FROM boss_mechanism_declarations''').fetchone()
    return dict(declarations=count, raw_bytes=raw_bytes, compressed_bytes=compressed_bytes,
                encounter_map_declarations=sum(kind == 'encounter_map' for _, _, kind in actual),
                supplemental_declarations=len(supplement_records(db)),
                skills=skills, mechanism_exports=dict(db.execute('''SELECT mechanism_type,count(*)
                    FROM boss_mechanisms GROUP BY mechanism_type ORDER BY mechanism_type''')))


def checked_bytes(package, expected, size, blob):
    raw = zlib.decompress(blob)
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f'Archived Boss declaration differs from its digest: {package}')
    return raw


def read_declaration(db, package):
    row = db.execute('''SELECT package,source_sha256,raw_bytes,declaration_zlib
        FROM boss_mechanism_declarations WHERE package=?''', (package,)).fetchone()
    if row is None:
        raise ValueError(f'Boss declaration is absent: {package}')
    return json.loads(checked_bytes(*row))


def read_export(db, package, export_index):
    exports = read_declaration(db, package)
    if not 0 <= export_index < len(exports):
        raise ValueError(f'Invalid export index for {package}: {export_index}')
    return exports[export_index]


def verify_contents(db, log=None):
    rows = db.execute('SELECT package,source_sha256,raw_bytes,declaration_zlib FROM boss_mechanism_declarations')
    count = 0
    with ThreadPoolExecutor(max_workers=4) as workers:
        while batch := list(islice(rows, 16)):
            for _ in workers.map(lambda row: checked_bytes(*row), batch):
                count += 1
                if log and count % 10000 == 0:
                    log(f'已复核数据库内 {count:,} 份声明的原始摘要')
    return count


def populate(db, log=None):
    collect(db, db, log)
    install_views(db)


def supplement_records(db):
    return db.execute("SELECT key,value FROM metadata WHERE key GLOB 'boss_mechanism_supplement:*' ORDER BY key").fetchall()


def encounter_export_rows(db):
    packages = db.execute("""SELECT package FROM boss_mechanism_declarations WHERE source_kind='encounter_map'
        UNION SELECT json_extract(value,'$.package') FROM metadata WHERE key GLOB 'boss_mechanism_supplement:*' """)
    for package, in packages:
        for i, export in enumerate(read_declaration(db, package)):
            yield package, i, export.get('Package'), export['Name'], export['Type']


def index_encounter_exports(db):
    db.execute('DELETE FROM boss_mechanism_encounter_exports')
    db.executemany('INSERT INTO boss_mechanism_encounter_exports VALUES (?,?,?,?,?)', encounter_export_rows(db))


def ability_ancestry_rows(db):
    registered = {path.casefold() for path, in db.execute("""SELECT class_path FROM skills
        UNION ALL SELECT identifier FROM capture_gaps WHERE category='quarantined' """)}
    candidates = {}
    for package, index, mount, name, kind, folder in db.execute('''SELECT
        package,export_index,mount,name,export_type,folder FROM boss_mechanism_exports
        WHERE export_type IN ('BlueprintGeneratedClass','LegoAbilityBlueprintGeneratedClass')
        AND package LIKE '%.uasset' ORDER BY package,export_index'''):
        candidates.setdefault(package, []).append((index, mount, name, kind, folder))
    classes = {}
    for package, entries in candidates.items():
        exports = read_declaration(db, package)
        for index, mount, name, kind, folder in entries:
            mount = mount or native_package(package)
            item = exports[index]
            if (item.get('Package') or '').casefold() != mount.casefold() or name.startswith('Default__'):
                continue
            if item['Type'] != kind or item['Name'] != name:
                raise ValueError(f'Native class index differs from its declaration: {package} export {index}')
            path = item['Package'] + '.' + name
            key = path.casefold()
            if key in classes:
                raise ValueError(f'Duplicate native class identity: {path}')
            classes[key] = (package, index, path, kind, folder, superclass(item))
    native_parents = {}
    for key in sorted(classes.keys() & registered):
        _, _, path, _, _, ref = classes[key]
        if ref and ref['ObjectPath'].startswith('/Script/'):
            native_parents.setdefault((ref['ObjectPath'], ref['ObjectName']), path)
    for key, (package, index, path, _, folder, ref) in classes.items():
        if key in registered:
            continue
        seen = {key}
        chain = []
        while ref:
            chain.append(ref)
            native_witness = native_parents.get((ref['ObjectPath'], ref['ObjectName']))
            if native_witness is not None:
                yield path, folder, package, index, encode(dict(chain=chain, verified_by=native_witness))
                break
            try:
                mount, ordinal, kind, name = split_reference(ref)
            except Unresolved:
                break
            parent_key = (mount + '.' + name).casefold()
            parent = classes.get(parent_key)
            if parent is None or parent_key in seen or (parent[1], parent[3]) != (ordinal, kind):
                break
            if parent_key in registered:
                yield path, folder, package, index, encode(dict(chain=chain, verified_by=parent[2]))
                break
            seen.add(parent_key)
            ref = parent[5]


def index_abilities(db):
    db.execute('DELETE FROM boss_mechanism_ability_ancestry')
    db.executemany('INSERT INTO boss_mechanism_ability_ancestry VALUES (?,?,?,?,?)', ability_ancestry_rows(db))


def read_supplement(audit):
    audit = audit.resolve()
    info = json.loads(audit.read_bytes())
    if info['kind'] != 'offline_dynamic_subtree_assignment_verification' or info['game_started'] is not False:
        raise ValueError('Expected an offline Boss encounter source audit')
    for source in info['verified_source_receipts']:
        receipt = Path(source['file']).resolve()
        if receipt.name != 'conversion-result.json':
            continue
        data = receipt.read_bytes()
        if not receipt.is_relative_to(audit.parent) or hashlib.sha256(data).hexdigest() != source['sha256']:
            raise ValueError(f'Invalid encounter source receipt: {receipt}')
        report = json.loads(data)
        if (report['mode'] != 'declarations' or report['game_started'] is not False
                or report['passed'] is not True or len(report['packages']) != source['packages']):
            raise ValueError(f'Incomplete encounter declaration receipt: {receipt}')
        for row in report['packages']:
            package, filename = row['package'], row['declaration_file']
            path = receipt.parent / filename
            if (row['passed'] is not True or Path(filename).name != filename or path.is_symlink()
                    or not package.startswith('ProjectPBZ/Content/') or not package.endswith(('.umap', '.uasset'))
                    or path.stat().st_size != row['declaration_bytes']):
                raise ValueError(f'Invalid encounter package declaration: {package}')
            yield dict(package=package, declaration=str(path), declaration_sha256=row['declaration_sha256'],
                       kind='encounter_map' if package.endswith('.umap') else 'asset',
                       receipt=str(receipt), receipt_sha256=source['sha256'])


def add_supplement(database, catalog, audit):
    additions = list(read_supplement(audit))
    if not additions:
        raise ValueError('No encounter declarations in the supplied audit')
    rows = [pack((r['package'], r['declaration'], r['declaration_sha256'], r['kind'])) for r in additions]
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=rw', uri=True, timeout=30)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        check_identity(db, catalog)
        if verify_inventory(db) is None:
            raise ValueError('Build the Boss declaration archive before adding encounter declarations')
        for source, row in zip(additions, rows):
            package, sha, kind, _, _ = row
            existing = db.execute('SELECT source_sha256,source_kind FROM boss_mechanism_declarations WHERE package=?',
                                  (package,)).fetchone()
            if existing is not None:
                if existing != (sha, kind):
                    raise ValueError(f'Conflicting frozen encounter declaration: {package}')
                continue
            db.execute('INSERT INTO boss_mechanism_declarations VALUES (?,?,?,?,?)', row)
            db.execute('INSERT INTO metadata VALUES (?,?)', (SUPPLEMENT_PREFIX + package, encode(source)))
        db.execute(ENCOUNTER_EXPORTS.replace('CREATE TABLE', 'CREATE TABLE IF NOT EXISTS', 1))
        index_encounter_exports(db)
        db.execute('DROP VIEW boss_mechanisms')
        db.execute('DROP VIEW boss_mechanism_exports')
        db.execute(EXPORTS)
        db.execute(MECHANISMS)
        db.execute(ABILITY_ANCESTRY.replace('CREATE TABLE', 'CREATE TABLE IF NOT EXISTS', 1))
        index_abilities(db)
        db.execute('DROP VIEW boss_skill_inventory')
        db.execute(SKILLS)
        return verify_inventory(db)


def build(database, catalog, log=None):
    with closing(connect_readonly(database)) as db:
        check_identity(db, catalog)
        if (existing := verify_inventory(db)) is not None:
            return existing
        with tempfile.TemporaryDirectory(prefix='boss-mechanisms-', dir=database.parent) as directory:
            staging = Path(directory) / 'declarations.sqlite3'
            with closing(sqlite3.connect(staging)) as stage, stage:
                collect(db, stage, log)
                verify_contents(stage, log)
            with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=rw', uri=True, timeout=30)) as target, target:
                target.execute('PRAGMA foreign_keys=ON')
                target.execute('ATTACH DATABASE ? AS staged', (staging.resolve().as_uri() + '?mode=ro',))
                target.execute('BEGIN IMMEDIATE')
                check_identity(target, catalog)
                if (existing := verify_inventory(target)) is not None:
                    return existing
                target.execute(TABLE)
                target.execute('INSERT INTO boss_mechanism_declarations SELECT * FROM staged.boss_mechanism_declarations')
                install_views(target)
                return verify_inventory(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage', type=Path, default=PROJECT_STORAGE)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--verify-content', action='store_true')
    modes.add_argument('--show-export', nargs=2, metavar=('PACKAGE', 'INDEX'))
    modes.add_argument('--supplement-audit', type=Path)
    args = parser.parse_args()
    database = args.storage / DATABASE
    log = lambda message: print(message, flush=True)
    if args.verify_content or args.show_export:
        with closing(connect_readonly(database)) as db:
            if args.show_export:
                package, ordinal = args.show_export
                print(json.dumps(read_export(db, package, int(ordinal)), ensure_ascii=False, indent=2))
            else:
                summary = verify_inventory(db)
                if summary is None:
                    raise ValueError('Boss declaration archive has not been built')
                summary['hashes_verified'] = verify_contents(db, log)
                print(encode(summary))
    elif args.supplement_audit:
        print(encode(add_supplement(database, Catalog(ROOT, args.storage), args.supplement_audit)))
    else:
        print(encode(build(database, Catalog(ROOT, args.storage), log)))
