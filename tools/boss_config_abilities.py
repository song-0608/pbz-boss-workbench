"""Trace offline skill and movement declarations to their Actor Configs."""
from contextlib import closing
from functools import lru_cache
import json
import sqlite3

from boss_catalog_database import DATABASE, encode
from boss_disk_dependencies import native_package
from build_boss_disk_combo_index import Capture, Unresolved, ordered_nodes
from prepare_complex_boss_configuration import ability_pools, asset_path, strategies
from research_storage import PROJECT_STORAGE


def ability_path(capture, value):
    if isinstance(value, dict):
        if value.get('ObjectPath', '').startswith('/Script/'):
            return None
        if 'AssetPathName' in value:
            value = value['AssetPathName']
        else:
            result = capture.resolve(value)
            return asset_path(result)
    return value if isinstance(value, str) and value.startswith('/') and '.' in value else None


def extract(capture, config, tree_for):
    result, issues = [], []
    config_path = asset_path(config)

    def remember(source, role, ordinal, ref, payload):
        try:
            path = ability_path(capture, ref)
        except Unresolved as error:
            issues.append(dict(source=source, role=role, ordinal=ordinal, reference=ref, reason=str(error)))
        else:
            if path:
                result.append((source, role, ordinal, path, payload))

    props = config.get('Properties', {})
    for field in ('Abilities', 'Passive Abilities'):
        for ordinal, ref in enumerate(props.get(field) or ()):
            remember(config_path, field, ordinal, ref, ref)
    ai_ref = props.get('AIConfig  Default')
    if not ai_ref:
        return result, issues, None
    try:
        ai = capture.resolve(ai_ref)
    except Unresolved as error:
        issues.append(dict(source=config_path, role='AIConfig  Default', reference=ai_ref, reason=str(error)))
        return result, issues, None

    ai_path = asset_path(ai)
    props = ai.get('Properties', {})
    for field in ('AbilityPool', 'StrategyConfig'):
        if not (ref := props.get(field)):
            continue
        try:
            obj = capture.resolve(ref)
            if field == 'AbilityPool':
                pools, gaps = ability_pools(capture, obj)
                for pool in pools:
                    for ordinal, action in enumerate(pool['tactics']):
                        remember(pool['path'], 'tactic', ordinal, action['class_path'], action)
                    for ordinal, entry in enumerate(pool['ability_tags']):
                        remember(pool['path'], 'tag_map', ordinal, entry.get('Key'), entry)
            else:
                trees, gaps = strategies(obj, tree_for)
                for tree in trees:
                    for node in tree['nodes']:
                        if 'ability' in node:
                            remember(tree['path'], 'strategy_task', node['export_index'], node['ability'], node)
                    issues.extend(dict(source=tree['path'], role='strategy_task', reason=reason)
                                  for reason in tree['issues'])
            issues.extend(dict(source=asset_path(obj), role=field, **gap) for gap in gaps)
        except ValueError as error:
            issues.append(dict(source=ai_path, role=field, reference=ref, reason=str(error)))
    return result, issues, ai_path


def summary(db):
    return dict(configs=db.execute('SELECT count(*) FROM boss_combat_config_index').fetchone()[0],
                links=db.execute('SELECT count(*) FROM boss_config_ability_links').fetchone()[0],
                matched_skill_classes=db.execute('SELECT count(DISTINCT matched_skill) FROM boss_config_ability_links').fetchone()[0],
                declaration_only_links=db.execute("SELECT count(*) FROM boss_config_ability_links WHERE resolution='class_declaration'").fetchone()[0],
                unresolved_links=db.execute("SELECT count(*) FROM boss_config_ability_links WHERE resolution='unresolved'").fetchone()[0],
                motion_fields=db.execute('SELECT count(*) FROM boss_config_motion').fetchone()[0],
                diagnostics=db.execute('SELECT sum(json_array_length(diagnostics)) FROM boss_combat_config_index').fetchone()[0])


