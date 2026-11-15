"""核对原菜单引起的自动重装配；不将手动重新arm或旧版日志计作成功。"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from control_action_evidence import control_identity, restoration_result

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def witness():
    import ahua_practice as practice
    from pbz_readonly import GameRead
    owner, state = practice.owned_session()
    assert owner['phase'] == 'armed' and (owner.get('player_entry') or owner.get('scene_transition_trial'))
    with GameRead() as game:
        text = practice.log_path(state).read_text(encoding='utf-8', errors='replace')
        before_pid = read(Path(state['work']) / 'combat-native-contract.json')['pid']
        result = {'at': datetime.now().astimezone().isoformat(), 'state_file': state['state_file'],
                  'pre_pid': before_pid, 'post_pid': game.pid, 'log_end': len(text),
                  'log_prefix_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}
    target = Path(state['work']) / 'auto-world-witness.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


def proof(text):
    ready = list(re.finditer(r'PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=', text))
    if len(ready) != 2:
        return {'passed': False, 'reason': 'exactly two automatic player assemblies required'}
    first, second = text[ready[0].start():ready[1].start()], text[ready[1].start():]
    previous, current = control_identity(first), control_identity(second)
    old_restore, new_restore = restoration_result(first), restoration_result(second)
    retired = first.find('IDLE_WORLD_OBJECTS_RETIRED=')
    wait = first.find('WORLD_REASSEMBLY_WAIT=', retired)
    resumed = first.find('WORLD_REASSEMBLY_AWAITING_GAMEPLAY=', wait)
    spawned = first.find('SPAWN_ATTEMPT=', resumed)
    labels = set(re.findall(r'OWNED_DESTROY_VERIFIED=([^|\r\n]+)\|engine_unusable=true', first[retired:spawned]))
    expected = {'boss', 'boss_controller', 'target', 'target_controller', 'extra_target', 'extra_target_controller'}
    natural = re.search(r'KEY_SKILL_END=skill_01\|peak=[1-9]\d*\|active=0\|natural=true\|health_before=([\d.-]+)\|health_after=([\d.-]+)', second)
    result = {'before_identity': previous, 'after_identity': current,
              'before_restoration': old_restore, 'after_restoration': new_restore,
              'old_world_and_owned_retired': retired >= 0 and expected <= labels,
              'title_wait_resumed': 0 <= retired < wait < resumed < spawned,
              'skill_natural_damage': bool(natural and float(natural[1]) > float(natural[2])),
              'manual_rearm_absent': 'PBZ_REARM_RETIRE:' not in text and 'ACTIVE_WORLD_TRIAL_REQUESTED=' not in text,
              'fault_absent': not any(s in text for s in ('state=FAULTED', 'PBZ_CONTROL_LIFECYCLE:ISSUE_', 'PREREQUISITE_NOT_READY='))}
    result['new_identity'] = bool(previous and current and previous['world_id'] != current['world_id']
        and previous['world_id'].split('|', 1)[0] == current['world_id'].split('|', 1)[0]
        and all(previous['participants'][k] != current['participants'][k]
                and previous['participants'][k]['class'] == current['participants'][k]['class']
                for k in ('player_controller', 'player', 'boss')))
    result['passed'] = old_restore['passed'] and new_restore['passed'] and all(result[k] for k in (
        'old_world_and_owned_retired', 'title_wait_resumed', 'skill_natural_damage',
        'manual_rearm_absent', 'fault_absent', 'new_identity'))
    return result


def collect(session,last_world_cycle=False):
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    state = read(ROOT / 'runtime' / ('official-validation-' + session) / 'state.json')
    work = Path(state['work'])
    assert state.get('restored') and work.name == session, 'closed matching session required'
    post = read(work / 'postcheck.json')
    assert post['validation_state'] == state['state_file'] and not post['formal_files_changed']
    assert not post['host_config_files_changed'] and post['host_registry_unchanged']
    assert post['research_box_empty'] and post['research_loader_removed']
    raw = (work / 'UE4SS.log').read_bytes()
    text = raw.decode('utf-8', errors='replace')
    stamp = read(work / 'auto-world-witness.json')
    assert stamp['state_file'] == state['state_file'] and stamp['pre_pid'] == stamp['post_pid']
    assert hashlib.sha256(text[:stamp['log_end']].encode('utf-8')).hexdigest() == stamp['log_prefix_sha256']
    deployments = list(work.glob('control-lifecycle-deployment-*.json'))
    assert len(deployments) == 1, 'one deployment, no manual rearm required'
    deployment = read(deployments[0])
    assert deployment['player_entry']
    assert 'MAP_TRAVEL_GUARD_READY=true' in text or deployment.get('scene_transition_trial')
    actions = read(work / 'settings-menu-actions.json')
    confirms = [a for a in actions if a['purpose'] == 'control_menu_confirm']
    continues = [a for a in actions if a['purpose'] == 'control_menu_continue']
    assert len(confirms) == len(continues) == 1 and confirms[0]['at'] < continues[0]['at']
    proof_text=text[:stamp['log_end']]
    scope_start=0
    if last_world_cycle:
        ready=list(re.finditer(r'PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=([^\r\n]+)',proof_text))
        assert len(ready)>=2 and ready[-2][1]==ready[-1][1]=='ahua_guitoudao'
        assert 'WORKBENCH_BOSS_SELECTED='not in proof_text[ready[-2].start():], 'no switching inside a World-cycle proof'
        scope_start=ready[-2].start()
    result = proof(proof_text[scope_start:])
    result.update(session=session, pid=stamp['post_pid'], log_sha256=hashlib.sha256(raw).hexdigest(),
                  module_source_sha256=deployment['module_source_sha256'], complete_mod=False,
                  travel_method='original-game-menu-after-verified-restoration',
                  active_receipt_carried_across_world=False,
                  proof_log_offset=scope_start,proof_log_end=stamp['log_end'],
                  ordinary_player_entry=not deployment.get('scene_transition_trial',False))
    target = work / 'auto-world-reassembly-evidence.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(target), 'passed': result['passed']}, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('session', nargs='?')
    parser.add_argument('--witness', action='store_true')
    parser.add_argument('--last-world-cycle',action='store_true',help='显式核对完成角色切换后的最后两次同角色装配；保留完整原日志')
    args = parser.parse_args()
    if args.witness:
        witness()
    else:
        raise SystemExit(collect(args.session,args.last_world_cycle))
