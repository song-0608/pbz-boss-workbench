"""Resolve complex Boss defaults, native AI pools and exact next verification jobs."""
import argparse
from contextlib import closing
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import boss_metadata_jobs as metadata
from boss_adaptation_workflow import BUILD, ROOT, sha
from boss_catalog_database import DATABASE, Catalog, check_identity, connect_readonly
from build_boss_disk_combo_index import Capture, Unresolved, ordered_nodes, split_reference
from research_storage import PROJECT_STORAGE


PREFIX = '/PBZCombatAsset/ActorData/Mobs/'
OUTPUT = DATABASE.parent / '复杂Boss配置'
# Explicit review of combat bodies. Closely named cinematic, helper, summon
# and stand-in classes are separate variants even if they share an Actor Config.
ROLES = (
    ('888_UltimateBoss', None, 'ActorC_UltimateBoss'),
    ('050_LeiDang_P2', 'BP_Monster_LeiDang_P2_C', 'ActorC_LeiDang_P2'),
    ('047_LeiDang', 'BP_Monster_LeiDang_C', 'ActorC_LeiDang'),
    ('035_HuaShan', 'BP_Monster_HuaShan_TwinSword_C', 'ActorC_HuaShan_TwinSword'),
    ('054_ZuoShang', 'BP_Monster_ZuoShang_C', 'ActorC_ZuoShang'),
    ('076_ZuoShang_P2', 'BP_Monster_ZuoShang_P2_C', 'ActorC_ZuoShang_P2'),
)
# Initial direct controls favor attacks with verified leaf lineage and explicit
# combat timelines. More intense sequences and phase transitions stay in the
# native configuration inventory until their inputs and context are tested.
SLOTS = {
    '050_LeiDang_P2': ('GA_LeiDang_P2_HeavyAttack_02_C', 'GA_LeiDang_P2_SpecialAttack_07_C',
                      'GA_LeiDang_P2_Skill_06_C', 'GA_LeiDang_P2_SpecialAttack_08_C'),
    '047_LeiDang': ('GA_LeiDang_LightAttack_01_C', 'GA_LeiDang_HeavyAttack_02_C',
                    'GA_LeiDang_SpecialAttack_02_C', 'GA_LeiDang_Dodge_B_C'),
    '035_HuaShan': ('GA_HuaShan_TwinSword_MiddleAttack_01_NoWave_C', 'GA_HuaShan_TwinSword_MiddleAttack_06_C',
                    'GA_HuaShan_TwinSword_SpecialAttack_02_NoWave_C', 'GA_HuaShan_TwinSword_Dodge_R_C'),
    '054_ZuoShang': ('GA_ZuoShang_HeavyAttack_02_C', 'GA_ZuoShang_SpecialAttack_02_C',
                    'GA_ZuoShang_Skill_02_C', 'GA_ZuoShang_Dash_B_C'),
    '076_ZuoShang_P2': ('GA_ZuoShang_P2_Attack_03_C', 'GA_ZuoShang_P2_Skill_03_C',
                      'GA_ZuoShang_P2_Skill_01_Hard_C', 'GA_ZuoShang_Dodge_R_01_C'),
}
SLOT_KEYS = ('F1', 'F2', 'F3', 'F4')


def asset_path(obj):
    return obj['Package'] + '.' + obj['Name']


def required_reference(capture, value, *expected_types):
    obj = capture.resolve(value)
    if obj['Type'] not in expected_types:
        raise ValueError(f'Expected {expected_types}, found {obj["Type"]}')
    return obj


def ability_pools(capture, root_pool):
    """Retain conditions and cross-folder references with their exact pool owner."""
    pools, issues = {}, []

    def visit(pool, stack):
        path = asset_path(pool)
        if path in stack or len(stack) >= 32:
            issues.append(dict(pool=path, reason='subpool_cycle_or_depth_limit'))
            return
        if path in pools:
            return
        props = pool.get('Properties', {})
        tactics = []
        for item in props.get('TacticActions', ()):
            asset = item.get('Ability') or {}
            path_name = asset.get('AssetPathName')
            if not path_name or path_name == 'None':
                issues.append(dict(pool=path, reason='tactic_without_serialized_class'))
                continue
            tactics.append(dict(class_path=path_name, comment=item.get('Comment'),
                weight=item.get('Weight'), tags=item.get('Tags', []), conditions=item.get('Conditions', [])))
        record = dict(path=path, tactics=tactics, ability_tags=props.get('AbilityTagsMap', []), subpools=[])
        pools[path] = record
        for ref in props.get('SubAbilityPools', ()):
            try:
                child = required_reference(capture, ref, 'SGameAIAbilityPool')
            except Unresolved as error:
                issues.append(dict(pool=path, reference=ref, reason=str(error)))
                continue
            record['subpools'].append(asset_path(child))
            visit(child, (*stack, path))

    visit(root_pool, ())
    return list(pools.values()), issues


