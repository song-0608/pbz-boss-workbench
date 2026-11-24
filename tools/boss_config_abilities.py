"""Trace offline skill and movement declarations to their Actor Configs."""
from contextlib import closing
from functools import lru_cache
import json
import sqlite3

from boss_catalog_database import DATABASE, encode
from boss_disk_dependencies import native_package
from build_boss_disk_combo_index import Capture, Unresolved, ordered_nodes, split_reference
from prepare_complex_boss_configuration import ability_pools, asset_path, strategies
from research_storage import PROJECT_STORAGE


STRATEGY_EVIDENCE_KEY = 'boss_config_strategy_evidence_version'


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


def subtree_assignment_sites(node, by_branch, tag):
    if not tag:
        return []
    branch = tuple(node['branch'])
    sites = [dict(kind='decorator', name=decorator['name'], branch=node['branch'])
             for decorator in node['decorators'] if decorator['type'] == 'BTDecorator_SetDynamicSubtree_C'
             and tag in (decorator['properties'].get('SubtreesToAssign') or ())]
    if branch and branch[-1] > 0:
        parent = by_branch[branch[:-1]]
        previous = by_branch.get((*branch[:-1], branch[-1] - 1))
        if (parent['type'] == 'BTComposite_Sequence' and previous
                and previous['type'] == 'BTTask_SetDynamicSubtree_C'
                and tag in (previous['properties'].get('SubtreesToAssign') or ())):
            sites.append(dict(kind='preceding_sequence_task', export_index=previous['export_index'],
                              branch=previous['branch']))
    return sites


def strategy_tree(capture, tree, injections):
    issues, nodes = set(tree['issues']), []
    by_branch = {tuple(node['branch']): node for node in tree['nodes']}
    for original in tree['nodes']:
        node = original.copy()
        nodes.append(node)
        props = node['properties']
        if node.get('ability_resolution') == 'unserialized_task_ability':
            method = props.get('AbilityActivationMethod')
            soft = props.get('SoftAbilityToActivate')
            if method == 'EAIAbilityActivationMethod::ByTactic' and props.get('TacticActionTagRequirements'):
                node['selector'] = dict(mode='tactic', requirements=props['TacticActionTagRequirements'],
                                        optional=props.get('IsOptionalTactic'))
                node['ability_resolution'] = 'tactic_selector'
            elif (method == 'EAIAbilityActivationMethod::BySoftClass' and isinstance(soft, dict)
                  and not soft.get('SubPathString') and (path := ability_path(capture, soft))):
                node['ability'] = path
                node['ability_resolution'] = 'soft_class'
        if node['type'] != 'BTTask_RunBehaviorDynamic':
            continue
        tag = (props.get('InjectionTag') or {}).get('TagName')
        selector = dict(mode='dynamic_subtree', injection_tag=tag)
        if sites := subtree_assignment_sites(node, by_branch, tag):
            selector['assignment_sites'] = sites
        for role, value in (('default', props.get('DefaultBehaviorAsset')), ('configured', injections.get(tag))):
            if not value:
                continue
            try:
                ref = split_reference(value)
                if ref[2] != 'BehaviorTree':
                    raise Unresolved('invalid_dynamic_subtree_type')
                capture.exact(*ref)
            except Unresolved as error:
                issues.add(str(error))
            else:
                selector[role] = value
                if role == 'default':
                    node.setdefault('subtree', ref)
        node['selector'] = selector
    if not any(node.get('ability_resolution') == 'unserialized_task_ability' for node in nodes):
        issues.discard('unserialized_task_ability')
    return dict(tree, nodes=nodes, issues=sorted(issues))


def extract(capture, config, tree_for):
    result, issues, selectors = [], [], []
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
        return result, issues, None, selectors
    try:
        ai = capture.resolve(ai_ref)
    except Unresolved as error:
        issues.append(dict(source=config_path, role='AIConfig  Default', reference=ai_ref, reason=str(error)))
        return result, issues, None, selectors

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
                injections, ambiguous = {}, set()
                for entry in obj.get('Properties', {}).get('DynamicSubTrees') or ():
                    tag = (entry.get('Key') or {}).get('TagName')
                    if not tag or tag in injections or tag in ambiguous:
                        issues.append(dict(source=asset_path(obj), role=field, reason='invalid_dynamic_subtree_tag'))
                        injections.pop(tag, None)
                        ambiguous.add(tag)
                        continue
                    injections[tag] = entry['Value']
                trees, gaps = strategies(obj, lambda ref: strategy_tree(capture, tree_for(ref), injections))
                for tree in trees:
                    for node in tree['nodes']:
                        if 'ability' in node:
                            remember(tree['path'], 'strategy_task', node['export_index'], node['ability'], node)
                        if 'selector' in node:
                            if node['selector']['mode'] == 'dynamic_subtree':
                                node['selector'].update(
                                    strategy_path=asset_path(obj),
                                    strategy_sha256=capture.packages[obj['Package'].casefold()]['declaration_sha256'])
                            selectors.append((tree['path'], node['export_index'], tree['declaration_sha256'], node))
                    issues.extend(dict(source=tree['path'], role='strategy_task', reason=reason)
                                  for reason in tree['issues'])
            issues.extend(dict(source=asset_path(obj), role=field, **gap) for gap in gaps)
        except ValueError as error:
            issues.append(dict(source=ai_path, role=field, reference=ref, reason=str(error)))
    return result, issues, ai_path, selectors


