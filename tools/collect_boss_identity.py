"""Validate closed-session metadata receipts; identity never grants playable status."""
import argparse
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, OUT, BUILD, sha, write_json


def analyze(lines, requests):
    events = {}
    for line in lines:
        match = re.search(r'PBZ_MULTI_ID:([A-Z_]+)=(.*)', line)
        if match:
            event, payload = match.groups()
            events.setdefault(event, []).append(payload.strip())
    assert len(events.get('START', [])) == len(events.get('END', [])) == 1, 'Complete single batch required'
    results = []
    for identifier in sorted({r['id'] for r in requests}):
        pair = {r['role']: r for r in requests if r['id'] == identifier}
        assert set(pair) == {'character', 'config'}, 'Exact character/config pair required'
        character, config = pair['character']['lookup_path'], pair['config']['lookup_path']
        def values(event):
            return [p.split('|', 1)[1] for p in events.get(event, []) if p.startswith(identifier+'|')]
        assets = values('ASSET')
        lineage = values('LINEAGE')
        defaults = values('CDO_CONFIG')
        names = values('NAME')
        rejected = values('REJECTED')
        checks = {
            'exact_class': assets.count('character|BlueprintGeneratedClass '+character) == 1,
            'npc_lineage': any(p.endswith('Class /Script/ProjectPBZ.PBZCharacter_NPC') for p in lineage),
            'complete_lineage': any(p.endswith('Class /Script/CoreUObject.Object') for p in lineage),
            'exact_config': len([p for p in assets if p.startswith('config|') and p.split(' ', 1)[-1] == config]) == 1,
            'cdo_config_binding': len(defaults) == 1 and defaults[0].split(' ', 1)[-1] == config,
            'declared_config_match': events.get('DEFAULT_CONFIG_MATCH', []).count(identifier) == 1,
            'display_name': len(names) == 1 and bool(names[0]),
            'no_rejection': not rejected,
        }
        results.append({'id': identifier, 'class_path': character, 'config_path': config,
            'observed_cdo_config': defaults, 'display_name': names[0] if len(names) == 1 else None,
            'checks': checks, 'identity_verified': all(checks.values()), 'rejections': rejected,
            'playable': False, 'control_verified': False})
    return results


def collect(session, batch):
    batch = Path(batch).resolve()
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    state_path = ROOT/'runtime'/('official-validation-'+session)/'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    work = Path(state['work'])
    assert state.get('restored') and work.resolve() == (ROOT/'evidence/official-validation'/session).resolve()
    post_path = work/'postcheck.json'
    post = json.loads(post_path.read_text(encoding='utf-8'))
    assert post['validation_state'] == str(state_path)
    assert not post['formal_files_changed'] and not post['host_config_files_changed']
    assert post['host_registry_unchanged'] and post['research_box_empty'] and post['research_loader_removed']
    manifest_path = batch/'identity-probe-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert manifest['target_build_sha256'] == BUILD
    assert sha(batch/'manifest.json') == manifest['batch_manifest_sha256']
    assert sha(batch/'identity-probe.lua') == manifest['script_sha256']
    receipt_path = work/'multi-boss-identity-results.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    assert receipt['state_file'] == str(state_path) and receipt['metadata_only'] is True
    assert receipt['script_sha256'] == manifest['script_sha256']
    assert receipt['batch_manifest_sha256'] == manifest['batch_manifest_sha256']
    raw_path = work/'UE4SS.log'
    raw = raw_path.read_text(encoding='utf-8', errors='replace')
    cursor = 0
    for line in receipt['lines']:
        cursor = raw.index(line, cursor)+len(line)
    candidates = analyze(receipt['lines'], manifest['requests'])
    source_paths = [state_path, post_path, raw_path, receipt_path, manifest_path,
                    batch/'manifest.json', batch/'identity-probe.lua']
    result = {'schema_version': 1, 'session': session, 'target_build_sha256': BUILD,
        'metadata_only': True, 'playable': False, 'candidates': candidates,
        'sources': {str(p.relative_to(ROOT)): sha(p) for p in source_paths}}
    output = OUT/'identity-receipts'/f'{session}.json'
    write_json(output, result)
    for candidate in candidates:
        path = OUT/'dossiers'/(candidate['id']+'.json')
        dossier = json.loads(path.read_text(encoding='utf-8'))
        dossier['metadata_identity'] = {**candidate, 'receipt': str(output.relative_to(ROOT)), 'receipt_sha256': sha(output)}
        dossier['enabled'] = dossier['playable'] = False
        write_json(path, dossier)
    print(json.dumps({'receipt': str(output), 'identities_verified': [c['id'] for c in candidates if c['identity_verified']],
                      'blocked': [c['id'] for c in candidates if not c['identity_verified']], 'playable': False}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', required=True)
    parser.add_argument('--batch', type=Path, required=True)
    args = parser.parse_args()
    collect(args.session, args.batch)
