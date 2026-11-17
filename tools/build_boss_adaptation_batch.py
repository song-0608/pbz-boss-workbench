"""Freeze offline candidate work and generate one missing-only read-only batch plan."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

from boss_adaptation_workflow import ROOT, OUT, BUILD, GATES, sha, write_json

# First bounded adaptation queue: one character/config resource pair per folder.
# These are internal identifiers, not claims of verified Boss identity or translated names.
FIRST_QUEUE=('057_wanjun','073_yanqiansui','056_youlong')


def exact_class(asset):
    leaf = asset['package'].rsplit('/', 1)[-1]
    expected = asset['package']+'.'+leaf+'_C'
    return expected if any(row['observed'] == expected for row in asset['observations']) else None


def candidate_work(candidate):
    characters = [a for a in candidate['assets'] if a['role'] == 'character_blueprint_clue']
    configs = [a['package'] for a in candidate['assets'] if a['role'] == 'actor_config_clue']
    skills = [a for a in candidate['assets'] if a['role'] in ('ability_clue', 'ability_dependency_clue')]
    return {'id': candidate['id'], 'resource_folder': candidate['resource_folder'],
        'enabled': False, 'playable': False, 'boss_identity_verified': False,
        'target_build_sha256': BUILD,
        'class_candidates': [{'package':a['package'], 'observed_class_path':exact_class(a),
                              'lineage_verified':False, 'config_binding_verified':False} for a in characters],
        'config_candidates': configs, 'selected_class': None, 'selected_config': None,
        'skills': [{'id': hashlib.sha256(a['package'].encode()).hexdigest()[:16],
            'package': a['package'], 'observed_class_path':exact_class(a), 'role': a['role'],
            'player_key': None, 'granted_to_selected_actor':False,
            'natural_finish_verified':False, 'active_cancel_restore_verified':False,
            'gameplay_or_movement_verified':False, 'evidence':[]} for a in skills],
        'runtime_gates': {gate:'not_verified' for gate in GATES},
        'runtime_session_allowed': False,
        'blockers': ['Exact Boss identity, class/config binding and granted abilities need their own evidence.']}


def select_batch(work, identifiers=None):
    if identifiers is None:
        return [c['id'] for c in work if len(c['class_candidates'])==1 and len(c['config_candidates'])==1][:3]
    if not 1<=len(identifiers)<=3 or len(set(identifiers))!=len(identifiers):
        raise ValueError('Choose one to three distinct candidate identifiers')
    indexed={c['id']:c for c in work}
    for identifier in identifiers:
        if identifier not in indexed:
            raise ValueError('Unknown or reference-only candidate: '+identifier)
        candidate=indexed[identifier]
        if len(candidate['class_candidates'])!=1 or len(candidate['config_candidates'])!=1:
            raise ValueError('Ambiguous character/config pairs require their own variant evidence: '+identifier)
    return list(identifiers)


def freeze(catalog_path=OUT/'catalog.json', output=OUT/'batches', root=ROOT, identifiers=None):
    catalog=json.loads(catalog_path.read_text(encoding='utf-8'))
    if catalog.get('target_build_sha256') != BUILD:
        raise ValueError('Fixed registered game build required')
    for source in catalog['sources']:
        target=(root/source['path']).resolve()
        target.relative_to((root/'evidence').resolve())
        if sha(target) != source['sha256']:
            raise ValueError(f"Source changed since catalog collection: {source['path']}")
    code_paths=('tools/boss_adaptation_workflow.py','tools/collect_boss_resource_names.py',
                'tools/build_boss_adaptation_batch.py','tools/build_boss_identity_probe.py',
                'tools/run_boss_offline_milestone.py',
                'tests/test_boss_adaptation_workflow.py','tests/test_boss_adaptation_batch.py',
                'tests/test_boss_identity_probe.lua')
    sources={name:sha(root/name) for name in code_paths}
    semantic_catalog={k:v for k,v in catalog.items() if k!='at'}
    content_sha=hashlib.sha256(json.dumps(semantic_catalog,sort_keys=True).encode()).hexdigest()
    selected=[c for c in catalog['candidates'] if not c['reference_only'] and c['resource_folder']!='Common']
    work=[candidate_work(c) for c in selected]
    # Review priority affects only work order; it is never a playability claim.
    work.sort(key=lambda c:(FIRST_QUEUE.index(c['id']) if c['id'] in FIRST_QUEUE else len(FIRST_QUEUE),
                           -bool(c['class_candidates']),-bool(c['config_candidates']),-len(c['skills']),c['id']))
    snapshot_available=catalog.get('bounded_name_snapshot_available',False)
    batch_ids=select_batch(work,identifiers)
    fingerprint=hashlib.sha256(json.dumps({'catalog':content_sha,'tools':sources,'batch_ids':batch_ids},sort_keys=True).encode()).hexdigest()[:16]
    target=output/f'offline-{fingerprint}'
    if target.exists():
        return target
    for candidate in work:
        write_json(target/'candidates'/f"{candidate['id']}.json",candidate)
    write_json(target/'catalog.json',catalog)
    manifest={'schema_version':1,'at':datetime.now().astimezone().isoformat(),
        'fingerprint':fingerprint,'target_build_sha256':BUILD,'catalog_sha256':sha(target/'catalog.json'),
        'catalog_content_sha256':content_sha,
        'source_files':sources,'historical_evidence':catalog['sources'],
        'candidate_order':[c['id'] for c in work], 'candidate_count':len(work),
        'offline_only':True,'game_started':False,'playable_bosses_added':0,
        'next_batch':{'kind':'read_only_identity_binding' if snapshot_available else 'read_only_resource_discovery',
                      'candidate_ids':batch_ids,
                      'gameplay_input_allowed':False,'ability_activation_allowed':False,
                      'collect_once_then_continue_offline':True,'max_seconds':90,
                      'repeat_name_scan':False if snapshot_available else None},
        'candidate_files':{p.relative_to(target).as_posix():sha(p) for p in sorted((target/'candidates').glob('*.json'))}}
    write_json(target/'manifest.json',manifest)
    write_json(output/'latest.json',{'directory':str(target),'fingerprint':fingerprint})
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog',type=Path,default=OUT/'catalog.json')
    parser.add_argument('--candidate',action='append',help='Explicit next-wave identifier; at most three unambiguous pairs')
    args=parser.parse_args()
    print(json.dumps({'batch':str(freeze(args.catalog,identifiers=args.candidate)),'game_started':False},ensure_ascii=False))
