"""用途：在当前已装配的离线研究游戏分批测F7/F5/F8；只测新增项，不重启或触碰正式存档。"""
import argparse
import json
from pathlib import Path
import re
import sys
import time
import ahua_practice as practice
import research_game_menu as menu
from control_action_evidence import cancellation_result, classify_stop, restoration_result, death_restoration_result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('enter', 'cycle', 'heavy', 'special', 'attack', 'left_attack', 'skill06', 'interrupt06', 'skill08', 'interrupt08',
        'skill07','interrupt07','dash','teleport_left','teleport_right','interrupt_left','interrupt_right','pause','death','death_skill08','exit',
        'heavy01','skill02','interrupt_heavy01','interrupt_skill02'))
    args = parser.parse_args()
    # 用途：重载样本的技能01在28秒后才完成尾部回读；保留有界40秒采样并同步预留租约余量。
    observation_seconds = (40 if args.action in ('attack', 'left_attack','heavy01','skill02') else
        25 if args.action in ('heavy', 'special', 'heavy01','skill02','skill06', 'skill08', 'skill07', 'dash',
                             'teleport_left', 'teleport_right', 'death', 'death_skill08') else 6)
    interrupted={'interrupt06':'skill_06','interrupt08':'skill_08','interrupt07':'skill_07',
                 'interrupt_left':'teleport_left','interrupt_right':'teleport_right',
                 'interrupt_heavy01':'heavy_01','interrupt_skill02':'skill_02'}.get(args.action)
    owner, state = practice.owned_session()
    # 用途：收尾定时器先于grant到期20秒；预留最长招式采样及恢复时间，不在边界抢按键。
    if args.action!='exit'and time.time() >= min(state['deadline_unix'], state.get('control_probe_expires_at', 0) - 20) - max(30, observation_seconds + 5):
        raise RuntimeError('Too close to automatic cleanup; do not start another input test')
    if owner.get('phase') != 'armed':
        raise RuntimeError('Practice must already be armed in this process')
    if args.action in ('heavy', 'special') and not owner.get('expanded'):
        raise RuntimeError('Unverified skill keys are only available in explicit developer mode')
    if args.action in ('skill08', 'interrupt08') and (owner.get('expanded') or owner.get('skill_lab')):
        raise RuntimeError('Default F8 skill08 cannot be tested in a developer key bank')
    path = practice.log_path(state)
    before = path.read_text(encoding='utf-8', errors='replace')
    offset = len(before)
    action, marker = {
        'enter': ('control_enter', '[PBZBossControl] enter success=true'),
        'cycle': ('control_target', '[PBZBossControl] target verified: '),
        'heavy01':('control_skill2','PBZ_CONTROL_LIFECYCLE:KEY_SKILL_END=heavy_01|'),
        'skill02':('control_skill3','PBZ_CONTROL_LIFECYCLE:KEY_SKILL_END=skill_02|'),
        'interrupt_heavy01':('control_skill2','[PBZBossControl] exit success=true'),
        'interrupt_skill02':('control_skill3','[PBZBossControl] exit success=true'),
        'heavy': ('control_skill8', 'PBZ_CONTROL_LIFECYCLE:KEY_SKILL_END=heavy_02|'),
        'special': ('control_skill9', 'PBZ_CONTROL_LIFECYCLE:KEY_SKILL_END=special_03|'),
        'skill06': ('control_skill5', 'PBZ_CONTROL_LIFECYCLE:KEY_SKILL_END=skill_06|'),
        'interrupt06': ('control_skill5', '[PBZBossControl] exit success=true'),
        'skill08': ('control_skill8', 'PBZ_CONTROL_LIFECYCLE:KEY_SKILL_END=skill_08|'),
        'interrupt08': ('control_skill8', '[PBZBossControl] exit success=true'),
        'skill07': ('control_skill9','PBZ_CONTROL_LIFECYCLE:KEY_SKILL_END=skill_07|'),
        'interrupt07': ('control_skill9','[PBZBossControl] exit success=true'),
        'dash': ('control_skill4','PBZ_CONTROL_LIFECYCLE:KEY_SKILL_END=dash|'),
        'teleport_left': ('control_teleport_left','PBZ_CONTROL_LIFECYCLE:KEY_SKILL_END=teleport_left|'),
        'teleport_right': ('control_teleport_right','PBZ_CONTROL_LIFECYCLE:KEY_SKILL_END=teleport_right|'),
        'interrupt_left': ('control_teleport_left','[PBZBossControl] exit success=true'),
        'interrupt_right': ('control_teleport_right','[PBZBossControl] exit success=true'),
        'attack': ('control_skill', 'PBZ_CONTROL_LIFECYCLE:KEY_SKILL_END=skill_01|'),
        'left_attack': ('control_attack', 'PBZ_CONTROL_LIFECYCLE:KEY_SKILL_END=skill_01|'),
        'exit': ('control_exit', '[PBZBossControl] exit success=true'),
        'pause': ('control_pause','[PBZBossControl] menu_exit success=true state=OFF'),
        'death': ('control_owned_damage','[PBZBossControl] auto_exit success=true state=OFF reason='+
                  ('owned boss disposed' if owner.get('native_death_trial') else 'boss health depleted')),
        'death_skill08':('control_death_skill08','[PBZBossControl] auto_exit success=true state=OFF reason=owned boss disposed'),
    }[args.action]
    if interrupted:action='control_cancel_'+{'skill_06':'skill06','skill_08':'skill08','skill_07':'skill07',
        'teleport_left':'teleport_left','teleport_right':'teleport_right','heavy_01':'heavy01','skill_02':'skill02'}[interrupted]
    menu.click(0, 0, 2560, 1600, action)
    deadline = time.monotonic() + observation_seconds
    needs_restore = args.action in ('exit', 'pause', 'death','death_skill08') or interrupted is not None
    restore_label = {'pause': 'menu_exit', 'death': 'auto_exit','death_skill08':'auto_exit'}.get(args.action, 'exit')
    def restore_proof(segment):
        if args.action in ('death','death_skill08'):
            return death_restoration_result(segment,owner.get('native_death_trial',False),'skill_08'if args.action=='death_skill08'else None)
        return restoration_result(segment, restore_label)
    segment = ''
    while time.monotonic() < deadline:
        segment = path.read_text(encoding='utf-8', errors='replace')[offset:]
        if 'state=FAULTED' in segment or 'PBZ_CONTROL_RESTORE:FAILED=' in segment or re.search(
                r'\[PBZBossControl\] (?!frame success=false state=OFF reason=(?:owned boss disposed|boss health depleted))\w+ success=false',segment):
            break
        if marker in segment and (not needs_restore or restore_proof(segment)['passed']):
            break
        time.sleep(.15)
    lines = [line for line in segment.splitlines() if any(token in line for token in (
        '[PBZBossControl]', 'KEY_SKILL_', 'ORIGINAL_PLAYER_', 'INTERACTIVE_TARGET', 'CANCEL_', 'SKILL_INSTANCE',
        'CAMERA_CLEANUP_ENGINE_VERIFIED=', 'OWNED_DEATH_', 'DEATH_TRIAL_', 'ISSUE_',
        'PBZ_CONTROL_RESTORE:', 'CONTROLLED_BOSS_DISPOSED=', 'CONTROL_WORLD_ID=', 'CONTROL_PARTICIPANT='))]
    result = {'at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'action': args.action,
              'marker_observed': marker in segment, 'log_offset': offset, 'log_end': offset + len(segment),
              'observation_seconds': observation_seconds, 'lines': lines,
              'state_file': state['state_file'], 'restart_requested': False}
    if args.action in ('death','death_skill08'):result['native_death_trial']=owner.get('native_death_trial',False)
    if interrupted:
        result['interrupted_skill']=interrupted
        result['active_candidate_cancelled']=cancellation_result(segment, interrupted)
        result['completion_kind']=classify_stop(segment)
    if needs_restore:
        result['restoration'] = restore_proof(segment)
    if args.action == 'interrupt06':
        result['active_skill06_cancelled'] = bool('KEY_SKILL_BEGIN=skill_06|' in segment
            and re.search(r'CANCEL_ACTIVE_BEFORE=[1-9]\d*', segment)
            and 'CANCEL_RESULT=true|active=0' in segment and marker in segment)
    if args.action == 'interrupt08':
        result['active_skill08_cancelled'] = bool('KEY_SKILL_BEGIN=skill_08|' in segment
            and re.search(r'CANCEL_ACTIVE_BEFORE=[1-9]\d*', segment)
            and 'CANCEL_RESULT=true|active=0' in segment and marker in segment)
    target = Path(state['work']) / 'expanded-actions.json'
    rows = json.loads(target.read_text(encoding='utf-8')) if target.exists() else []
    rows.append(result)
    target.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    cancellation_ok = not interrupted or result.get('active_candidate_cancelled')is True
    restoration_ok = result.get('restoration', {}).get('passed', True)
    return 0 if result['marker_observed'] and cancellation_ok and restoration_ok else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.exit(main())
