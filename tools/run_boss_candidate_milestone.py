"""One bounded candidate batch: real keys, natural/cancel, movement/camera, and 600s cleanup."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import ahua_practice as practice
import research_game_menu as menu
from control_action_evidence import restoration_result
from test_player_skill_batch import wait_for,action_proof
from player_status_stream import valid_status


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume',action='store_true',help='复用同一装配内已通过的招式，不延长租约')
    args=parser.parse_args()
    owner,state=practice.owned_session()
    assert owner.get('phase')=='armed' and owner.get('boss_candidate')=='057_wanjun'
    assert not owner.get('player_entry') and not owner.get('skill_lab') and not owner.get('expanded')
    path=practice.log_path(state);work=Path(state['work']);offset=owner['log_offset']
    def raw():return path.read_text(encoding='utf-8',errors='replace')
    text=raw()[offset:]
    ready_rows=re.findall(r'^\[([^]]+)\][^\r\n]*INTERACTIVE_READY=([^\r\n]+)',text,re.M)
    assert len(ready_rows)==1 and 'cleanup in 600 seconds' in ready_rows[0][1]
    tz=datetime.fromisoformat(state['started_at']).tzinfo
    ready=datetime.fromisoformat(ready_rows[0][0]).replace(tzinfo=tz).timestamp()
    assert 0<=time.time()-ready<=(240 if args.resume else 30) and state['deadline_unix']-ready>=640
    assert min(state['deadline_unix'],state['control_probe_expires_at']-20)-time.time()>ready+600-time.time()+10
    report={'candidate':owner['boss_candidate'],'state_file':state['state_file'],
            'started_at':datetime.now().astimezone().isoformat(),'log_offset':offset,'phases':[],'passed':False}
    target=work/'boss-candidate-milestone.json'
    if target.exists():
        previous=json.loads(target.read_text(encoding='utf-8'))
        assert args.resume and previous['state_file']==state['state_file'] and previous['candidate']==owner['boss_candidate']
        archive=work/('boss-candidate-milestone-attempt-'+str(time.time_ns())+'.json')
        archive.write_text(target.read_text(encoding='utf-8'),encoding='utf-8')
        report['resumed_from']=str(archive)
    def save():
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def healthy():
        text=raw()[offset:]
        assert not any(t in text for t in ('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_',
            'PBZ_CONTROL_RESTORE:FAILED=','HUD_UNAVAILABLE=')),'candidate runtime health failed'
        return text
    def send(action,token):
        start=len(raw());menu.click(0,0,2560,1600,action)
        tail=wait_for(path,start,lambda t:token in t,9,True)
        assert token in tail,'Missing '+token
        return start
    save()
    try:
        skills=['skill_01','heavy_01','skill_02','dash']
        actual={r['skill'] for r in owner['actual_bindings']}
        assert set(skills)<=actual,'all independent candidate bindings required'
        for interrupt in (False,True):
            remaining=list(skills)
            if args.resume:
                actions_path=work/'player-extra-skill-actions.json'
                actions=json.loads(actions_path.read_text(encoding='utf-8'))if actions_path.exists()else []
                current=raw()
                for action in actions:
                    if action.get('state_file')!=state['state_file'] or action.get('interrupt')!=interrupt or not action.get('passed'):continue
                    start,end=action['log_offset'],action['log_end']
                    assert offset<=start<end<=len(current),'resume action outside current assembly'
                    interval=current[start:end]
                    assert action['lines']==interval.splitlines(),'resume action raw log mismatch'
                    proof=action_proof(interval,action['skill'])
                    verified=proof['active_cancel_and_restoration']if interrupt else proof['natural_completion']and proof['restoration']['passed']
                    assert verified,'resume requires independent raw proof'
                    if action['skill']in remaining:remaining.remove(action['skill'])
            if not remaining:
                report['phases'].append({'name':'cancel'if interrupt else'natural','exit_code':0,'reused_current_assembly':True})
                save();continue
            command=[sys.executable,str(practice.ROOT/'tools/test_player_skill_batch.py'),*remaining]
            if interrupt:command.append('--interrupt')
            result=subprocess.run(command,cwd=practice.ROOT,timeout=260,capture_output=True,
                text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW)
            print(result.stdout,flush=True)
            report['phases'].append({'name':'cancel' if interrupt else 'natural','exit_code':result.returncode})
            save()
            assert result.returncode==0,result.stderr or result.stdout
        assert time.time()-ready<265,'insufficient unchanged lease for continuous ACTIVE'
        start=send('control_enter','[PBZBossControl] enter success=true state=ACTIVE')
        menu.click(0,0,2560,1600,'control_forward')
        menu.click(0,0,2560,1600,'control_look')
        active_started=time.time();exit_at=max(ready+565,active_started+305)
        assert exit_at<=ready+590,'restoration margin unavailable'
        next_progress=0
        while time.time()<exit_at:
            text=healthy()
            rows=re.findall(r'PBZ_PLAYER_UI:STATUS=(\{[^\r\n]+\})',text)
            status=json.loads(rows[-1]) if rows else None
            assert valid_status(status,'official-validation-'+work.name,time.time()),'fresh candidate HUD required'
            assert status['text'].startswith('巨锤客：万钧 | ACTIVE\n'),'candidate must remain ACTIVE'
            if time.time()>=next_progress:
                print('万钧稳定性：装配 '+str(int(time.time()-ready))+' 秒，连续接管 '+str(int(time.time()-active_started))+' 秒',flush=True)
                next_progress=time.time()+30
            time.sleep(1)
        menu.click(0,0,2560,1600,'control_exit')
        tail=wait_for(path,start,lambda t:restoration_result(t,'exit')['passed'],10)
        assert restoration_result(tail,'exit')['passed'],'final candidate restoration incomplete'
        distances=re.findall(r'CONTROLLED_BOSS_POSITION_DELTA=([\d.eE+-]+)',tail)
        assert distances and float(distances[-1])>1,'actual movement readback required'
        control=re.findall(r'CAMERA_CONTROL_YAW=([\d.eE+-]+)',tail)
        arm=re.findall(r'CAMERA_ARM_YAW=([\d.eE+-]+)',tail)
        assert len(control)>=2 and len(arm)>=2 and abs(float(control[-1])-float(control[0]))>0.1,'actual camera rotation required'
        report['phases'].append({'name':'movement_camera_and_continuous_active','active_seconds':time.time()-active_started,
            'movement_delta':float(distances[-1]),'control_yaws':control,'arm_yaws':arm})
        save()
        until=ready+620
        while 'INTERACTIVE_END=' not in healthy():
            assert time.time()<until,'assembly cleanup not observed'
            time.sleep(1)
        report['passed']=True
    except Exception as error:
        report['error']=str(error)
        current=raw();last=current.rfind('[PBZBossControl] enter success=true state=ACTIVE')
        if last>=offset and not restoration_result(current[last:])['passed']:
            try:
                menu.click(0,0,2560,1600,'control_exit')
                report['failure_restoration']=restoration_result(wait_for(path,last,
                    lambda t:restoration_result(t,'exit')['passed'],10),'exit')
            except Exception as cleanup:report['cleanup_error']=str(cleanup)
    finally:
        report['log_end']=len(raw());save()
        print(json.dumps(report,ensure_ascii=False),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