def strategies(strategy, tree_for):
    trees, issues = {}, []

    def collect(value):
        if isinstance(value, dict):
            if value.get('ObjectName', '').startswith("BehaviorTree'"):
                try:
                    follow(split_reference(value), ())
                except Unresolved as error:
                    issues.append(dict(reference=value, reason=str(error)))
            else:
                for child in value.values():
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    def follow(ref, stack):
        if ref in stack or len(stack) >= 64:
            issues.append(dict(reference=list(ref), reason='strategy_tree_cycle_or_depth_limit'))
            return
        try:
            tree = tree_for(ref)
        except Unresolved as error:
            issues.append(dict(reference=list(ref), reason=str(error)))
            return
        path = tree['path']
        if path in trees:
            return
        trees[path] = tree
        for node in tree['nodes']:
            if 'subtree' in node:
                follow(tuple(node['subtree']), (*stack, ref))

    collect(strategy.get('Properties', {}))
    return list(trees.values()), issues


def candidate_slots(names, pools, trees, skill_rows, primary_folder):
    tactics = {row['class_path']: pool['path'] for pool in pools for row in pool['tactics']}
    tree_links = {node['ability']: tree['path'] for tree in trees for node in tree['nodes'] if 'ability' in node}
    # Related tag maps and phase folders do not supply bindings. Require a
    # concrete tactic or tree task linked to this exact combat configuration.
    known = (tactics.keys() | tree_links.keys()) & skill_rows.keys()
    slots, blocked = [], []
    for key, short in zip(SLOT_KEYS, names):
        matches = [path for path in sorted(known) if path.rsplit('.', 1)[-1] == short]
        if len(matches) != 1:
            blocked.append(dict(key=key, expected=short, reason='exact_tactic_missing_or_ambiguous'))
            continue
        path, = matches
        skill, evidence = skill_rows[path]
        if (evidence['native_metadata'] != 'verified' or evidence['native_kind'] != 'leaf'
                or not skill['timeline_available'] or not skill['declared_actions']):
            blocked.append(dict(key=key, expected=short, reason='leaf_or_timeline_evidence_missing'))
            continue
        slots.append(dict(key=key, class_path=path, declared_actions=skill['declared_actions'],
            declared_by=tactics.get(path) or tree_links[path],
            shared=not path.startswith(PREFIX + primary_folder + '/'), requires_native_grant=True,
            activated=False, binding_verified=False))
    return slots, blocked


def resolve_actor(db, capture, folder, short):
    if short is None:
        return None, None
    matches = db.execute('SELECT class_path, export_index FROM actor_variants WHERE folder=? ORDER BY class_path',
                         (folder,)).fetchall()
    matches = [(path, index) for path, index in matches if path.rsplit('.', 1)[-1] == short]
    if len(matches) != 1:
        raise ValueError(f'Expected one captured combat body for {folder}: {short}')
    (path, index), = matches
    mount, name = path.rsplit('.', 1)
    cls = capture.exact(mount, index, 'BlueprintGeneratedClass', name)
    return path, required_reference(capture, capture.defaults(cls).get('Actor Config'), 'PDA_ActorConfig_C')


def config_only(db, capture, folder, config_name):
    matches = db.execute('SELECT e.payload FROM combat_config_exports e JOIN combat_configs c ON c.package=e.package'
                         " WHERE c.folder=? AND e.name=? AND e.export_type='PDA_ActorConfig_C'",
                         (folder, config_name)).fetchall()
    if len(matches) != 1:
        raise ValueError(f'Expected one serialized Actor Config for {folder}')
    obj = json.loads(matches[0][0])
    package = capture.packages[obj['Package'].casefold()]
    exports = capture.exports(obj['Package'].casefold())
    if obj not in exports:
        raise ValueError(f'Database config differs from verified declaration: {package["package"]}')
    return obj