def summary(db):
    result = dict(configs=db.execute('SELECT count(*) FROM boss_combat_config_index').fetchone()[0],
                links=db.execute('SELECT count(*) FROM boss_config_ability_links').fetchone()[0],
                matched_skill_classes=db.execute('SELECT count(DISTINCT matched_skill) FROM boss_config_ability_links').fetchone()[0],
                declaration_only_links=db.execute("SELECT count(*) FROM boss_config_ability_links WHERE resolution='class_declaration'").fetchone()[0],
                unresolved_links=db.execute("SELECT count(*) FROM boss_config_ability_links WHERE resolution='unresolved'").fetchone()[0],
                motion_fields=db.execute('SELECT count(*) FROM boss_config_motion').fetchone()[0],
                diagnostics=db.execute('SELECT sum(json_array_length(diagnostics)) FROM boss_combat_config_index').fetchone()[0])
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='boss_config_strategy_selectors'").fetchone():
        result['strategy_selectors'] = dict(db.execute('''SELECT mode,count(*)
            FROM boss_config_strategy_selectors GROUP BY mode'''))
        local_assignments, = db.execute('''SELECT count(*) FROM boss_config_strategy_selectors WHERE mode='dynamic_subtree'
            AND json_array_length(payload,'$.selector.assignment_sites')>0''').fetchone()
        if local_assignments:
            result['subtree_selectors_with_assignment_sites'] = local_assignments
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='boss_config_state_machines'").fetchone():
        configs, resources = db.execute('''SELECT count(*),count(DISTINCT state_machine)
            FROM boss_config_state_machines''').fetchone()
        result['state_machines'] = dict(configs=configs, resources=resources)
    return result


def database_capture(db):
    return Capture([dict(package=p, declaration=path, declaration_sha256=sha) for p, path, sha in db.execute('''
        SELECT package,declaration,declaration_sha256 FROM packages
        UNION ALL SELECT package,declaration,declaration_sha256 FROM additional_boss_packages''')])


def configuration_sources(db, capture):
    tree_for = lru_cache(maxsize=512)(lambda ref: ordered_nodes(capture, ref))
    configs = db.execute("""SELECT folder,payload FROM combat_config_exports e JOIN combat_configs USING(package)
        WHERE export_type='PDA_ActorConfig_C' ORDER BY folder,package,export_index""")
    for folder, raw in configs:
        config = json.loads(raw)
        yield asset_path(config), folder, extract(capture, config, tree_for)


def selector_rows(path, selectors):
    return [(path, tree, index, sha, node['selector']['mode'], encode(node))
            for tree, index, sha, node in selectors]


def verify_strategy_evidence(db):
    version = db.execute('SELECT value FROM metadata WHERE key=?', (STRATEGY_EVIDENCE_KEY,)).fetchone()
    if version is None:
        return False
    if version != ('1',):
        raise ValueError('Unknown Boss strategy evidence version')
    configs = dict((path, (folder, ai, raw)) for path, folder, ai, raw in db.execute(
        'SELECT config_path,folder,ai_config,diagnostics FROM boss_combat_config_index'))
    for path, folder, (_, issues, ai, selectors) in configuration_sources(db, database_capture(db)):
        actual = db.execute('SELECT * FROM boss_config_strategy_selectors WHERE config_path=? ORDER BY tree_path,export_index',
                            (path,)).fetchall()
        if configs.pop(path, None) != (folder, ai, encode(issues)) or actual != sorted(selector_rows(path, selectors)):
            raise ValueError(f'Boss strategy records differ from the captured configuration: {path}')
    if configs:
        raise ValueError('Boss strategy index contains unknown configurations')
    return True


