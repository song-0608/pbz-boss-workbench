"""Trace original defense and attack-cue dependencies without granting abilities."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import boss_disk_declarations as disk
from boss_disk_dependencies import native_package
from boss_disk_skill_index import OBJECT_NAME, abilities as parse_abilities, references, resolve_local

CUE_ACTIONS = {'GAAction_WeaponParticle_BlueRedEye_C', 'GAAction_PowerAttackParticle_C'}
STANCE_BASE = '/PBZDeflectSystem/Abilities/BP_StanceAction_Base.BP_StanceAction_Base_C'
NPC_STANCE_BASE = '/PBZDeflectSystem/Abilities/BP_StanceAction_Base_NPC.BP_StanceAction_Base_NPC_C'


def native_contract_ready(classes):
    sentinel = next((c for c in classes if c['path'] ==
                     '/Script/GameplayAbilities.AbilitySystemComponent'), None)
    return bool(sentinel and any(p['name'] == 'ActivatableAbilities' for p in sentinel['properties'])
                and any(f['name'] == 'TryActivateAbilityByClass' for f in sentinel['functions']))


def class_reference(ref):
    if not isinstance(ref, dict):
        return None
    match = OBJECT_NAME.fullmatch(ref.get('ObjectName', ''))
    path = ref.get('ObjectPath', '')
    if not match or 'GeneratedClass' not in match[1] or '.' not in path:
        return None
    # Export ordinals are package-local. Resolve the name from the native ref,
    # never substitute an ordinal or derive a class from a filename.
    return path.rsplit('.', 1)[0]+'.'+match[2].rsplit('.', 1)[-1]


def parent_reference(obj):
    first, second = obj.get('Super'), obj.get('SuperStruct')
    if first and second and first != second:
        raise ValueError('Conflicting serialized class parent declarations')
    return class_reference(first or second)


def class_records(target):
    target = Path(target)
    inventory = disk.summarize(target)
    if inventory['failed'] or inventory['pending']:
        raise ValueError('Complete support declarations required')
    classes, mappings = {}, []
    for row in inventory['packages']:
        path = target/row['declaration']
        exports = json.loads(path.read_bytes())
        if disk.digest(path) != row['declaration_sha256']:
            raise ValueError('Support declaration changed during audit')
        source = dict(declaration=row['declaration'], sha256=row['declaration_sha256'])
        for obj in exports:
            if obj.get('Type') == 'InputMappingContext':
                props = obj.get('Properties', {})
                for mapping in props.get('DefaultKeyMappings', {}).get('Mappings', []):
                    action = mapping.get('Action', {}).get('ObjectPath', '')
                    if action.startswith('/PBZDeflectSystem/Input/'):
                        triggers = [resolve_local(r, obj['Package'], exports) for r in mapping.get('Triggers', [])]
                        mappings.append(dict(action=action, key=mapping.get('Key', {}).get('KeyName'),
                            triggers=[t['Type'] if t else None for t in triggers], source=source))
            if 'GeneratedClass' not in obj.get('Type', '') or not obj.get('Package'):
                continue
            identity = obj['Package']+'.'+obj['Name']
            cdo = resolve_local(obj.get('ClassDefaultObject'), obj['Package'], exports)
            if cdo is None or cdo.get('Name') != 'Default__'+obj['Name']:
                raise ValueError('Support class default object is unresolved')
            functions = {}
            for function in exports:
                outer = function.get('Outer', {})
                if function.get('Type') == 'Function' and class_reference(outer) == identity:
                    functions[function['Name']] = [p['Name'] for p in function.get('ChildProperties', [])]
            if identity in classes:
                raise ValueError('Duplicate support class identity')
            classes[identity] = dict(class_path=identity, parent=parent_reference(obj),
                cdo_overrides=cdo.get('Properties', {}), functions=functions, source=source)
    return inventory, classes, mappings


def lineage(path, classes):
    chain, seen = [], set()
    while path:
        if path in seen:
            raise ValueError('Serialized class inheritance cycle')
        seen.add(path)
        chain.append(path)
        record = classes.get(path)
        if record is None:
            return chain, path
        path = record.get('parent')
    return chain, None


def cue_actions(ability, abilities, seen=None):
    seen = set() if seen is None else seen
    path = ability['class_path']
    if path in seen:
        raise ValueError('Skill timeline inheritance cycle')
    seen.add(path)
    # An explicitly serialized empty array is still an override. Only absence
    # permits following a parent's timeline declaration.
    if 'AbilityTimelines' not in ability['serialized_class_properties']:
        parent = class_reference(ability.get('serialized_super'))
        if parent in abilities:
            yield from cue_actions(abilities[parent], abilities, seen)
        return
    for timeline in ability['timelines']:
        for action in timeline['actions']:
            props = action.get('serialized_action_properties') or {}
            refs = list(references(props))
            hints = [r for r in refs if 'AttackAlert' in r['ObjectPath']]
            # Soft references have AssetPathName rather than ObjectPath.
            soft = []
            def walk(value):
                if isinstance(value, dict):
                    if isinstance(value.get('AssetPathName'), str) and any(
                            token in value['AssetPathName'] for token in ('AttackAlert', '_Blue_', '_Red_', '_Bule_')):
                        soft.append(value['AssetPathName'])
                    for child in value.values():
                        walk(child)
                elif isinstance(value, list):
                    for child in value:
                        walk(child)
            walk(props)
            if action['action_type'] in CUE_ACTIONS or hints or soft:
                yield dict(timeline_owner=path, timeline=timeline['name'], ordinal=action['ordinal'],
                    type=action['action_type'], start_seconds=action['start_seconds'],
                    duration_seconds=action['duration_seconds'], track=action['track'],
                    activation_requirements=props.get('ActivationRequirements'),
                    action_overrides=props, explicit_cue_assets=soft+[r['ObjectPath'] for r in hints])


def audit(index, coverage, classes, mappings):
    if (index.get('kind') != 'offline_serialized_boss_skill_index' or index.get('indexing_issues') != 0
            or index.get('failed_packages') != 0 or index.get('pending_packages') != 0):
        raise ValueError('Complete issue-free skill index required')
    abilities, folders = {}, {}
    for package in index['packages']:
        for ability in package['abilities']:
            path = ability['class_path']
            if not path or path in abilities or ability['issues']:
                raise ValueError('Unique issue-free exact skill classes required')
            abilities[path] = ability
            folders[path] = package['folder']
    combined = dict(classes)
    for path, ability in abilities.items():
        combined[path] = dict(parent=class_reference(ability.get('serialized_super')))
    published = {r['class_path'] for r in coverage['rows'] if r['native_route'] == 'in_v5_profile'}
    if not published <= abilities.keys():
        raise ValueError('Published coverage does not match skill identities')
    rows = []
    for path, ability in abilities.items():
        cues = list(cue_actions(ability, abilities))
        chain, unresolved = lineage(path, combined)
        stance = STANCE_BASE in chain
        if not cues and not stance:
            continue
        rows.append(dict(class_path=path, folder=folders[path], in_published_v5=path in published,
            stance_ancestry_declared=stance, lineage=chain, unresolved_parent=unresolved,
            cue_actions=cues, cue_render_verified=False, defense_runtime_verified=False))
    action_defaults = {p: r for p, r in classes.items() if p.rsplit('.', 1)[-1] in CUE_ACTIONS}
    return dict(schema=1, kind='native_defense_and_cue_dependency_audit',
        skills_with_cue_or_stance=len(rows), published_skills=len(published),
        published_skills_with_declared_cues=sum(r['in_published_v5'] and bool(r['cue_actions']) for r in rows),
        declared_stance_classes=sum(r['stance_ancestry_declared'] for r in rows),
        by_folder=dict(sorted(Counter(r['folder'] for r in rows).items())),
        native_input_mappings=mappings, cue_class_defaults=action_defaults, rows=rows,
        serialized_overrides_only=True, blueprint_execution_flow_verified=False,
        activation_allowed=False, game_started=False, installed=False,
        defense_runtime_verified=False, cue_render_verified=False)


def weapon_declarations(support, inventory):
    weapons = []
    for row in inventory['packages']:
        if '/Weapon_' not in row['package']:
            continue
        path = Path(support)/row['declaration']
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row['declaration_sha256']:
            raise ValueError('Weapon declaration changed during audit')
        for obj in json.loads(data):
            if obj.get('Type') != 'PBZ_MainWeaponConfig_C':
                continue
            props = obj.get('Properties', {})
            declared = 'Equip Abilities' in props
            refs = props.get('Equip Abilities', [])
            if not isinstance(refs, list):
                raise ValueError('Serialized weapon ability list required')
            paths = [class_reference(ref) for ref in refs]
            if any(path is None for path in paths):
                raise ValueError('Exact weapon equipped ability class references required')
            weapons.append(dict(package=row['package'], name=obj['Name'], equip_abilities_declared=declared,
                equipped_class_paths=paths, source=dict(declaration=row['declaration'],
                    sha256=row['declaration_sha256']), live_grant_verified=False,
                defense_runtime_verified=False))
    return weapons


def build(index_path, coverage_path, support):
    index_path, coverage_path = Path(index_path), Path(coverage_path)
    index, coverage = json.loads(index_path.read_bytes()), json.loads(coverage_path.read_bytes())
    if coverage.get('disk_skill_index_sha256') != disk.digest(index_path):
        raise ValueError('Coverage belongs to another disk index')
    inventory, classes, mappings = class_records(support)
    result = audit(index, coverage, classes, mappings)
    result['sources'] = dict(skill_index_sha256=disk.digest(index_path),
        coverage_sha256=disk.digest(coverage_path), support_plan_sha256=inventory['plan_sha256'],
        audit_sha256=disk.digest(__file__))
    result['support_packages'] = inventory['extracted']
    # Weapon configs are DataAsset instances, not generated classes/CDOs.
    # Keep absent Equip Abilities distinct from an explicitly empty override.
    result['weapon_config_declarations'] = weapon_declarations(support, inventory)
    return result


def audit_terminal_scan(scan, coverage):
    """Recheck captured timeline owners before reading exact native cue actions."""
    indexed = {}
    quarantined = Counter()
    for package in scan['packages']:
        for ability in package['abilities']:
            path = ability['class_path']
            if not path or ability['issues']:
                quarantined[path, package['declaration_sha256']] += 1
                continue
            if path in indexed:
                raise ValueError('Duplicate serialized ability identity')
            indexed[path] = (package, ability)
    rows = {row['class_path']: row for row in coverage['rows']}
    queue_quarantined = Counter((row['class_path'], row['disk_declaration_sha256'])
                                for row in coverage['quarantined_rows'])
    if (len(rows) != len(coverage['rows']) or rows.keys() != indexed.keys()
            or quarantined != queue_quarantined
            or len(rows) + len(coverage['quarantined_rows']) != scan['ability_classes']):
        raise ValueError('Coverage does not match the terminal ability inventory')

    cues_by_owner = {}
    result = []
    unresolved = Counter()
    declared = Counter()
    for path, (package, ability) in indexed.items():
        row = rows[path]
        if (row['disk_declaration_sha256'] != package['declaration_sha256']
                or row['timeline_resolution'] != ability['timeline_resolution']
                or row['effective_timeline_class'] != ability['effective_timeline_class']):
            raise ValueError('Coverage and terminal declaration differ: ' + path)
        route = row['native_route']
        owner = ability['effective_timeline_class']
        if owner is None:
            unresolved[route] += 1
            continue
        if owner not in indexed:
            # An inherited timeline may belong to a class with a quarantined action.
            unresolved[route] += 1
            continue
        if owner not in cues_by_owner:
            source, origin = indexed[owner]
            if origin['timeline_override'] == 'explicit_empty':
                cues_by_owner[owner] = []
            else:
                declaration = Path(source['declaration']).read_bytes()
                if hashlib.sha256(declaration).hexdigest() != source['declaration_sha256']:
                    raise ValueError('Cue timeline declaration changed: ' + owner)
                matches = [item for item in parse_abilities(json.loads(declaration),
                           native_package(source['package']), include_native_types=True)
                           if item['class_path'] == owner and item['export_index'] == origin['export_index']]
                if len(matches) != 1 or matches[0]['issues'] or origin['timeline_override'] != 'declared':
                    raise ValueError('Exact native timeline owner required: ' + owner)
                cues_by_owner[owner] = list(cue_actions(matches[0], {}))
        cues = cues_by_owner[owner]
        if cues:
            declared[route] += 1
            result.append(dict(class_path=path, folder=package['folder'], native_route=route,
                               timeline_owner=owner, cue_actions=cues))
    return dict(schema=1, kind='terminal_native_cue_declaration_audit',
                analyzed_abilities=len(rows), quarantined_abilities=len(coverage['quarantined_rows']),
                abilities_with_cue_clues=len(result), cue_clues_by_native_route=dict(declared),
                unresolved_timeline_by_native_route=dict(unresolved),
                explicit_cue_action_abilities=sum(any(action['type'] in CUE_ACTIONS
                    for action in row['cue_actions']) for row in result),
                rows=result, capture_gaps=coverage['capture_gaps'], game_started=False,
                npc_stances=terminal_npc_stances(scan, rows),
                activation_allowed=False, cue_render_verified=False, defense_runtime_verified=False)


def terminal_npc_stances(scan, rows):
    classes = {item['class_path'].casefold(): item for package in scan['packages']
               for item in package.get('parent_classes', ())}
    result = []
    for path, row in rows.items():
        if not path.startswith('/PBZCombatAsset/ActorData/Mobs/'):
            continue
        current = classes.get(path.casefold())
        seen = set()
        while current and current['class_path'] not in seen:
            current_path = current['class_path']
            if current_path == NPC_STANCE_BASE:
                result.append(dict(class_path=path, folder=row['folder'], native_route=row['native_route'],
                                   historical_unique_grants=len(row['historical_unique_grants'])))
                break
            seen.add(current_path)
            ref = current['serialized_super']
            parent = class_reference(ref)
            match = classes.get(parent.casefold()) if parent else None
            if not match or not ref['ObjectPath'].endswith('.' + str(match['export_index'])):
                break
            if OBJECT_NAME.fullmatch(ref['ObjectName'])[1] != match['export_type']:
                break
            current = match
    return result


def build_terminal(scan_path, coverage_path):
    scan_bytes, coverage_bytes = Path(scan_path).read_bytes(), Path(coverage_path).read_bytes()
    scan, coverage = json.loads(scan_bytes), json.loads(coverage_bytes)
    scan_sha = hashlib.sha256(scan_bytes).hexdigest()
    if (scan.get('kind') != 'offline_native_dependency_scan'
            or scan.get('declaration_contents_verified') is not True
            or scan.get('pending_roots') != 0 or scan.get('pending_dependency_count') != 0
            or scan['root_packages'] != scan['extracted_roots']
            or coverage.get('kind') != 'dependency_disk_and_closed_native_skill_coverage'
            or coverage.get('disk_dependency_scan_sha256') != scan_sha
            or any(coverage.get(key) is not False for key in
                   ('game_started', 'activation_allowed', 'playable'))):
        raise ValueError('Matching verified terminal scan and adaptation queue required')
    result = audit_terminal_scan(scan, coverage)
    result['sources'] = dict(scan_sha256=scan_sha,
                             queue_sha256=hashlib.sha256(coverage_bytes).hexdigest(),
                             audit_sha256=disk.digest(__file__))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--index', type=Path)
    inputs.add_argument('--dependency-scan', type=Path)
    parser.add_argument('--support', type=Path)
    for name in ('coverage', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    if args.dependency_scan:
        result = build_terminal(args.dependency_scan, args.coverage)
    else:
        if not args.support:
            parser.error('--index requires --support')
        result = build(args.index, args.coverage, args.support)
    disk.write_new(args.output, result)
    print(json.dumps({k:v for k,v in result.items() if k not in (
        'rows', 'npc_stances', 'cue_class_defaults', 'native_input_mappings', 'sources',
        'weapon_config_declarations')}, ensure_ascii=False))