def query(identifier, role, path, configs=()):
    record = dict(id=identifier, role=role, package=path.rsplit('.', 1)[0], lookup_path=path,
                  config_candidates=list(configs), source='exact_serialized_class')
    return dict(record, key=hashlib.sha256(metadata.canonical(record)).hexdigest()[:20])


def profile(db, capture, item, skills, tree_for):
    folder, short, expected_config = item
    actor, config = resolve_actor(db, capture, folder, short)
    if config is None:
        config = config_only(db, capture, folder, expected_config)
    if config['Name'] != expected_config or not asset_path(config).startswith(PREFIX + folder + '/'):
        raise ValueError(f'Actor Config drift for {folder}')
    props = config.get('Properties', {})
    ai = required_reference(capture, props.get('AIConfig  Default'), 'PDA_PBZAIConfig_C')
    ai_props = ai.get('Properties', {})
    pool = required_reference(capture, ai_props.get('AbilityPool'), 'SGameAIAbilityPool')
    strategy = required_reference(capture, ai_props.get('StrategyConfig'),
        'BP_PBZAIStrategyConfig_C', 'BP_DefaultStrategyConfig_C')
    pools, issues = ability_pools(capture, pool)
    trees, tree_issues = strategies(strategy, tree_for)
    slots, slot_issues = candidate_slots(SLOTS.get(folder, ()), pools, trees, skills, folder)
    issues.extend(tree_issues)
    issues.extend(slot_issues)
    if actor is None:
        issues.append(dict(reason='combat_body_identity_unresolved'))
    jobs = []
    if actor:
        jobs.append(query(folder.casefold(), 'character', actor, (asset_path(config),)))
        jobs.extend(query(folder.casefold(), 'ability', slot['class_path']) for slot in slots)
    assets = [actor, asset_path(config), asset_path(ai), asset_path(strategy)]
    assets.extend(row['path'] for row in pools + trees)
    assets.extend(row['class_path'] for row in slots)
    asset_sources = {path.rsplit('.', 1)[0] for path in assets if path}
    sources = {path: capture.packages[path.casefold()]['declaration_sha256'] for path in sorted(asset_sources)}
    return dict(id=folder.casefold(), folder=folder, class_path=actor, config_path=asset_path(config),
        character_name_key=(props.get('Character Name') or {}).get('Key'), ai_config=asset_path(ai),
        root_pool=asset_path(pool), pools=pools, strategy=asset_path(strategy), strategy_trees=trees,
        direct_controls=slots, metadata_jobs=jobs,
        gaps=issues, declaration_digests=sources, runtime_identity_verified=False, playable=False)


def plan(root=ROOT, storage=PROJECT_STORAGE):
    catalog = Catalog(root, storage)
    with closing(connect_readonly(Path(storage) / DATABASE)) as db:
        check_identity(db, catalog)
        packages = [dict(package=package, declaration=path, declaration_sha256=digest)
                    for package, path, digest in db.execute('SELECT package,declaration,declaration_sha256 FROM packages')]
        capture = Capture(packages)
        skills = {path: (json.loads(raw), json.loads(evidence)) for path, raw, evidence in
                  db.execute('SELECT class_path,payload,adaptation FROM skills')}
        tree_for = lru_cache(maxsize=256)(lambda ref: ordered_nodes(capture, ref))
        profiles = [profile(db, capture, item, skills, tree_for) for item in ROLES]
    return dict(schema=1, build_sha256=BUILD, source_digests=catalog.source_digests,
        generator_sha256=sha(__file__), profiles=profiles, game_started=False,
        installed=False, runtime_acceptance_current=False, playable=False)


def build(root=ROOT, storage=PROJECT_STORAGE, *, verify_only=False):
    report = plan(root, storage)
    key = hashlib.sha256(metadata.canonical(report)).hexdigest()[:20]
    target = Path(storage) / OUTPUT / key / 'profiles.json'
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if not target.exists() and not verify_only:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(raw)
    if target.read_bytes() != raw:
        raise ValueError('Frozen complex Boss profile changed')
    return target, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    output, report = build(verify_only=args.verify)
    print(json.dumps(dict(path=str(output), profiles=[dict(folder=p['folder'], actor=p['class_path'],
        pools=len(p['pools']), trees=len(p['strategy_trees']), bindings=len(p['direct_controls']),
        gaps=len(p['gaps']))
        for p in report['profiles']], game_started=False), ensure_ascii=False, indent=2))
