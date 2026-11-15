"""从关闭会话的原始区间重验F11玩家连招；不修改原始动作记录或开放标志。"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from control_action_evidence import restoration_result

ROOT = Path(__file__).resolve().parents[1]


def collect(session):
    if not re.fullmatch(r'\d{8}-\d{6}', session):
        raise ValueError('Exact session directory required')
    state = json.loads((ROOT / 'runtime' / ('official-validation-' + session) / 'state.json').read_text(encoding='utf-8'))
    work = Path(state['work'])
    if not state.get('restored') or work.name != session:
        raise RuntimeError('Matching closed research session required')
    post = json.loads((work / 'postcheck.json').read_text(encoding='utf-8'))
    if (post['validation_state'] != state['state_file'] or post['formal_files_changed']
            or post['host_config_files_changed'] or not post['research_box_empty']
            or not post['research_loader_removed'] or not post['host_registry_unchanged']):
        raise RuntimeError('Verified clean teardown required')
    log_path = work / 'UE4SS.log'
    raw = log_path.read_bytes()
    text = log_path.read_text(encoding='utf-8', errors='replace')
    actions = json.loads((work / 'native-combo-player-actions.json').read_text(encoding='utf-8'))
    deployments = [json.loads(p.read_text(encoding='utf-8'))
                   for p in work.glob('control-lifecycle-deployment-*.json')]
    rows = []
    for action in actions:
        if action['state_file'] != state['state_file'] or action['actual_binding'] not in ('native_combo|attack_01|F11','native_combo|attack_01|R'):
            raise RuntimeError('Current session and exact F11 action required')
        start, end = action['log_offset'], action['log_end']
        if not 0 <= start < end <= len(text):
            raise RuntimeError('Original action interval outside final log')
        delta = text[start:end]
        stamp = re.search(r'\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)', delta)
        if not stamp:
            raise RuntimeError('Timestamped original interval required')
        began = datetime.fromisoformat(stamp[1]).replace(tzinfo=datetime.fromisoformat(action['at']).tzinfo)
        candidates = [d for d in deployments if datetime.fromisoformat(d['at']) <= began]
        if not candidates:
            raise RuntimeError('Deployed source snapshot missing')
        deployment = max(candidates, key=lambda d: datetime.fromisoformat(d['at']))
        if not (deployment.get('player_entry') or deployment.get('player_key_trial')):
            raise RuntimeError('Player entry or explicit key trial deployment required')
        ended = re.search(r'KEY_SKILL_END=attack_01\|peak=(\d+)\|active=(\d+)\|natural=(true|false)\|health_before=([\d.-]+)\|health_after=([\d.-]+)', delta)
        natural = bool(ended and int(ended[1]) > 0 and int(ended[2]) == 0 and ended[3] == 'true'
            and 'COMBO_SCHEDULER_END=natural=true|all_grants_at_baseline=true|brain_tick=false' in delta)
        cancelled = bool(re.search(r'KEY_SKILL_BEGIN=attack_01\|[^\r\n]*\|active=[1-9]\d*', delta)
            and 'COMBO_SCHEDULER_END=cancelled=true|all_grants_at_baseline=true|brain_tick=false' in delta
            and restoration_result(delta)['passed'])
        if natural != action['natural_completion'] or cancelled != action['active_combo_cancelled']:
            raise RuntimeError('Action result does not match original log interval')
        rows.append({'action': action['action'], 'actual_binding': action['actual_binding'], 'log_offset': start, 'log_end': end,
            'natural_completion': natural, 'damage_observed': bool(natural and float(ended[4]) > float(ended[5])),
            'active_combo_cancelled': cancelled, 'restoration': restoration_result(delta),
            'player_entry': deployment.get('player_entry', False), 'deployment_at': deployment['at'],
            'module_source_sha256': deployment['module_source_sha256']})
    result = {'at': datetime.now().astimezone().isoformat(), 'session': session,
        'source_log_sha256': hashlib.sha256(raw).hexdigest(), 'actions': rows,
        'default_player_natural_damage_verified': any(r['player_entry'] and r['natural_completion'] and r['damage_observed'] for r in rows),
        'default_player_active_cancel_verified': any(r['player_entry'] and r['active_combo_cancelled'] for r in rows),
        'formal_files_changed': [], 'research_box_empty': True, 'complete_mod': False}
    target = work / 'native-combo-player-evidence.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'actions'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('session')
    collect(parser.parse_args().session)