def state_machine_rows(db, capture):
    configs = db.execute('''SELECT e.payload FROM combat_config_exports e
        JOIN boss_combat_config_index c ON c.config_path=json_extract(e.payload,'$.Package') || '.' || e.name
        WHERE e.export_type='PDA_ActorConfig_C' AND c.ai_config IS NOT NULL ORDER BY c.config_path''')
    for raw, in configs:
        config = json.loads(raw)
        ai = capture.resolve(config['Properties']['AIConfig  Default'])
        reference = ai.get('Properties', {}).get('CombatStateMachineConfig')
        if not reference:
            continue
        state = capture.resolve(reference)
        if state['Type'] not in ('SGameAIStateMachineConfig', 'BP_PBZAIStateMachineConfig_C'):
            raise ValueError(f'Unexpected combat state machine type for {asset_path(ai)}')
        source = capture.packages[state['Package'].casefold()]
        yield (asset_path(config), asset_path(ai), asset_path(state), source['package'],
               source['declaration_sha256'], encode(reference))


def verify_state_machines(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='boss_config_state_machines'").fetchone():
        return
    actual = db.execute('SELECT * FROM boss_config_state_machines ORDER BY config_path').fetchall()
    if actual != list(state_machine_rows(db, database_capture(db))):
        raise ValueError('Combat state machine associations differ from the captured declarations')


def populate(db):
    capture = database_capture(db)
    ids = {path.casefold(): path for path, in db.execute('SELECT class_path FROM skills')}
    declared_classes = {(mount + '.' + name).casefold() for mount, name in db.execute('''
        SELECT mount,name FROM native_package_exports WHERE export_type LIKE '%BlueprintGeneratedClass' ''')}
    declared_classes.update((native_package(package) + '.' + name).casefold() for package, name in db.execute('''
        SELECT package,name FROM additional_boss_exports WHERE export_type LIKE '%BlueprintGeneratedClass' '''))
    db.execute('''CREATE TABLE IF NOT EXISTS boss_combat_config_index (
        config_path TEXT PRIMARY KEY, folder TEXT NOT NULL, ai_config TEXT, diagnostics TEXT NOT NULL
    ) WITHOUT ROWID''')
    db.execute('DROP TABLE IF EXISTS boss_config_ability_links')
    db.execute('DROP TABLE IF EXISTS boss_config_strategy_selectors')
    db.execute('DROP TABLE IF EXISTS boss_config_state_machines')
    db.execute('''CREATE TABLE boss_config_ability_links (
        config_path TEXT NOT NULL REFERENCES boss_combat_config_index, source_path TEXT NOT NULL, relation TEXT NOT NULL,
        ordinal INTEGER NOT NULL, ability_path TEXT NOT NULL, matched_skill TEXT REFERENCES skills(class_path),
        resolution TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(config_path,source_path,relation,ordinal)
    ) WITHOUT ROWID''')
    db.execute('''CREATE TABLE boss_config_strategy_selectors (
        config_path TEXT NOT NULL REFERENCES boss_combat_config_index, tree_path TEXT NOT NULL,
        export_index INTEGER NOT NULL, source_sha256 TEXT NOT NULL, mode TEXT NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY(config_path,tree_path,export_index)
    ) WITHOUT ROWID''')
    db.execute('''CREATE TABLE boss_config_state_machines (
        config_path TEXT PRIMARY KEY REFERENCES boss_combat_config_index,
        ai_config TEXT NOT NULL, state_machine TEXT NOT NULL, source_package TEXT NOT NULL,
        source_sha256 TEXT NOT NULL, reference TEXT NOT NULL
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
    for path, folder, (links, issues, ai, selectors) in configuration_sources(db, capture):
        db.execute('INSERT INTO boss_combat_config_index VALUES (?,?,?,?)', (path, folder, ai, encode(issues)))
        db.executemany('INSERT INTO boss_config_strategy_selectors VALUES (?,?,?,?,?,?)', selector_rows(path, selectors))
        for source, relation, i, ability, row in links:
            key = ability.casefold()
            resolution = 'skill' if key in ids else 'class_declaration' if key in declared_classes else 'unresolved'
            db.execute('INSERT INTO boss_config_ability_links VALUES (?,?,?,?,?,?,?,?)',
                       (path, source, relation, i, ability, ids.get(key), resolution, encode(row)))
    db.executemany('INSERT INTO boss_config_state_machines VALUES (?,?,?,?,?,?)', state_machine_rows(db, capture))
    result = summary(db)
    db.execute("INSERT OR REPLACE INTO metadata VALUES ('boss_config_ability_counts',?)", (encode(result),))
    db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', (STRATEGY_EVIDENCE_KEY, '1'))
    return result


if __name__ == '__main__':
    path = PROJECT_STORAGE / DATABASE
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        print(json.dumps(populate(db), ensure_ascii=False))
