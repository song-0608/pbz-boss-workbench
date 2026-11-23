"""Materialize the verified PBZ disk captures as a read-only workbench database."""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from build_boss_disk_combo_index import Unresolved, split_reference
from build_boss_disk_repertoire import read_verified
from research_storage import PROJECT_STORAGE, ROOT
from workbench_skill_catalog import Catalog


VERSION = 3
APPLICATION_ID = 0x50425A43
DATABASE = Path('创作协作/Boss数据库/PBZ-Boss.sqlite3')
PHASE = re.compile(r'_P[1-9][0-9]*$')
NPC_BASE = '/Game/PBZContent/Blueprint/Character/NPC/BP_NPC_Base.BP_NPC_Base_C'
NPC_RENEWAL = '/Game/RenewalContent/Prototypes/Character/BP_RenewalNPC.BP_RenewalNPC_C'
CONFIG_NAME = re.compile(r'^(?:actor_?c(?:onfig)?_|(?:pbz)?ai(?:strategy|statemachine)?config|(?:pbz)?abilitypool)',
                         re.IGNORECASE)
CONFIG_TYPES = {'PDA_ActorConfig_C', 'PDA_PBZAIConfig_C', 'SGameAIAbilityPool',
                'BP_PBZAIStrategyConfig_C', 'BP_PBZAIStateMachineConfig_C'}

SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE folders (
    folder TEXT PRIMARY KEY, family TEXT NOT NULL, priority INTEGER NOT NULL UNIQUE,
    phase_groups INTEGER NOT NULL, skill_count INTEGER NOT NULL, combo_count INTEGER NOT NULL,
    tree_count INTEGER NOT NULL, node_count INTEGER NOT NULL, subtree_count INTEGER NOT NULL,
    root_packages INTEGER NOT NULL, native_routes TEXT NOT NULL
);
CREATE TABLE packages (
    package TEXT PRIMARY KEY, folder TEXT NOT NULL, declaration TEXT NOT NULL,
    declaration_sha256 TEXT NOT NULL
);
CREATE TABLE package_references (
    package TEXT NOT NULL REFERENCES packages, reference TEXT NOT NULL, status TEXT NOT NULL,
    PRIMARY KEY (package, reference, status)
) WITHOUT ROWID;
CREATE TABLE actor_variants (
    class_path TEXT PRIMARY KEY, folder TEXT NOT NULL REFERENCES folders,
    package TEXT NOT NULL REFERENCES packages, export_index INTEGER NOT NULL, ancestry TEXT NOT NULL
);
CREATE INDEX actor_variants_folder ON actor_variants(folder, class_path);
CREATE TABLE combat_configs (
    package TEXT PRIMARY KEY REFERENCES packages, folder TEXT NOT NULL REFERENCES folders, export_count INTEGER NOT NULL
);
CREATE INDEX combat_configs_folder ON combat_configs(folder, package);
CREATE TABLE combat_config_exports (
    package TEXT NOT NULL REFERENCES combat_configs, export_index INTEGER NOT NULL, name TEXT NOT NULL,
    export_type TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY (package, export_index)
);
CREATE TABLE skills (
    class_path TEXT PRIMARY KEY, folder TEXT NOT NULL REFERENCES folders,
    package TEXT NOT NULL REFERENCES packages, native_route TEXT NOT NULL, timeline_owner TEXT,
    payload TEXT NOT NULL, adaptation TEXT NOT NULL
);
CREATE INDEX skills_folder ON skills(folder, class_path);
CREATE TABLE timelines (
    owner TEXT NOT NULL, ordinal INTEGER NOT NULL, name TEXT NOT NULL,
    declaration_sha256 TEXT NOT NULL, declared_end_seconds REAL, PRIMARY KEY (owner, ordinal)
);
CREATE TABLE timeline_actions (
    owner TEXT NOT NULL, timeline INTEGER NOT NULL, ordinal INTEGER NOT NULL,
    action_type TEXT, start_seconds REAL, duration_seconds REAL, payload TEXT NOT NULL,
    PRIMARY KEY (owner, timeline, ordinal),
    FOREIGN KEY (owner, timeline) REFERENCES timelines(owner, ordinal)
);
CREATE TABLE scripts (
    package TEXT PRIMARY KEY REFERENCES packages, path TEXT NOT NULL, sha256 TEXT NOT NULL
);
CREATE TABLE script_functions (
    package TEXT NOT NULL REFERENCES scripts, ordinal INTEGER NOT NULL, name TEXT NOT NULL,
    complete INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY (package, ordinal)
);
CREATE TABLE combo_parents (class_path TEXT PRIMARY KEY REFERENCES skills, payload TEXT NOT NULL);
CREATE TABLE combo_trees (path TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE combo_links (
    parent TEXT NOT NULL REFERENCES combo_parents, tree TEXT NOT NULL REFERENCES combo_trees,
    PRIMARY KEY (parent, tree)
) WITHOUT ROWID;
CREATE TABLE combo_references (
    parent TEXT NOT NULL REFERENCES combo_parents, child TEXT NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (parent, child)
) WITHOUT ROWID;
CREATE INDEX combo_reverse ON combo_references(child, parent);
CREATE TABLE capture_gaps (
    category TEXT NOT NULL, identifier TEXT NOT NULL, ordinal INTEGER NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (category, ordinal)
);
CREATE VIEW boss_adaptation_queue AS
SELECT f.priority, f.folder, f.family, s.class_path, s.native_route,
       json_extract(s.adaptation, '$.next_action') AS next_action
FROM skills s JOIN folders f ON f.folder=s.folder;
"""

COMPLEX_CONFIGS = """
CREATE TABLE IF NOT EXISTS complex_boss_profiles (
    folder TEXT PRIMARY KEY REFERENCES folders(folder),
    class_path TEXT REFERENCES actor_variants(class_path),
    payload TEXT NOT NULL
)
"""


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def connect_readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)


def complex_config_rows(db, folder=None):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='complex_boss_profiles'").fetchone():
        return []
    if folder is not None:
        return db.execute('SELECT folder, class_path, payload FROM complex_boss_profiles WHERE folder=?', (folder,)).fetchall()
    return db.execute('SELECT folder, class_path, payload FROM complex_boss_profiles ORDER BY folder').fetchall()


def write_complex_configs(db, rows):
    previous = {folder: json.loads(raw) for folder, _, raw in complex_config_rows(db)}
    records = []
    for folder, actor, raw in rows:
        old = previous.get(folder, {})
        if 'trial' in old:
            entry = json.loads(raw)
            if all(old[key] == entry[key] for key in ('class_path', 'bindings', 'metadata_receipt_sha256')):
                raw = encode(dict(entry, trial=old['trial'], native_grants_verified=True))
        records.append((folder, actor, raw))
    db.execute(COMPLEX_CONFIGS)
    db.execute('DELETE FROM complex_boss_profiles')
    db.executemany('INSERT INTO complex_boss_profiles (folder,class_path,payload) VALUES (?,?,?)', records)


def priorities(roles, parents, trees):
    families = {folder: PHASE.sub('', re.sub(r'^[0-9]+_', '', folder)).casefold() for folder in roles}
    family_sizes = Counter(families.values())
    by_folder = defaultdict(list)
    for parent in parents.values():
        by_folder[parent['folder']].append(parent)
    rows = []
    for folder, role in roles.items():
        combos = by_folder[folder]
        paths = {path for parent in combos for path in parent['trees']}
        nodes = [node for path in paths for node in trees[path]['nodes']]
        branches = sum(len(node['branch']) > 0 for node in nodes)
        subtrees = sum('subtree' in node for node in nodes)
        phase_groups = family_sizes[families[folder]]
        skill_count = len(role['skills'])
        # Prioritize large tree graphs and repeated stages. Keep the ultimate boss
        # visible even though only one of its combo entry points was decoded.
        score = 3 * branches + 4 * subtrees + 12 * len(combos) + 35 * (phase_groups - 1) + skill_count
        key = (folder == 'native_support', folder != '888_UltimateBoss', -score, folder)
        rows.append((key, (folder, families[folder], phase_groups, skill_count, len(combos),
            len(paths), len(nodes), subtrees, role['root_packages'], encode(role['native_routes']))))
    return [(*row[:2], i, *row[2:]) for i, (_, row) in enumerate(sorted(rows), 1)]


def actor_variants(packages, folders):
    """Index captured generated classes only when their exact ancestry reaches a known NPC base."""
    classes = {}
    for package, item in packages.items():
        for export in item.get('parent_classes', ()):
            mount, name = export['class_path'].rsplit('.', 1)
            key = (mount.casefold(), export['export_index'], export['export_type'], name)
            if key in classes:
                raise ValueError(f'Duplicate captured class export: {export["class_path"]}')
            classes[key] = package, item['folder'], export
    for package, folder, export in classes.values():
        class_path = export['class_path']
        if folder not in folders or not class_path.startswith(f'/PBZCombatAsset/ActorData/Mobs/{folder}/'):
            continue
        ancestry = [class_path]
        current = export
        while len(ancestry) < 64:
            try:
                mount, index, kind, name = split_reference(current['serialized_super'])
            except Unresolved:
                break
            parent = classes.get((mount.casefold(), index, kind, name))
            if parent is None:
                break
            current = parent[2]
            path = current['class_path']
            if path in ancestry:
                break
            ancestry.append(path)
            if path in (NPC_BASE, NPC_RENEWAL):
                yield class_path, folder, package, export['export_index'], encode(ancestry)
                break


def capture_inputs(catalog):
    directory = catalog.directory / 'convergence-verified'
    summary = catalog.repertoire_summary
    workflow = read_verified(directory / 'result.json', summary['workflow_sha256'])
    scan_path = Path(workflow['final_scan'])
    if scan_path.parent.resolve() != directory.resolve() or workflow['final_scan_sha256'] != summary['scan_sha256']:
        raise ValueError('Terminal scan identity differs from repertoire')
    scan = read_verified(scan_path, summary['scan_sha256'])
    queue = read_verified(directory / 'adaptation-queue-v1.json', summary['queue_sha256'])
    if (scan['pending_roots'] or scan['pending_dependency_count'] or not scan['declaration_contents_verified']
            or queue['disk_dependency_scan_sha256'] != summary['scan_sha256']):
        raise ValueError('Terminal offline capture required')
    return scan, queue


def insert_configs(db, packages, folder_rank):
    candidates = [(folder_rank[item['folder']], name) for name, item in packages.items()
                  if item['folder'] in folder_rank and CONFIG_NAME.match(Path(name).stem)]
    counts = Counter()
    for _, name in sorted(candidates):
        item = packages[name]
        exports = read_verified(item['declaration'], item['declaration_sha256'])
        if not any(obj['Type'] in CONFIG_TYPES for obj in exports):
            continue
        db.execute('INSERT INTO combat_configs VALUES (?,?,?)', (name, item['folder'], len(exports)))
        db.executemany('INSERT INTO combat_config_exports VALUES (?,?,?,?,?)', (
            (name, i, obj['Name'], obj['Type'], encode(obj)) for i, obj in enumerate(exports)))
        counts['combat_configs'] += 1
        counts['combat_config_exports'] += len(exports)
    return dict(combat_configs=counts['combat_configs'], combat_config_exports=counts['combat_config_exports'])


def insert_catalog(db, catalog, *, log=None):
    roles = {folder: catalog.role(folder) for folder in catalog.folders}
    trees = read_verified(catalog.combo_directory / 'trees.json', catalog.combo_files['trees.json'])
    folder_rows = priorities(roles, catalog.parents, trees)
    folder_rank = {row[0]: row[2] for row in folder_rows}
    scan, queue = capture_inputs(catalog)
    adaptation = {row['class_path']: row for row in queue['rows']}
    insert = db.executemany
    insert('INSERT INTO folders VALUES (?,?,?,?,?,?,?,?,?,?,?)', folder_rows)
    packages = {item['package']: item for item in scan['packages']}
    insert('INSERT INTO packages VALUES (?,?,?,?)', (
        (name, item['folder'], item['declaration'], item['declaration_sha256']) for name, item in packages.items()))
    actors = list(actor_variants(packages, roles))
    insert('INSERT INTO actor_variants VALUES (?,?,?,?,?)', actors)
    config_counts = insert_configs(db, packages, folder_rank)
    for folder, *_ in folder_rows:
        rows = roles[folder]['skills']
        insert('INSERT INTO skills VALUES (?,?,?,?,?,?,?)', (
            (row['class_path'], folder, row['package'], row['native_route'], row['timeline_owner'], encode(row),
             encode(adaptation.pop(row['class_path']))) for row in rows))
    if adaptation:
        raise ValueError('Adaptation queue contains classes missing from the repertoire')
    if log:
        log('完成全部资源分组和技能入库，正在写入动作时间线、连招、脚本和依赖。')

    for path, tree in trees.items():
        db.execute('INSERT INTO combo_trees VALUES (?,?)', (path, encode(tree)))
    for path, row in catalog.parents.items():
        db.execute('INSERT INTO combo_parents VALUES (?,?)', (path, encode(row)))
        insert('INSERT INTO combo_links VALUES (?,?)', ((path, tree) for tree in row['trees']))
        insert('INSERT INTO combo_references VALUES (?,?,?)',
               ((path, child['class_path'], encode(child)) for child in row['referenced_abilities']))

    captures = catalog.repertoire
    timelines = read_verified(captures / 'timelines.json', catalog.files['timelines.json'])
    for owner, data in timelines.items():
        for ordinal, timeline in enumerate(data['timelines']):
            db.execute('INSERT INTO timelines VALUES (?,?,?,?,?)', (owner, ordinal,
                timeline['name'], data['declaration_sha256'], timeline['declared_end_seconds']))
            insert('INSERT INTO timeline_actions VALUES (?,?,?,?,?,?,?)', (
                (owner, ordinal, row['ordinal'], row['action_type'], row['start_seconds'],
                 row['duration_seconds'], encode(row)) for row in timeline['actions']))

    scripts = read_verified(captures / 'scripts.json', catalog.files['scripts.json'])
    for package, receipt in sorted(scripts.items(), key=lambda item: (
            folder_rank.get(packages[item[0]]['folder'], len(folder_rows)), item[0])):
        functions = read_verified(receipt['path'], receipt['sha256'])
        if len(functions) != receipt['functions'] or sum(row['complete'] for row in functions) != receipt['complete_functions']:
            raise ValueError(f'Function counts differ from verified receipt: {package}')
        db.execute('INSERT INTO scripts VALUES (?,?,?)', (package, receipt['path'], receipt['sha256']))
        insert('INSERT INTO script_functions VALUES (?,?,?,?,?)', ((package, i, row['name'], row['complete'],
            encode(row)) for i, row in enumerate(functions)))

    insert('INSERT INTO package_references VALUES (?,?,?)', (
        (name, row['reference'], row['status']) for name, package in packages.items()
        for row in package['references']))
    gaps = {category: scan[category] for category in ('failed_dependencies', 'deferred_dependencies', 'unindexed_references')}
    for category in ('root-reference-gaps', 'quarantined'):
        name = category + '.json'
        gaps[category] = read_verified(captures / name, catalog.files[name])
    actor_folders = {row[1] for row in actors}
    gaps['no_captured_actor_identity'] = [dict(reference=folder, folder=folder)
        for folder in roles if folder != 'native_support' and folder not in actor_folders]
    for category, rows in gaps.items():
        insert('INSERT INTO capture_gaps VALUES (?,?,?,?)', (
            (category, row if isinstance(row, str) else row.get('reference') or row.get('class_path') or row['package'],
             i, encode(row)) for i, row in enumerate(rows)))
    expected = dict(folders=len(roles), skills=catalog.repertoire_summary['ability_classes'] - catalog.repertoire_summary['quarantined'],
        packages=len(packages), package_references=sum(len(row['references']) for row in packages.values()),
        actor_variants=len(actors),
        combo_parents=catalog.combo_summary['parents'], combo_trees=catalog.combo_summary['trees'],
        timelines=sum(len(d['timelines']) for d in timelines.values()), timeline_actions=sum(len(t['actions']) for d in timelines.values()
            for t in d['timelines']), scripts=catalog.repertoire_summary['script_packages'],
        script_functions=catalog.repertoire_summary['function_exports'], capture_gaps=sum(map(len, gaps.values())),
        **config_counts)
    insert('INSERT INTO metadata VALUES (?,?)', ((key, encode(value)) for key, value in {
        'source_digests': catalog.source_digests, 'expected_counts': expected,
        'game_started': False, 'activation_allowed': False}.items()))


def check_identity(db, catalog):
    if (db.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID
            or db.execute('PRAGMA user_version').fetchone()[0] != VERSION):
        raise ValueError('Boss 数据库格式不匹配')
    row = db.execute("SELECT value FROM metadata WHERE key='source_digests'").fetchone()
    if not row or json.loads(row[0]) != catalog.source_digests:
        raise ValueError('Boss 数据库来源与工作台技能目录不匹配')


def verify(database, catalog):
    with closing(connect_readonly(database)) as db:
        check_identity(db, catalog)
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Boss 数据库完整性检查失败')
        expected = json.loads(db.execute("SELECT value FROM metadata WHERE key='expected_counts'").fetchone()[0])
        tables = ('folders', 'skills', 'packages', 'package_references', 'actor_variants',
                  'combat_configs', 'combat_config_exports', 'combo_parents', 'combo_trees',
                  'timelines', 'timeline_actions', 'scripts', 'script_functions', 'capture_gaps')
        counts = {name: db.execute(f'SELECT count(*) FROM {name}').fetchone()[0] for name in tables}
        if counts != expected or counts['folders'] != len(catalog.folders):
            raise ValueError(f'Boss 数据库记录数差异: {counts} != {expected}')
        profiles = complex_config_rows(db)
        for folder, actor, raw in profiles:
            entry = json.loads(raw)
            trial = entry.get('trial')
            if (entry['folder'] != folder or entry['class_path'] != actor or entry['playable'] is not False
                    or entry['metadata_verified'] != (actor is not None and bool(entry['bindings']))
                    or entry['native_grants_verified'] != bool(trial)
                    or (trial and (trial['class_path'] != actor or trial['playable'] is not False
                        or trial['owned_cleanup_verified'] is not True
                        or any(trial['native_grant_counts'].get(slot['class_path']) != 1 for slot in entry['bindings'])))):
                raise ValueError(f'复杂 Boss 配置状态不一致: {folder}')
        ranked = db.execute('SELECT folder, skill_count, combo_count, tree_count, node_count, phase_groups'
                            ' FROM folders ORDER BY priority LIMIT 12').fetchall()
        supplements = {}
        native = db.execute("SELECT value FROM metadata WHERE key='native_asset_counts'").fetchone()
        if native:
            from boss_catalog_assets import summarize
            supplements['native_assets'] = summarize(db)
            if supplements['native_assets'] != json.loads(native[0]):
                raise ValueError('Native asset counts differ from the import receipt')
        extension = db.execute("SELECT value FROM metadata WHERE key='native_extension_counts'").fetchone()
        if extension:
            from boss_asset_extensions import TABLES, VIEWS
            value = json.loads(extension[0])
            if value['counts'] != {name: db.execute(f'SELECT count(*) FROM {name}').fetchone()[0] for name in (*TABLES, *VIEWS)}:
                raise ValueError('Additional character counts differ from the import receipt')
            supplements['native_extensions'] = value
        return dict(database=str(database), counts=counts, complex_first=ranked,
                    complex_profiles=len(profiles), game_started=False, **supplements)


def build(root=ROOT, storage=PROJECT_STORAGE, *, verify_only=False, rebuild=False, log=None):
    catalog = Catalog(root, storage)
    database = Path(storage) / DATABASE
    if verify_only or (database.is_file() and not rebuild):
        return verify(database, catalog)
    profiles, native, extensions = [], False, None
    if database.is_file():
        with closing(connect_readonly(database)) as previous:
            sources = previous.execute("SELECT value FROM metadata WHERE key='source_digests'").fetchone()
            if sources and json.loads(sources[0]) == catalog.source_digests:
                profiles = complex_config_rows(previous)
                native = bool(previous.execute("SELECT 1 FROM metadata WHERE key='native_asset_counts'").fetchone())
                extension = previous.execute("SELECT value FROM metadata WHERE key='native_extension_sources'").fetchone()
                extensions = json.loads(extension[0]) if extension else None
    database.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='boss-catalog-', dir=database.parent) as staging:
        candidate = Path(staging) / database.name
        with closing(sqlite3.connect(candidate)) as db, db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute(f'PRAGMA application_id={APPLICATION_ID}')
            db.execute(f'PRAGMA user_version={VERSION}')
            db.executescript(SCHEMA)
            insert_catalog(db, catalog, log=log)
            if profiles:
                write_complex_configs(db, profiles)
            if native:
                from boss_catalog_assets import populate
                scan, _ = capture_inputs(catalog)
                populate(db, scan, log)
            if extensions:
                from boss_asset_extensions import populate, validated_inputs
                index = Path(extensions['index'])
                _, scan, extra, identities = validated_inputs(index, extensions['sources'], root, storage)
                populate(db, scan, extra, identities, index)
        report = verify(candidate, catalog)
        os.replace(candidate, database)
    return dict(report, database=str(database))


class DatabaseCatalog(Catalog):
    def __init__(self, root, storage):
        self.database = Path(storage) / DATABASE

        def read_parents(catalog):
            with closing(connect_readonly(self.database)) as db:
                check_identity(db, catalog)
                parents = db.execute('SELECT payload FROM combo_parents ORDER BY class_path')
                return [json.loads(row[0]) for row in parents]

        super().__init__(root, storage, read_parents=read_parents)
        with closing(connect_readonly(self.database)) as db:
            rows = db.execute('SELECT folder, skill_count, combo_count, tree_count,'
                              ' (SELECT count(*) FROM actor_variants a WHERE a.folder=f.folder)'
                              ' FROM folders f ORDER BY priority')
            self.metrics = {folder: dict(skills=skills, combos=combos, trees=trees, actors=actors)
                            for folder, skills, combos, trees, actors in rows}
            self.native_assets = bool(db.execute("SELECT 1 FROM metadata WHERE key='native_asset_counts'").fetchone())
            self.native_extensions = bool(db.execute("SELECT 1 FROM metadata WHERE key='native_extension_counts'").fetchone())
            if self.native_extensions:
                for folder, count in db.execute('SELECT folder,count(*) FROM additional_boss_actors GROUP BY folder'):
                    self.metrics[folder]['actors'] += count
        if self.metrics.keys() != set(self.folders):
            raise ValueError('Boss 数据库资源分组不完整')

    def ordered_folders(self):
        return tuple(self.metrics)

    def role(self, folder):
        if folder not in self.metrics:
            raise ValueError('未知原生资源分组')
        if folder not in self.roles:
            with closing(connect_readonly(self.database)) as db:
                roots, routes = db.execute('SELECT root_packages, native_routes FROM folders WHERE folder=?',
                                           (folder,)).fetchone()
                rows = [json.loads(row[0]) for row in db.execute(
                    'SELECT payload FROM skills WHERE folder=? ORDER BY class_path', (folder,))]
            if (len(rows) != self.metrics[folder]['skills'] or
                    any(row['activation_allowed'] is not False or row['playable'] is not False for row in rows)):
                raise ValueError('Boss 数据库技能与资源分组不匹配')
            self.roles[folder] = dict(folder=folder, root_packages=roots, native_routes=json.loads(routes), skills=rows)
        return self.roles[folder]

    def tree(self, path):
        with closing(connect_readonly(self.database)) as db:
            row = db.execute('SELECT payload FROM combo_trees WHERE path=?', (path,)).fetchone()
        if not row:
            raise KeyError(path)
        return json.loads(row[0])

    def folder_details(self, folder):
        if folder not in self.metrics:
            raise ValueError('未知原生资源分组')
        with closing(connect_readonly(self.database)) as db:
            family = db.execute('SELECT family FROM folders WHERE folder=?', (folder,)).fetchone()[0]
            related = [row[0] for row in db.execute('SELECT folder FROM folders WHERE family=? ORDER BY priority', (family,))]
            actors = [row[0] for row in db.execute(
                'SELECT class_path FROM actor_variants WHERE folder=? ORDER BY class_path', (folder,))]
            models = db.execute('SELECT e.name, e.export_type FROM combat_config_exports e'
                ' JOIN combat_configs c ON c.package=e.package WHERE c.folder=? ORDER BY e.name', (folder,))
            configs = [f'{name}  {kind}' for name, kind in models if kind in CONFIG_TYPES]
            gaps = [row[0] for row in db.execute(
                "SELECT identifier FROM capture_gaps WHERE category='root-reference-gaps'"
                " AND json_extract(payload, '$.folder')=?", (folder,))]
            complex_profile = next((json.loads(raw) for _, _, raw in complex_config_rows(db, folder)), None)
            additional = db.execute('SELECT class_path,config_path FROM additional_boss_actors WHERE folder=?'
                                    ' ORDER BY class_path', (folder,)).fetchall() if self.native_extensions else []
            coverage = {}
            if self.native_assets:
                coverage = dict(db.execute('''SELECT c.domain,count(*) FROM control_declarations c
                    WHERE c.package IN (SELECT DISTINCT x.package FROM actor_control_sources x
                        JOIN actor_variants a USING(class_path) WHERE a.folder=?) GROUP BY c.domain''', (folder,)))
            if additional:
                for domain, count in db.execute('''SELECT e.domain,count(*) FROM additional_boss_exports e
                    WHERE e.domain IS NOT NULL AND e.domain <> 'animation' AND e.package IN (
                        SELECT DISTINCT package FROM additional_boss_actors WHERE folder=?) GROUP BY e.domain''', (folder,)):
                    coverage[domain] = coverage.get(domain, 0) + count
        lines = [folder]
        if len(related) > 1:
            lines.append('同名阶段资源  ' + ' / '.join(related))
        if complex_profile:
            lines.extend(('', '复杂 Boss 操控配置'))
            if complex_profile['metadata_verified']:
                lines.extend((complex_profile['display_name'], complex_profile['class_path']))
                trial = complex_profile.get('trial')
                if trial:
                    hits = {row['key'] for row in trial['natural_completions'] if row['damage_observed']}
                    lines.append(f"研究副本已验证原生授予，{len(hits)} 个键位产生伤害。会话 {trial['session']}")
                else:
                    lines.append('本体与技能类已核对，原生授予与操控待验')
                lines.extend(f"{row['key']}  {row['class_path'].rsplit('.', 1)[-1]}"
                             + ('（跨阶段共享）' if row['shared'] else '') for row in complex_profile['bindings'])
            else:
                lines.append('已找到磁盘角色蓝图，待核对运行时技能类' if additional else '待核对战斗本体或技能类')
            lines.append(f"技能池 {len(complex_profile['pools'])}，策略树 {len(complex_profile['strategy_trees'])}")
        lines.extend(('', '角色蓝图', *(actors or ([] if additional else ['待核对主身蓝图']))))
        lines.extend(f'{actor}\n  Actor Config  {config}' for actor, config in additional)
        if coverage:
            labels = {'movement': '移动', 'camera': '镜头', 'input': '输入', 'targeting': '锁敌', 'character': '角色'}
            lines.extend(('', '角色及父类的磁盘声明', ' / '.join(f'{labels[key]} {value}' for key, value in coverage.items())))
        if configs:
            lines.extend(('', '角色与战斗配置', *configs))
        if gaps:
            lines.extend(('', '直接资源缺口', *gaps))
        return '\n'.join(lines)

    def details(self, skill):
        description = super().details(skill)
        if not skill['timeline_owner']:
            return description
        with closing(connect_readonly(self.database)) as db:
            rows = db.execute('SELECT t.ordinal, t.name, a.start_seconds, a.duration_seconds, a.action_type'
                              ' FROM timelines t LEFT JOIN timeline_actions a ON a.owner=t.owner AND a.timeline=t.ordinal'
                              ' WHERE t.owner=? ORDER BY t.ordinal, a.ordinal', (skill['timeline_owner'],)).fetchall()
            animations = db.execute('''SELECT DISTINCT target_mount,target_name,target_type,package
                                       FROM skill_animation_links WHERE owner=? ORDER BY target_mount,target_name''',
                                    (skill['timeline_owner'],)).fetchall() if self.native_assets else []
        if not rows:
            return description
        lines = [description, '', '时间线动作（秒）']
        current = None
        for ordinal, name, start, duration, action in rows:
            if ordinal != current:
                current = ordinal
                lines.append(name)
            if action:
                at = '?' if start is None else f'{start:g}'
                length = '?' if duration is None else f'{duration:g}'
                lines.append(f'  {at}  {action}  {length}')
        if animations:
            lines.extend(('', '关联动画声明'))
            lines.extend(f'{mount}.{name}  {kind}' + ('' if package else '（待核对）')
                         for mount, name, kind, package in animations)
        return '\n'.join(lines)


def open_catalog(root, storage=PROJECT_STORAGE):
    if (Path(storage) / DATABASE).is_file():
        return DatabaseCatalog(root, storage)
    return Catalog(root, storage)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage', type=Path, default=PROJECT_STORAGE)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--verify', action='store_true')
    mode.add_argument('--rebuild', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(storage=args.storage, verify_only=args.verify, rebuild=args.rebuild,
                           log=lambda message: print(message, flush=True)), ensure_ascii=False, indent=2))
