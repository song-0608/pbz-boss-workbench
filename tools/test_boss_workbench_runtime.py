"""One consolidated workbench acceptance pass in an existing protected player assembly."""
import json
from pathlib import Path
import time
import ahua_practice as practice
import research_game_menu as menu
from control_action_evidence import restoration_result
from test_player_skill_batch import wait_for


def main():
    owner,state=practice.owned_session()
    assert owner['phase']=='armed' and owner.get('player_entry') and owner.get('workbench')
    path=practice.log_path(state);start=len(path.read_text(encoding='utf-8',errors='replace'))
    results=[]
    def send(action,token=None):
        offset=len(path.read_text(encoding='utf-8',errors='replace'))
        menu.click(0,0,2560,1600,action)
        tail=wait_for(path,offset,lambda t:token in t,7) if token else ''
        if token:assert token in tail,'Missing '+token
        return offset,tail
    def check(label,callback):
        callback();results.append(label);print(label+': PASS',flush=True)
    try:
        send('control_enter','[PBZBossControl] enter success=true state=ACTIVE')
        offset,tail=send('control_workbench_toggle','[PBZBossControl] workbench_toggle success=true state=OFF')
        tail=wait_for(path,offset,lambda t:restoration_result(t,'auto_exit')['passed'],6)
        assert restoration_result(tail,'auto_exit')['passed'] and 'WORKBENCH_INPUT_LOCKED='in tail
        results.append('active_open_restores_player')
        from capture_player_overlay import capture
        screenshot=capture('boss-workbench-open')
        blocked_offset=len(path.read_text(encoding='utf-8',errors='replace'))
        send('control_enter');send('control_skill')
        time.sleep(.4)
        blocked=path.read_text(encoding='utf-8',errors='replace')[blocked_offset:]
        assert 'enter success=true' not in blocked and 'KEY_SKILL_BEGIN='not in blocked
        results.append('takeover_and_skill_blocked_in_workbench')
        from player_settings import BOSSES
        preview_steps=len(BOSSES)
        for _ in range(preview_steps):send('control_workbench_down','workbench_down success=true state=OFF')
        send('control_workbench_confirm','workbench_confirm success=false state=OFF')
        assert 'WORKBENCH_BOSS_SELECTED='not in path.read_text(encoding='utf-8',errors='replace')[start:]
        results.append('unaccepted_boss_cannot_be_confirmed')
        send('control_workbench_close','WORKBENCH_INPUT_RESTORED=true')
        results.append('escape_closes_and_retires_input')
        send('control_workbench_toggle','workbench_toggle success=true state=OFF')
        for _ in range(preview_steps):send('control_workbench_up','workbench_up success=true state=OFF')
        send('control_workbench_confirm','WORKBENCH_INPUT_RESTORED=true')
        results.append('confirm_current_boss_closes')
        send('control_workbench_toggle','workbench_toggle success=true state=OFF')
        send('control_workbench_toggle','WORKBENCH_INPUT_RESTORED=true')
        results.append('insert_closes')
        send('control_workbench_toggle','workbench_toggle success=true state=OFF')
        send('control_exit','WORKBENCH_INPUT_RESTORED=true')
        results.append('f10_closes_while_off')
        send('control_enter','[PBZBossControl] enter success=true state=ACTIVE')
        offset,tail=send('control_exit','[PBZBossControl] exit success=true state=OFF')
        tail=wait_for(path,offset,lambda t:restoration_result(t,'exit')['passed'],6)
        assert restoration_result(tail,'exit')['passed']
        results.append('takeover_and_restore_after_repeated_menu_use')
        report={'passed':True,'checks':results,'screenshot':screenshot,'preview_steps':preview_steps}
    except Exception as error:
        report={'passed':False,'checks':results,'error':str(error)}
        raise
    finally:
        raw=path.read_text(encoding='utf-8',errors='replace')
        report.update(state_file=state['state_file'],log_offset=start,log_end=len(raw),lines=raw[start:].splitlines())
        target=Path(state['work'])/'boss-workbench-runtime-actions.json'
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items()if k!='lines'},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
