"""在批量招式完成后复用同一600秒装配验收持续接管，不启动游戏或续期。"""
from datetime import datetime
import json
from pathlib import Path
import re
import time
import ahua_practice as practice
import research_game_menu as menu
from control_action_evidence import restoration_result
from player_status_stream import StatusStream
from test_player_skill_batch import wait_for


def main():
    owner,state=practice.owned_session();assert owner['phase']=='armed' and owner.get('player_entry')
    path=practice.log_path(state);work=Path(state['work'])
    def raw():
        try:return path.read_text(encoding='utf-8',errors='replace')
        except FileNotFoundError:return (work/'UE4SS.log').read_text(encoding='utf-8',errors='replace')
    text=raw()[owner['log_offset']:]
    rows=re.findall(r'^\[([^]]+)\][^\r\n]*INTERACTIVE_READY=([^\r\n]+)',text,re.M)
    assert len(rows)==1 and 'cleanup in 600 seconds'in rows[0][1] and 'INTERACTIVE_END='not in text
    ready=datetime.fromisoformat(rows[0][0]).replace(tzinfo=datetime.fromisoformat(state['started_at']).tzinfo).timestamp()
    assert 0<=time.time()-ready<=275,'preserve unchanged lease; insufficient continuous ACTIVE window'
    assert min(state['deadline_unix'],state['control_probe_expires_at']-20)>ready+610
    assert restoration_result(text)['passed'],'previous batch must have fully restored the player'
    start=len(raw());target=work/'player-stability-tail.json';assert not target.exists()
    result={'state_file':state['state_file'],'log_offset':start,'passed':False}
    try:
        menu.click(0,0,2560,1600,'control_enter')
        tail=wait_for(path,start,lambda t:'[PBZBossControl] enter success=true state=ACTIVE'in t,8,True)
        assert '[PBZBossControl] enter success=true state=ACTIVE'in tail
        menu.click(0,0,2560,1600,'control_forward');menu.click(0,0,2560,1600,'control_look')
        active_started=time.time();exit_at=max(ready+565,active_started+305)
        assert exit_at<=ready+590
        stream=StatusStream(path,'official-validation-'+work.name)
        progress=0
        while time.time()<exit_at:
            status=stream.read(time.time())
            assert status and status['text'].startswith('新娘阿花 | ACTIVE\n'),'fresh continuous current Boss status required'
            text=raw()[owner['log_offset']:]
            assert not any(k in text for k in ('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_',
                'HUD_UNAVAILABLE=','PBZ_CONTROL_RESTORE:FAILED='))
            if time.time()>=progress:
                print('阿花持续接管 '+str(int(time.time()-active_started))+' 秒；装配 '+str(int(time.time()-ready))+' 秒',flush=True)
                progress=time.time()+30
            time.sleep(1)
        menu.click(0,0,2560,1600,'control_exit')
        tail=wait_for(path,start,lambda t:restoration_result(t,'exit')['passed'],10)
        assert restoration_result(tail,'exit')['passed']
        result['active_seconds']=time.time()-active_started
        while 'INTERACTIVE_END='not in raw()[owner['log_offset']:]:
            assert time.time()<ready+620
            time.sleep(1)
        result['passed']=True
    except Exception as error:result['error']=str(error)
    finally:
        result['log_end']=len(raw())
        target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['passed']else 1


if __name__=='__main__':raise SystemExit(main())
