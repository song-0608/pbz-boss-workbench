"""Offline Boss resource dossiers. Historical names never grant runtime authority."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/boss-adaptation'
BUILD = '4415933ce33476f14c837abb61a1b60af8b78cd81783896501913a7aac69e423'
ASSET = re.compile(r'/PBZCombatAsset/ActorData/Mobs/([A-Za-z0-9_]+)/[A-Za-z0-9_/]+(?:\.[A-Za-z0-9_]+)*')
SOURCE_NAMES = ('*character*metadata*.json', '*character*abilit*.json', '*boss*class*catalog*.json',
                '*boss*binding*.json', '*bride*candidates*.json', '*bride*candidate-catalog*.json',
                '*boss*asset*query*.json', 'boss-resource-names.json')
GATES = ('current_world_identity', 'actor_config_binding', 'boss_identity', 'granted_abilities',
         'ai_suspend_restore', 'camera_input_restore', 'natural_finish', 'active_cancel_restore',
         'damage_or_movement', 'owned_disposal_restore', 'stability_600s', 'native_menu_world_cycle',
         'performance_cache_and_timing')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(value):
    """An observed CDO/component path is evidence for its package, not a class path guess."""
    return value.split('.', 1)[0]


def role(package):
    leaf = package.rsplit('/', 1)[-1]
    if leaf.startswith(('BP_Monster_', 'BP_Boss_', 'BP_NPC_')):
        return 'character_blueprint_clue'
    if leaf.startswith(('ActorC_', 'ActorConfig_')):
        return 'actor_config_clue'
    if leaf.startswith('GA_'):
        return 'ability_dependency_clue' if '/Child/' in package or '/Grab/' in package or leaf.endswith('_Base') else 'ability_clue'
    return 'support_resource_clue'


def strings(value, pointer=''):
    if isinstance(value, str):
        yield pointer, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from strings(item, f'{pointer}/{index}')
    elif isinstance(value, dict):
        for key, item in value.items():
            escaped = str(key).replace('~', '~0').replace('/', '~1')
            yield from strings(item, f'{pointer}/{escaped}')


def discover_sources(root=ROOT):
    sources = set()
    for base in (root/'evidence/adaptation', root/'evidence/official-validation'):
        for pattern in SOURCE_NAMES:
            sources.update(base.rglob(pattern))
    return sorted(sources)


def collect(sources, root=ROOT):
    sources=list(sources)
    assets = {}
    manifest = []
    snapshot_available=False
    for path in sorted(set(map(Path, sources))):
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError(f'Historical JSON exceeds 16 MiB bound: {path}')
        source_id = path.resolve().relative_to(root.resolve()).as_posix()
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        digest = sha(path)
        manifest.append({'path': source_id, 'sha256': digest, 'bytes': path.stat().st_size})
        if path.name=='boss-resource-names.json':
            if data.get('target_build_sha256')!=BUILD or data.get('complete') is not True:
                raise ValueError('Incomplete or different-build name snapshot cannot advance the workflow')
            snapshot_available=True
        for pointer, value in strings(data):
            for match in ASSET.finditer(value):
                observed = match.group(0)
                package = canonical(observed)
                key = (match.group(1), package)
                item = assets.setdefault(key, {'package': package, 'role': role(package), 'observations': []})
                receipt = {'source': source_id, 'json_pointer': pointer, 'observed': observed}
                if receipt not in item['observations']:
                    item['observations'].append(receipt)
    groups = defaultdict(list)
    for (folder, _), asset in sorted(assets.items()):
        groups[folder].append(asset)
    candidates = []
    for folder, entries in sorted(groups.items()):
        counts = {kind: sum(e['role'] == kind for e in entries) for kind in sorted({e['role'] for e in entries})}
        stage = 'offline_identity_dossier' if counts.get('character_blueprint_clue') and counts.get('actor_config_clue') else 'resource_clues_only'
        candidates.append({'id': folder.casefold(), 'resource_folder': folder, 'stage': stage,
            'display_name': None, 'boss_identity_verified': False, 'playable': False,
            'reference_only': folder == '042_AHua', 'counts': counts, 'assets': entries})
    return {'schema_version': 1, 'at': datetime.now().astimezone().isoformat(),
        'target_build_sha256': BUILD, 'collection_mode': 'offline_historical_evidence',
        'current_runtime_verified': False, 'game_started': False,
        'sources': manifest, 'candidates': candidates,
        'bounded_name_snapshot_available': snapshot_available,
        'limits': ['Resource names are historical clues, not unlocked Bosses or current live objects.',
                   'No inferred Chinese names, guessed class paths, or inherited Ahua skill evidence.',
                   'Package plaintext scan previously yielded zero Ahua clues; this is not a package extraction.',
                   'A name snapshot is not a complete packaged asset inventory; unloaded names may be absent.']}


def dossier(candidate, catalog):
    resources = {kind: [a['package'] for a in candidate['assets'] if a['role'] == kind]
                 for kind in sorted(candidate['counts'])}
    return {'schema_version': 1, 'id': candidate['id'], 'resource_folder': candidate['resource_folder'],
        'enabled': False, 'playable': False, 'stage': candidate['stage'],
        'target_build_sha256': BUILD, 'source_manifest': catalog['sources'],
        'resources': resources, 'runtime_profile': None,
        'runtime_gates': {name: {'status': 'not_verified', 'evidence': []} for name in GATES},
        'next_step': 'Resolve exact class lineage, actor-config reference and granted abilities in one bounded read-only batch.',
        'acceptance_policy': {'offline_first': True, 'repeat_only_changed_or_failed': True,
            'session_seconds_max': 1200, 'assembly_seconds_max': 600,
            'native_object_cache_required': True, 'developer_profiler_default': False,
            'input_dispatch': 'tools/research_game_menu.py', 'unrelated_menus': False,
            'preserve_isolation_identity_los_and_restore_guards': True}}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw=json.dumps(data, ensure_ascii=False, indent=2)+'\n'
    if not path.exists() or path.read_text(encoding='utf-8')!=raw:
        path.write_text(raw, encoding='utf-8')


def prepare(catalog, out=OUT):
    write_json(out/'catalog.json', catalog)
    prepared = []
    for candidate in catalog['candidates']:
        if candidate['reference_only'] or candidate['resource_folder'] == 'Common':
            continue
        target = out/'dossiers'/f"{candidate['id']}.json"
        generated = dossier(candidate, catalog)
        if target.exists():
            # Refresh discovery inputs while retaining independently reviewed runtime work.
            existing = json.loads(target.read_text(encoding='utf-8'))
            for key in ('stage', 'source_manifest', 'resources'):
                existing[key] = generated[key]
            existing['enabled']=False
            existing['playable']=False
            write_json(target, existing)
        else:
            write_json(target, generated)
        prepared.append(str(target))
    return prepared


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, action='append')
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    catalog = collect(args.source or discover_sources())
    prepared = prepare(catalog, args.output)
    print(json.dumps({'catalog': str(args.output/'catalog.json'), 'sources': len(catalog['sources']),
        'candidates': [{k: c[k] for k in ('id', 'stage', 'counts')} for c in catalog['candidates']],
        'dossiers': prepared, 'game_started': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
