"""Collect exact closed metadata outcomes without promoting any playable entry."""
import argparse
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, OUT, BUILD, sha, write_json
from build_boss_followup_batch import verify


def analyze(lines, manifest):
    fingerprint = manifest['batch_fingerprint']
    events = {}
    for line in lines:
        match = re.search(r'PBZ_BOSS_META:([A-Z_]+)=(.*)', line)
        if match:
            events.setdefault(match[1], []).append(match[2].strip())
    assert events.get('START') == events.get('END') == [fingerprint], 'One complete frozen metadata batch required'
    assert not events.get('STOP'), 'Expired batch cannot pass'
    expected = {(row['id'], row['lookup_path']) for row in manifest['ability_requests']}
    observed, failures = {}, {}
    for value in events.get('ABILITY', []):
        identifier, path, kind = value.split('|')
        key = identifier, path
        assert key in expected and key not in observed and key not in failures, 'Unknown or duplicate metadata outcome'
        assert kind in ('leaf', 'subtree')
        observed[key] = kind
    for value in events.get('REJECTED', []):
        identifier, role, path, reason = value.split('|', 3)
        key = identifier, path
        assert role == 'ability' and key in expected and key not in observed and key not in failures
        failures[key] = reason
    assert expected == observed.keys() | failures.keys(), 'Every requested class needs one outcome'
    return [{'id': row['id'], 'class_path': row['lookup_path'],
        'metadata_verified': (row['id'], row['lookup_path']) in observed,
        'ability_kind': observed.get((row['id'], row['lookup_path'])),
        'rejection': failures.get((row['id'], row['lookup_path'])),
        'live_grant_verified': False, 'activation_verified': False, 'playable': False}
        for row in manifest['ability_requests']]


def collect(session, batch):
    _, probe = verify(batch)
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    state_path = ROOT / 'runtime' / ('official-validation-' + session) / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    work = ROOT / 'evidence/official-validation' / session
    assert state['restored'] and Path(state['work']).resolve() == work.resolve()
    post_path = work / 'postcheck.json'
    post = json.loads(post_path.read_text(encoding='utf-8'))
    assert post['validation_state'] == str(state_path)
    assert post['research_box_empty'] and post['research_loader_removed'] and post['host_registry_unchanged']
    assert not post['formal_files_changed'] and not post['host_config_files_changed']
    action_path = work / 'multi-boss-identity-results.json'
    action = json.loads(action_path.read_text(encoding='utf-8'))
    assert action['state_file'] == str(state_path) and action['metadata_only']
    assert action['script_sha256'] == probe['script_sha256']
    assert action['batch_manifest_sha256'] == probe['batch_manifest_sha256']
    raw_path = work / 'UE4SS.log'
    raw = raw_path.read_text(encoding='utf-8', errors='replace')
    cursor = 0
    for line in action['lines']:
        cursor = raw.index(line, cursor) + len(line)
    abilities = analyze(action['lines'], probe)
    from collect_boss_identity import collect as collect_identity
    identity = collect_identity(session, batch)
    result = {'schema_version': 1, 'session': session, 'target_build_sha256': BUILD,
        'batch_fingerprint': probe['batch_fingerprint'], 'metadata_only': True, 'playable': False,
        'identity_candidates': identity['candidates'], 'ability_metadata': abilities,
        'live_grants_verified': False, 'activation_verified': False,
        'sources': {path.relative_to(ROOT).as_posix(): sha(path) for path in (
            state_path, post_path, action_path, raw_path, batch / 'manifest.json',
            batch / 'identity-probe-manifest.json', batch / 'identity-probe.lua')},
        'next_step': 'Bind only independently observed unique live grants in a protected developer candidate; metadata does not unlock players.'}
    target = OUT / 'ability-metadata-receipts' / (session + '.json')
    write_json(target, result)
    summary = {'receipt': target.relative_to(ROOT).as_posix(),
        'sha256': sha(target), 'leaf_count': sum(row['ability_kind'] == 'leaf' for row in abilities),
        'subtree_count': sum(row['ability_kind'] == 'subtree' for row in abilities),
        'rejected_count': sum(not row['metadata_verified'] for row in abilities),
        'live_grants_verified': False, 'playable': False}
    print(json.dumps({'report': str(target), 'verified_identities': [row['id'] for row in identity['candidates']
        if row['identity_verified']], 'ability_metadata': summary, 'playable_bosses_added': 0}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session')
    parser.add_argument('batch', type=Path)
    args = parser.parse_args()
    collect(args.session, args.batch)