def populate(db):
    packages = [dict(package=p, declaration=path, declaration_sha256=sha) for p, path, sha in db.execute('''
        SELECT package,declaration,declaration_sha256 FROM packages
        UNION ALL SELECT package,declaration,declaration_sha256 FROM additional_boss_packages''')]
    capture = Capture(packages)
    tree_for = lru_cache(maxsize=512)(lambda ref: ordered_nodes(capture, ref))
    ids = {path.casefold(): path for path, in db.execute('SELECT class_path FROM skills')}
    declared_classes = {(mount + '.' + name).casefold() for mount, name in db.execute('''
        SELECT mount,name FROM native_package_exports WHERE export_type LIKE '%BlueprintGeneratedClass' ''')}
    declared_classes.update((native_package(package) + '.' + name).casefold() for package, name in db.execute('''
        SELECT package,name FROM additional_boss_exports WHERE export_type LIKE '%BlueprintGeneratedClass' '''))
    db.execute('''CREATE TABLE IF NOT EXISTS boss_combat_config_index (
        config_path TEXT PRIMARY KEY, folder TEXT NOT NULL, ai_config TEXT, diagnostics TEXT NOT NULL
    ) WITHOUT ROWID''')
    db.execute('DROP TABLE IF EXISTS boss_config_ability_links')
    db.execute('''CREATE TABLE boss_config_ability_links (
        config_path TEXT NOT NULL REFERENCES boss_combat_config_index, source_path TEXT NOT NULL, relation TEXT NOT NULL,
        ordinal INTEGER NOT NULL, ability_path TEXT NOT NULL, matched_skill TEXT REFERENCES skills(class_path),
        resolution TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(config_path,source_path,relation,ordinal)
    ) WITHOUT ROWID''')
    db.execute('''CREATE VIEW IF NOT EXISTS boss_config_motion AS
       SELECT p.config_path,p.folder,j.key AS field,j.value,j.type
       FROM boss_combat_config_index p JOIN combat_config_exports e
       ON p.config_path=json_extract(e.payload,'$.Package') || '.' || e.name,
       json_each(e.payload,'$.Properties."Attribute Data"') j
       WHERE e.export_type='PDA_ActorConfig_C' AND j.key IN ('WalkSpeed','JogSpeed','SprintSpeed','CrouchSpeed')
       UNION ALL
       SELECT p.config_path,p.folder,j.key,j.value,j.type
       FROM boss_combat_config_index p JOIN combat_config_exports e
       ON p.config_path=json_extract(e.payload,'$.Package') || '.' || e.name,
       json_each(e.payload,'$.Properties') j
       WHERE e.export_type='PDA_ActorConfig_C' AND j.key IN ('Normal Parameters','Walk Parameters','Sprint Parameters',
         'Crouch Parameters','Crouch Slow Parameters','DriverConfig','Lock Sockets')''')
    db.execute('DELETE FROM boss_combat_config_index')
    configs = db.execute("""SELECT folder,payload FROM combat_config_exports e JOIN combat_configs USING(package)
        WHERE export_type='PDA_ActorConfig_C' ORDER BY folder,package,export_index""")
    for folder, raw in configs:
        config = json.loads(raw)
        path = asset_path(config)
        links, issues, ai = extract(capture, config, tree_for)
        db.execute('INSERT INTO boss_combat_config_index VALUES (?,?,?,?)', (path, folder, ai, encode(issues)))
        for source, relation, i, ability, row in links:
            key = ability.casefold()
            resolution = 'skill' if key in ids else 'class_declaration' if key in declared_classes else 'unresolved'
            db.execute('INSERT INTO boss_config_ability_links VALUES (?,?,?,?,?,?,?,?)',
                       (path, source, relation, i, ability, ids.get(key), resolution, encode(row)))
    result = summary(db)
    db.execute("INSERT OR REPLACE INTO metadata VALUES ('boss_config_ability_counts',?)", (encode(result),))
    return result


if __name__ == '__main__':
    path = PROJECT_STORAGE / DATABASE
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        print(json.dumps(populate(db), ensure_ascii=False))
