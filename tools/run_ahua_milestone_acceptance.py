"""在已启动的一轮普通入口中集中验收六个新键与600秒稳定性；不启动或重启游戏。"""
from datetime import datetime
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import ahua_practice as practice
import research_game_menu as menu
from control_action_evidence import restoration_result
from mod_installation import active_mod_root,ROOT

SKILLS=('special_05_a','special_11','special_move_01','special_move_back','special_move_left','special_move_right')


def validate_active_heartbeat(text,session,now):
    rows=[line.split('PBZ_PLAYER_UI:STATUS=',1)[1]for line in text.splitlines()if 'PBZ_PLAYER_UI:STATUS='in line]
    try:
        row=json.loads(rows[-1])
        valid=(row['session']==session and type(row['at'])is int and now-3<=row['at']<=now+1
            and type(row['expires_at'])is int and row['expires_at']>now and row['player']
            and row['text'].startswith('新娘阿花 | ACTIVE\n'))
    except (ValueError,KeyError,TypeError,IndexError,AttributeError):
        valid=False
    if not valid:raise RuntimeError('Continuous current-session ACTIVE heartbeat not verified')
    return row


def validate_start(owner,state,text,now,resume=False):
    if owner.get('phase')!='armed'or any(owner.get(k)for k in
        ('skill_lab','expanded','death_trial','scene_transition_trial','player_key_trial')):
        raise RuntimeError('A newly armed ordinary player entry without developer controls is required')
    rows=re.findall(r'^\[([^]]+)\][^\r\n]*PBZ_CONTROL_LIFECYCLE:INTERACTIVE_READY=([^\r\n]+)',text,re.M)
    if len(rows)!=1 or 'cleanup in 600 seconds'not in rows[0][1]or 'INTERACTIVE_END='in text:
        raise RuntimeError('One fresh complete 600-second assembly is required')
    if not owner.get('player_entry') or 'MAP_TRAVEL_GUARD_READY=true' not in text:
        raise RuntimeError('Ordinary player entry with verified map-travel protection is required')
    tz=datetime.fromisoformat(state['started_at']).tzinfo
    ready=datetime.fromisoformat(rows[0][0]).replace(tzinfo=tz).timestamp()
    maximum_elapsed,minimum_remaining=(180,410)if resume else(30,570)
    if not 0<=now-ready<=maximum_elapsed or min(state['deadline_unix'],state['control_probe_expires_at']-20)-now<minimum_remaining:
        raise RuntimeError('Start the batch within 30 seconds of full assembly; never extend its credentials')
    actual={r['slot']:r for r in owner.get('actual_bindings',[])}
    if any(k not in actual or actual[k]['skill']!=k for k in SKILLS):
        raise RuntimeError('All six ordinary bindings must be present in the deployed snapshot')
    return ready


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--resume-with-target-cycle',action='store_true',help='只允许同装配一次真实遮挡拒绝且完整恢复后重做；仅当前HUD遮挡时切换，不重启或续期')
    args=parser.parse_args()
    owner,state=practice.owned_session();path=practice.log_path(state);work=Path(state['work'])
    text=path.read_text(encoding='utf-8',errors='replace')
    ready=validate_start(owner,state,text[owner['log_offset']:],time.time(),args.resume_with_target_cycle)
    source=active_mod_root()
    deployment=max(work.glob('control-lifecycle-deployment-*.json'),key=lambda p:p.stat().st_mtime_ns)
    declared=json.loads(deployment.read_text(encoding='utf-8'))
    current={p.relative_to(source/'Scripts').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for p in(source/'Scripts').rglob('*.lua')if p.name!='main.lua'}
    if declared['module_source_sha256']!=current:raise RuntimeError('Installed source differs from the live deployment')
    previous=None
    if args.resume_with_target_cycle:
        previous_reports=list(work.glob('milestone-batch-*.json'))
        if len(previous_reports)!=1:raise RuntimeError('Only one bounded recovery of the original failed batch is allowed')
        previous=json.loads(previous_reports[0].read_text(encoding='utf-8'))
        if (previous.get('passed')or previous.get('resume_from')or previous.get('state_file')!=state['state_file']
            or previous.get('module_source_sha256')!=current
            or hashlib.sha256(text[:previous['log_end']].encode('utf-8')).hexdigest()!=previous['log_prefix_sha256']):
            raise RuntimeError('Current-session failed batch and immutable log prefix required')
        actions=json.loads((work/'player-extra-skill-actions.json').read_text(encoding='utf-8'))
        if not actions or actions[-1].get('passed')or not actions[-1].get('cleanup_restoration',{}).get('passed'):
            raise RuntimeError('Complete F10 restoration of the rejected action is required')
        if 'target visibility not verified'not in '\n'.join(actions[-1].get('lines',[])):
            raise RuntimeError('Recovery is only for the recorded real target-visibility rejection')
    witness={'at':datetime.now().astimezone().isoformat(),'state_file':state['state_file'],
        'deployment_file':deployment.name,'module_source_sha256':current,'skills':list(SKILLS),
        'game_launch_requested':False,'game_restart_requested':False,'phases':[],'passed':False}
    if previous:witness['resume_from']=previous_reports[0].name
    target=work/('milestone-batch-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')

    def save():target.write_text(json.dumps(witness,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def log():
        current_path=path if path.exists()else work/'UE4SS.log'
        return current_path.read_text(encoding='utf-8',errors='replace')
    def healthy():
        tail=log()[owner['log_offset']:]
        if any(t in tail for t in('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_',
            'PBZ_CONTROL_RESTORE:FAILED=','HUD_UNAVAILABLE=')):
            raise RuntimeError('Runtime health check failed; preserve evidence and let the existing supervisor close the session')
        return tail
    save()
    try:
        for interrupt in(False,True):
            name='ordinary_cancel'if interrupt else'ordinary_natural'
            command=[sys.executable,str(ROOT/'tools/test_player_skill_batch.py'),*SKILLS,
                *(['--interrupt']if interrupt else[])]
            print('集中验收：'+name,flush=True)
            run=subprocess.run(command,cwd=ROOT,timeout=280,creationflags=subprocess.CREATE_NO_WINDOW,
                capture_output=True,text=True,encoding='utf-8',errors='replace')
            print(run.stdout,flush=True)
            if run.stderr:print(run.stderr,file=sys.stderr,flush=True)
            witness['phases'].append({'name':name,'exit_code':run.returncode,'at':datetime.now().astimezone().isoformat()});save()
            if run.returncode:raise RuntimeError(name+' failed; the batch will not retry or restart the game')
        if time.time()-ready>275:raise RuntimeError('Insufficient time for 300 seconds ACTIVE within this unmodified 600-second assembly')
        start=len(log());menu.click(0,0,2560,1600,'control_enter')
        until=time.monotonic()+8
        while '[PBZBossControl] enter success=true state=ACTIVE'not in healthy()[max(0,start-owner['log_offset']):]:
            if time.monotonic()>=until:raise RuntimeError('Stability entry not confirmed')
            time.sleep(.2)
        active_started=time.time();exit_at=max(ready+565,active_started+305)
        if exit_at>ready+590:raise RuntimeError('Stability restoration margin unavailable')
        next_progress=0
        while time.time()<exit_at:
            validate_active_heartbeat(healthy(),'official-validation-'+work.name,time.time())
            if time.time()>=next_progress:
                print('稳定性观察：装配已运行'+str(int(time.time()-ready))+'秒；ACTIVE已持续'+str(int(time.time()-active_started))+'秒',flush=True)
                next_progress=time.time()+30
            time.sleep(1)
        menu.click(0,0,2560,1600,'control_exit');until=time.monotonic()+10
        while not restoration_result(log()[start:],'exit')['passed']:
            healthy()
            if time.monotonic()>=until:raise RuntimeError('Final restoration incomplete')
            time.sleep(.2)
        witness['phases'].append({'name':'stability_active_and_restored','active_elapsed':time.time()-active_started});save()
        until=ready+625
        while 'INTERACTIVE_END='not in healthy():
            if time.time()>=until:raise RuntimeError('Complete assembly end not observed')
            time.sleep(1)
        witness['passed']=True
    except Exception as error:
        witness['error']=str(error)
    finally:
        current=log();entered=current.rfind('[PBZBossControl] enter success=true state=ACTIVE')
        if entered>=owner['log_offset'] and not restoration_result(current[entered:])['passed']:
            try:
                menu.click(0,0,2560,1600,'control_exit');until=time.monotonic()+8
                while not restoration_result(log()[entered:],'exit')['passed'] and time.monotonic()<until:time.sleep(.2)
                witness['cleanup_restoration']=restoration_result(log()[entered:],'exit')
                if not witness['cleanup_restoration']['passed']:witness['passed']=False
            except Exception as error:
                witness['cleanup_error']=str(error);witness['passed']=False
        final=log();witness['log_end']=len(final)
        witness['log_prefix_sha256']=hashlib.sha256(final.encode('utf-8')).hexdigest();save()
        print(json.dumps({'report':str(target),'passed':witness['passed'],'error':witness.get('error'),
            'closure_and_collectors_still_required':True},ensure_ascii=False),flush=True)
    return 0 if witness['passed']else 1


if __name__=='__main__':raise SystemExit(main())
