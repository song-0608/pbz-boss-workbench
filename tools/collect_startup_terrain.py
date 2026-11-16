"""Collect closed, unarmed navigation observations without claiming control acceptance."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from mod_installation import ROOT, MANIFEST, digest, validate_package, unlinked_path


def xyz(value):
    parts = value.split(',')
    assert len(parts) == 3
    result = [float(v) for v in parts]
    assert all(math.isfinite(v) for v in result), 'Finite trace coordinates required'
    return result


def observation(raw, token, offset):
    assert token.isdigit() and isinstance(offset, int) and 0 <= offset < len(raw)
    tail = raw[offset:]
    markers = list(re.finditer(r'PBZ_STARTUP_TERRAIN:TOKEN=' + token +
        r'\|accepted=(true|false)\|position_unchanged=(true|false)\|reason=([^\r\n]*)', tail))
    assert len(markers) == 1, 'One exact completed observation required'
    marker = markers[0]
    assert marker[2] == 'true', 'Unchanged restored player required'
    segment = tail[:marker.start()]
    traces = list(re.finditer(r'PBZ_TERRAIN_TRACE:BEGIN=origin:([^|\r\n]+)\|forward:([^\r\n]+)'
        r'([\s\S]*?)PBZ_TERRAIN_TRACE:END=queries:(\d+)\|accepted:(true|false)', segment))
    assert len(traces) == 1, 'One complete bounded terrain trace required'
    trace = traces[0]
    rows = re.findall(r'PBZ_TERRAIN_TRACE:QUERY=(\d+)\|wanted=([^|\r\n]+)\|actual=([^\r\n]+)', trace[3])
    assert 0 < len(rows) == int(trace[4]) <= 192
    assert [int(r[0]) for r in rows] == list(range(1, len(rows) + 1))
    assert trace[5] == marker[1], 'Trace and result disagree'
    assert not any(v in tail[:marker.end()] for v in
        ('SPAWN_ATTEMPT=', 'KEY_SKILL_BEGIN=', 'enter success=true', 'PLAYER_ENTRY_READY=', 'WORKBENCH_BOSS_SELECTED='))
    unavailable, drifts, height_deltas = 0, [], []
    for _, wanted, actual in rows:
        desired = xyz(wanted)
        if actual == 'unavailable':
            unavailable += 1
        else:
            point = xyz(actual)
            drifts.append(math.hypot(point[0] - desired[0], point[1] - desired[1]))
            height_deltas.append(abs(point[2] - desired[2]))
    return {'token': token, 'origin': xyz(trace[1]), 'forward': xyz(trace[2]),
            'queries': len(rows), 'unavailable_projections': unavailable,
            'projections_over_35cm_horizontal_drift': sum(v > 35 for v in drifts),
            'projections_over_100cm_requested_height_difference': sum(v > 100 for v in height_deltas),
            'terrain_preflight_result': marker[1] == 'true', 'player_identity_position_unchanged': True,
            'log_offset': offset, 'result_log_end': offset + marker.end(),
            'later_errors': re.findall(r'PBZ_STARTUP_TERRAIN:ERROR=' + token + r'\|([^\r\n]*)', tail[marker.end():]),
            'geometric_replay_claimed': False, 'ordinary_integration_accepted': False}


def probe_source(sha):
    path = ROOT / 'tools/terrain_startup_preflight.py'
    if digest(path) == sha:return 'working-tree'
    commits = subprocess.check_output(['git', 'rev-list', '-n', '30', 'HEAD', '--',
                                      'tools/terrain_startup_preflight.py'], cwd=ROOT).decode().splitlines()
    for commit in commits:
        result = subprocess.run(['git', 'show', commit + ':tools/terrain_startup_preflight.py'],
                                cwd=ROOT, capture_output=True)
        if result.returncode == 0 and hashlib.sha256(result.stdout).hexdigest() == sha:return commit
    raise AssertionError('Exact historical probe source unavailable')


def collect(session):
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    state_path = ROOT / 'runtime' / ('official-validation-' + session) / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    work = ROOT / 'evidence/official-validation' / session
    assert state['restored'] and Path(state['work']).resolve() == work.resolve()
    assert state['offline_validation'] and not state.get('boss_lifecycle_experiment')
    post_path = work / 'postcheck.json';post = json.loads(post_path.read_text(encoding='utf-8'))
    assert post['validation_state'] == str(state_path)
    assert all(post[k] for k in ('research_box_empty', 'research_loader_removed', 'host_registry_unchanged'))
    assert not any(post[k] for k in ('formal_files_changed', 'host_config_files_changed', 'remaining_games'))
    raw_path = work / 'UE4SS.log';raw = raw_path.read_text(encoding='utf-8', errors='replace')
    assert not any(k in raw for k in ('SPAWN_ATTEMPT=', 'KEY_SKILL_BEGIN=', 'PLAYER_ENTRY_READY='))
    receipts = sorted(work.glob('startup-terrain-*.json'));assert receipts
    paths = [state_path, post_path, raw_path, Path(__file__)]
    results = []
    for receipt in receipts:
        data = json.loads(receipt.read_text(encoding='utf-8'))
        assert data['state_file'] == str(state_path)
        assert all(data[k] is False for k in ('input_sent', 'assembly_started', 'acceptance_claimed'))
        candidate = unlinked_path(ROOT / 'runtime/release-candidates' / data['candidate'])
        assert candidate.parent == (ROOT / 'runtime/release-candidates').resolve()
        manifest = validate_package(candidate)
        assert manifest['release_id'] == candidate.name and digest(candidate / MANIFEST) == data['candidate_manifest_sha256']
        result = observation(raw, data['token'], data['log_offset'])
        result.update(candidate=candidate.name, probe_source_sha256=data['probe_source_sha256'],
                      exact_probe_source=probe_source(data['probe_source_sha256']))
        payload = work / ('startup-preflight-' + data['token'] + '.lua')
        result['payload_archived_and_digest_verified'] = payload.exists()
        if payload.exists():
            assert digest(payload) == data['payload_sha256']
            paths.append(payload)
        paths.extend([receipt, candidate / MANIFEST]);results.append(result)
    return {'schema': 1, 'session': session, 'observations_verified': True,
            'unarmed_no_spawn_no_takeover': True, 'formal_postcheck_passed': True,
            'ordinary_integration_accepted': False, 'terrain_observations': results,
            'sources': {p.relative_to(ROOT).as_posix(): digest(p) for p in paths}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser();parser.add_argument('session');parser.add_argument('--verify', action='store_true')
    args = parser.parse_args();report = collect(args.session)
    output = ROOT / 'research/boss-adaptation/developer-attempt-receipts' / ('startup-terrain-' + args.session + '.json')
    if args.verify:
        assert json.loads(output.read_text(encoding='utf-8')) == report
    else:
        assert not output.exists(), 'Preserve historical observations'
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'observations_verified': True, 'observations': len(report['terrain_observations']),
                      'ordinary_integration_accepted': False, 'receipt': str(output)}, ensure_ascii=False))
