"""有界实测真实招式来袭，血量耗尽和恢复必须分别从原始区间回读。"""
from datetime import datetime
import json
from pathlib import Path
import re
import time
import ahua_practice as practice
import research_game_menu as menu
from control_action_evidence import restoration_result


def main():
    owner,state=practice.owned_session()
    assert owner['phase']=='armed' and owner.get('incoming_combat_trial')
    assert min(state['deadline_unix'],state['control_probe_expires_at'])-time.time()>400
    path=practice.log_path(state)
    offset=len(path.read_text(encoding='utf-8',errors='replace'))
    menu.click(0,0,2560,1600,'control_owned_damage')
    began=time.monotonic();segment='';manual_exit=False
    while time.monotonic()-began<365:
        segment=path.read_text(encoding='utf-8',errors='replace')[offset:]
        if any(token in segment for token in ('ISSUE_INCOMING_COMBAT','INCOMING_COMBAT_START_REJECTED=',
                'state=FAULTED','PBZ_CONTROL_RESTORE:FAILED=')):
            break
        if restoration_result(segment,'auto_exit')['passed']:
            break
        drops=[(float(a),float(b)) for a,b in re.findall(r'OWNED_COMBAT_HEALTH=before=([\d.-]+)\|after=([\d.-]+)',segment)]
        if time.monotonic()-began>30 and not any(a>b for a,b in drops):
            break
        if 'INCOMING_COMBAT_TIMEOUT='in segment:
            break
        time.sleep(.25)
    restoration=restoration_result(segment,'auto_exit')
    if restoration['passed']:
        until=time.monotonic()+65
        while time.monotonic()<until:
            segment=path.read_text(encoding='utf-8',errors='replace')[offset:]
            if 'INCOMING_COMBAT_POST_RESTORE_END=true'in segment or 'INCOMING_COMBAT_POST_RESTORE_REJECTED='in segment:
                break
            time.sleep(.25)
    if not restoration['passed']:
        # 没有死亡不掩盖：用正式F10通道真实停止来袭并恢复，保留失败结果。
        if not practice.read(practice.OWNER).get('phase')in('closed','failed_and_closed'):
            menu.click(0,0,2560,1600,'control_exit');manual_exit=True
            until=time.monotonic()+5
            while time.monotonic()<until:
                segment=path.read_text(encoding='utf-8',errors='replace')[offset:]
                if restoration_result(segment,'exit')['passed']:break
                time.sleep(.15)
    drops=[(float(a),float(b)) for a,b in re.findall(r'OWNED_COMBAT_HEALTH=before=([\d.-]+)\|after=([\d.-]+)',segment)]
    result={'at':datetime.now().astimezone().isoformat(),'state_file':state['state_file'],
            'log_offset':offset,'log_end':offset+len(segment),'manual_exit':manual_exit,
            'native_skill_casts':len(re.findall('INCOMING_COMBAT_CAST=',segment)),
            'observed_health_changes':drops,'depletion_observed':any(a>0 and b<=0 for a,b in drops),
            'restoration':restoration_result(segment,'auto_exit'),
            'manual_restoration':restoration_result(segment,'exit'),
            'source_cleanup':'INCOMING_COMBAT_STOP=all_source_abilities_inactive=true'in segment}
    observed=[float(v) for v in re.findall(r'INCOMING_COMBAT_SNAPSHOT=(?:stopped|after_restore)\|player_health=([\d.-]+)',segment)]
    result['post_restore_health_samples']=observed
    result['post_restore_stability_verified']=bool(observed and len(set(observed))==1
        and 'INCOMING_COMBAT_POST_RESTORE_BEGIN=seconds=60'in segment
        and 'INCOMING_COMBAT_POST_RESTORE_END=true'in segment)
    result['passed']=result['depletion_observed'] and result['restoration']['passed'] and result['source_cleanup'] and not manual_exit
    target=Path(state['work'])/'incoming-combat-actions.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['passed'] and result['post_restore_stability_verified']else 1


if __name__=='__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
