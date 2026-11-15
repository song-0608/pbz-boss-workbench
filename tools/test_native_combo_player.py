"""经实际部署的玩家连招键测试原生连招；所有输入仍通过研究窗口守卫。"""
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
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('cast','interrupt'))
    parser.add_argument('--leaf',choices=('skill_08','skill_05_hard','ca_01_teleport_redeye'))
    args=parser.parse_args()
    if args.leaf and args.action!='interrupt':raise RuntimeError('Leaf is only for timed cancellation')
    owner,state=practice.owned_session()
    if owner.get('phase')!='armed'or not any(r.get('slot')=='native_combo'and r.get('skill')=='attack_01'and r.get('key')in('R','F11')for r in owner.get('actual_bindings',[])):
        raise RuntimeError('Current deployed native combo required')
    native_key=next(r['key']for r in owner['actual_bindings']if r.get('slot')=='native_combo')
    if time.time()>min(state['deadline_unix'],state['control_probe_expires_at']-20)-55:
        raise RuntimeError('Insufficient native combo and restoration margin')
    log=practice.log_path(state);offset=len(log.read_text(encoding='utf-8',errors='replace'))
    menu.click(0,0,2560,1600,'control_native_combo')
    leaf_path=None
    if args.leaf:
        name={'skill_08':'GA_AHua_Skill_08','skill_05_hard':'GA_AHua_Skill_05_Hard',
            'ca_01_teleport_redeye':'GA_AHua_CA_01_GEx_Teleport_RedEye'}[args.leaf]
        leaf_path='/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/New/'+name+'.'+name+'_C'
    if args.action=='interrupt':
        until=time.monotonic()+(23 if leaf_path else 4)
        while time.monotonic()<until:
            delta=log.read_text(encoding='utf-8',errors='replace')[offset:]
            parent=re.search(r'KEY_SKILL_BEGIN=attack_01\|[^\r\n]*\|active=[1-9]\d*',delta)
            leaf=not leaf_path or re.search(r'COMBO_OBSERVED_ACTIVE='+re.escape(leaf_path)+r'\|active=[1-9]\d*',delta)
            if parent and leaf:break
            if 'state=FAULTED'in delta or 'native_combo success=false'in delta:raise RuntimeError('Native activation rejected; no cancellation input sent')
            time.sleep(.1)
        else:raise RuntimeError('No actual requested activity proof; no cancellation input sent')
        menu.click(0,0,2560,1600,'control_exit')
    until=time.monotonic()+(45 if args.action=='cast'else 8)
    while time.monotonic()<until:
        delta=log.read_text(encoding='utf-8',errors='replace')[offset:]
        if ('KEY_SKILL_END=attack_01|'in delta if args.action=='cast'else restoration_result(delta)['passed']):break
        if 'state=FAULTED'in delta or 'native_combo success=false'in delta:break
        time.sleep(.15)
    ended=re.search(r'KEY_SKILL_END=attack_01\|peak=(\d+)\|active=(\d+)\|natural=(true|false)\|health_before=([\d.-]+)\|health_after=([\d.-]+)',delta)
    natural=bool(ended and int(ended[1])>0 and int(ended[2])==0 and ended[3]=='true'
        and 'COMBO_SCHEDULER_END=natural=true|all_grants_at_baseline=true|brain_tick=false'in delta)
    cancelled=bool(re.search(r'KEY_SKILL_BEGIN=attack_01\|[^\r\n]*\|active=[1-9]\d*',delta)
        and 'COMBO_SCHEDULER_END=cancelled=true|all_grants_at_baseline=true|brain_tick=false'in delta
        and restoration_result(delta)['passed'])
    leaf_cancel=not leaf_path or bool(re.search(r'CANCEL_TRACE=invoking_cancel\|class=[^\r\n|]+ '+re.escape(leaf_path)+r'\|active=[1-9]\d*',delta))
    result={'at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'state_file':state['state_file'],'action':args.action,
        'requested_leaf':args.leaf,'log_offset':offset,'log_end':offset+len(delta),'actual_binding':'native_combo|attack_01|'+native_key,
        'natural_completion':natural,'damage_observed':bool(natural and float(ended[4])>float(ended[5])),
        'active_combo_cancelled':cancelled,'requested_leaf_cancel_invoked_while_active':leaf_cancel,
        'restoration':restoration_result(delta),'lines':[l for l in delta.splitlines()if any(t in l for t in (
            'KEY_SKILL_', 'COMBO_', 'CANCEL_', '[PBZBossControl]', 'ORIGINAL_PLAYER_', 'CAMERA_CLEANUP_ENGINE_VERIFIED'))]}
    target=Path(state['work'])/'native-combo-player-actions.json'
    rows=json.loads(target.read_text(encoding='utf-8'))if target.exists()else[]
    rows.append(result);target.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if(natural if args.action=='cast'else cancelled and leaf_cancel)else 1


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace');sys.exit(main())
