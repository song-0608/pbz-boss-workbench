"""严格核对单次装配满600秒、持续状态回读与最终完整恢复。"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from control_action_evidence import restoration_result

ROOT = Path(__file__).resolve().parents[1]


def proof(text, session, display_name='新娘阿花'):
    rows = text.splitlines()
    ready = [i for i, line in enumerate(rows) if 'PBZ_CONTROL_LIFECYCLE:INTERACTIVE_READY=' in line]
    ended = [i for i, line in enumerate(rows) if 'PBZ_CONTROL_LIFECYCLE:INTERACTIVE_END=' in line]
    if len(ready) != 1 or len(ended) != 1 or ended[0] <= ready[0]:
        return {'passed': False, 'reason': 'one complete assembly interval required'}
    def timestamp(line):
        match = re.match(r'\[([^]]+)\]', line)
        return datetime.fromisoformat(match[1])
    elapsed = (timestamp(rows[ended[0]]) - timestamp(rows[ready[0]])).total_seconds()
    interval = '\n'.join(rows[ready[0]:ended[0]+1])
    statuses = []
    malformed = False
    for line in rows[ready[0]:ended[0]+1]:
        if 'PBZ_PLAYER_UI:STATUS=' not in line:
            continue
        try:
            row = json.loads(line.split('PBZ_PLAYER_UI:STATUS=', 1)[1])
            assert row['session'] == 'official-validation-' + session
            assert type(row['at']) is int and type(row['expires_at']) is int and row['at'] < row['expires_at']
            assert isinstance(row['player'], str) and row['player'] and isinstance(row['text'], str)
            statuses.append(row)
        except (ValueError, KeyError, TypeError, AssertionError):
            malformed = True
    times = [row['at'] for row in statuses]
    active_prefix=display_name+' | ACTIVE\n'
    active = [row['at'] for row in statuses if row['text'].startswith(active_prefix)]
    active_start = None
    longest_active = 0
    for row in statuses:
        if row['text'].startswith(active_prefix):
            if active_start is None:
                active_start = row['at']
            longest_active = max(longest_active, row['at'] - active_start)
        else:
            active_start = None
    enter = interval.rfind('[PBZBossControl] enter success=true state=ACTIVE')
    restoration = restoration_result(interval[enter:] if enter >= 0 else '')
    result = {
        'elapsed_seconds': elapsed,
        'declared_600_seconds': 'cleanup in 600 seconds' in rows[ready[0]],
        'heartbeat_count': len(statuses),
        'heartbeat_span_seconds': times[-1] - times[0] if times else 0,
        'maximum_heartbeat_gap': max((b-a for a, b in zip(times, times[1:])), default=999),
        'heartbeat_ordered': bool(times) and all(b >= a for a, b in zip(times, times[1:])),
        'active_span_seconds': active[-1] - active[0] if active else 0,
        'longest_continuous_active_seconds': longest_active,
        'statuses_valid': not malformed,
        'restoration': restoration,
        'fault_absent': not any(token in interval for token in (
            'state=FAULTED', 'PBZ_CONTROL_LIFECYCLE:ISSUE_', 'PBZ_CONTROL_RESTORE:FAILED=',
            'HUD_UNAVAILABLE=', '[Lua::execute_file]', 'idle_world_check success=false')),
    }
    result['passed'] = bool(
        elapsed >= 600 and result['declared_600_seconds'] and len(statuses) >= 580
        and result['heartbeat_span_seconds'] >= 598 and result['maximum_heartbeat_gap'] <= 5
        and result['heartbeat_ordered'] and result['longest_continuous_active_seconds'] >= 300
        and result['statuses_valid'] and result['fault_absent'] and restoration['passed'])
    return result


def collect(session):
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    state = json.loads((ROOT/'runtime'/('official-validation-'+session)/'state.json').read_text(encoding='utf-8'))
    work = Path(state['work'])
    assert state.get('restored') and work.name == session
    post = json.loads((work/'postcheck.json').read_text(encoding='utf-8'))
    assert post['validation_state'] == state['state_file'] and not post['formal_files_changed']
    assert not post['host_config_files_changed'] and post['host_registry_unchanged']
    assert post['research_box_empty'] and post['research_loader_removed']
    deployments = list(work.glob('control-lifecycle-deployment-*.json'))
    assert len(deployments) == 1
    deployment = json.loads(deployments[0].read_text(encoding='utf-8'))
    assert deployment['player_entry']
    raw = (work/'UE4SS.log').read_bytes()
    result = proof(raw.decode('utf-8', errors='replace'), session)
    result.update(session=session, log_sha256=hashlib.sha256(raw).hexdigest(),
                  module_source_sha256=deployment['module_source_sha256'], complete_mod=False)
    target = work/'practice-stability-evidence.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'report': str(target), 'passed': result['passed'],
                      'elapsed_seconds': result.get('elapsed_seconds')}, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('session')
    raise SystemExit(collect(parser.parse_args().session))
