"""用途：同一离线游戏逐项试放候选，等真实日志收集完再测下一招；不重启。"""
import argparse
import json
from pathlib import Path
import re
import sys
import time
import ahua_practice as practice
import research_game_menu as menu
from control_action_evidence import restoration_result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('cast', 'next', 'interrupt'))
    parser.add_argument('--candidate', help='用途：只通过真实F9在本轮已装配列表中选择指定候选，不绕过按键或授予能力')
    parser.add_argument('--interrupt-leaf',choices=('skill_08','skill_05','skill_05_b','skill_05_hard','ca_01_teleport_redeye'),help='仅已登记父类连招取消试验：等实际观察到该叶能力后再请求F10')
    args = parser.parse_args()
    owner, state = practice.owned_session()
    if owner.get('phase') != 'armed' or not owner.get('skill_lab'):
        raise RuntimeError('Current protected developer skill lab must be armed')
    leaf_allowlist={'attack_01':{'skill_08','skill_05_hard','ca_01_teleport_redeye'},
        'homing_flower':{'skill_05','skill_05_b'},
        'homing_flower_hard':{'skill_05_hard','skill_05_b','ca_01_teleport_redeye'}}
    if args.interrupt_leaf and not(args.action=='interrupt'and owner.get('combo_scheduler_trial')
            and args.interrupt_leaf in leaf_allowlist.get(args.candidate,set())):
        raise RuntimeError('Leaf-timed interruption requires explicit matching parent scheduler trial')
    if min(state['deadline_unix'], state['control_probe_expires_at'] - 20) - time.time() < 60:
        raise RuntimeError('Insufficient time for skill observation and verified restoration')
    path = practice.log_path(state)
    before = path.read_text(encoding='utf-8', errors='replace')
    segment = before[owner['log_offset']:]
    selection_inputs=[]
    if args.candidate:
        available=re.findall(r'LAB_CANDIDATE_AVAILABLE=([\w_]+)',segment)
        if args.action=='next' or args.candidate not in available or not 1<=len(available)<=32:
            raise RuntimeError('Requested candidate is not in this assembly')
        for _ in range(len(available)):
            current_changes=re.findall(r'\[PBZBossControl\] lab_next success=true state=ACTIVE reason=([\w_]+)',segment)
            initial=re.findall(r'\[PBZBossControl\] lab_selected=([\w_]+)',segment)
            current=current_changes[-1] if current_changes else initial[-1] if initial else None
            if current==args.candidate:
                break
            selection_offset=len(before)
            menu.click(0,0,2560,1600,'control_lab_next')
            limit=time.monotonic()+5
            while time.monotonic()<limit:
                before=path.read_text(encoding='utf-8',errors='replace')
                delta=before[selection_offset:]
                if 'lab_next success=true state=ACTIVE reason=' in delta:
                    selection_inputs.append(delta.split('lab_next success=true state=ACTIVE reason=',1)[1].splitlines()[0]);break
                if 'success=false' in delta or 'state=FAULTED' in delta:
                    raise RuntimeError('Candidate selection rejected; current skill/control preserved')
                time.sleep(.1)
            else:
                raise RuntimeError('No selection readback; candidate activation not requested')
            segment=before[owner['log_offset']:]
        else:
            raise RuntimeError('Candidate selection did not converge within the actual bank')
    selected = re.findall(r'\[PBZBossControl\] lab_selected=([\w_]+)', segment)
    changes = re.findall(r'\[PBZBossControl\] lab_next success=true state=ACTIVE reason=([\w_]+)', segment)
    if not selected:
        raise RuntimeError('No candidate selection proof in this assembly')
    candidate = changes[-1] if changes else selected[-1]
    offset = len(before)
    marker = ('[PBZBossControl] exit success=true' if args.action == 'interrupt' else
              'PBZ_CONTROL_LIFECYCLE:KEY_SKILL_END=' + candidate + '|'
              if args.action == 'cast' else '[PBZBossControl] lab_next success=true')
    combined_cancel=args.action=='interrupt'and not args.interrupt_leaf
    menu.click(0,0,2560,1600,'control_cancel_lab_cast'if combined_cancel else'control_lab_'+('cast'if args.action=='interrupt'else args.action))
    interruption_error=None
    leaf_path=None
    if args.action == 'interrupt':
        # 用途：必须先看到本次候选实际活动，才请求F10；不把未出招的退出当作中断通过。
        if args.interrupt_leaf:
            name={'skill_08':'GA_AHua_Skill_08','skill_05':'GA_AHua_Skill_05','skill_05_b':'GA_AHua_Skill_05_B',
                'skill_05_hard':'GA_AHua_Skill_05_Hard',
                'ca_01_teleport_redeye':'GA_AHua_CA_01_GEx_Teleport_RedEye'}[args.interrupt_leaf]
            leaf_path='/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/New/'+name+'.'+name+'_C'
        begin_deadline = time.monotonic() + (23 if leaf_path else 4)
        while time.monotonic() < begin_deadline:
            current = path.read_text(encoding='utf-8', errors='replace')[offset:]
            parent_active=re.search(r'KEY_SKILL_BEGIN=' + re.escape(candidate) + r'\|[^\r\n]*\|active=[1-9]\d*', current)
            leaf_active=not leaf_path or re.search(r'COMBO_OBSERVED_ACTIVE='+re.escape(leaf_path)+r'\|active=[1-9]\d*',current)
            if parent_active and leaf_active:
                break
            if 'state=FAULTED' in current or re.search(r'\[PBZBossControl\] \w+ success=false', current):
                interruption_error='Candidate activation failed before cancellation request'
                break
            time.sleep(.05)
        else:
            interruption_error='No actual active candidate proof; cancellation not requested'
        if not interruption_error and not combined_cancel:
            menu.click(0, 0, 2560, 1600, 'control_exit')
    deadline = time.monotonic() + (55 if args.action=='cast'and candidate in('attack_01','homing_flower','homing_flower_hard')else 40 if args.action=='cast' else 6)
    delta = ''
    while time.monotonic() < deadline:
        delta = path.read_text(encoding='utf-8', errors='replace')[offset:]
        complete = marker in delta and (args.action != 'interrupt' or restoration_result(delta, 'exit')['passed'])
        if complete or interruption_error or 'state=FAULTED' in delta or re.search(r'\[PBZBossControl\] \w+ success=false', delta):
            break
        time.sleep(.15)
    rows = [line for line in delta.splitlines() if any(token in line for token in (
        '[PBZBossControl]', 'KEY_SKILL_', 'SKILL_GEOMETRY', 'SKILL_TARGET_HEALTH', 'SKILL_INSTANCE',
        'CANCEL_', 'COMBO_', 'ORIGINAL_PLAYER_', 'PBZ_REMOTE_MAINTAIN', 'ISSUE_', 'REJECTED'))]
    result = {'at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'action': args.action,
              'interrupt_leaf_requested':args.interrupt_leaf,
              'candidate_requested':args.candidate,'selection_key_readbacks':selection_inputs,
              'candidate_before_input': candidate, 'marker_observed': marker in delta,
              'log_offset': offset, 'log_end': offset+len(delta), 'lines': rows, 'state_file': state['state_file'], 'restart_requested': False}
    if args.action == 'interrupt':
        result['interruption_error']=interruption_error
        direct_cancel=bool(re.search(r'CANCEL_ACTIVE_BEFORE=[1-9]\d*', delta)and 'CANCEL_RESULT=true|active=0'in delta)
        combo_cancel=(candidate in('attack_01','homing_flower','homing_flower_hard')and owner.get('combo_scheduler_trial')is True
            and re.search(r'KEY_SKILL_BEGIN='+re.escape(candidate)+r'\|[^\r\n]*\|active=[1-9]\d*',delta)
            and 'COMBO_SCHEDULER_END=cancelled=true|all_grants_at_baseline=true|brain_tick=false'in delta)
        result['active_candidate_cancelled']=bool((direct_cancel or combo_cancel)and marker in delta)
        result['restoration']=restoration_result(delta, 'exit')
        if leaf_path:
            result['requested_leaf_cancel_invoked_while_active']=bool(re.search(
                r'CANCEL_TRACE=invoking_cancel\|class=[^\r\n|]+ '+re.escape(leaf_path)+r'\|active=[1-9]\d*',delta))
    output = Path(state['work']) / 'skill-lab-actions.json'
    history = json.loads(output.read_text(encoding='utf-8')) if output.exists() else []
    history.append(result)
    output.write_text(json.dumps(history, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if (result['marker_observed'] and (args.action != 'interrupt' or
        (result['active_candidate_cancelled'] and result['restoration']['passed']))
        and result.get('requested_leaf_cancel_invoked_while_active',True)) else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.exit(main())
