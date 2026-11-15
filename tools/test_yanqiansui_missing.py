"""Missing-only workbench and World cycle, without repeating accepted skills."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import ahua_practice as practice
import research_game_menu as menu
from test_player_skill_batch import wait_for
from control_action_evidence import restoration_result
from collect_multi_boss_switching import movement_camera_proof
from yanqiansui_skill_reuse import verify

ID='073_yanqiansui'
OWNED=('boss','boss_controller','target','target_controller','extra_target','extra_target_controller')


def main(finish_world=False):
    owner,state=practice.owned_session();work=Path(state['work']);path=practice.log_path(state)
    assert owner['phase']=='armed' and owner.get('player_entry') and owner.get('workbench')
    assert not owner.get('boss_candidate') and not owner.get('scene_transition_trial')
    deployment=practice.read(work/'control-lifecycle-deployment.json')
    assert deployment['boss_id']=='ahua_guitoudao'
    _,sources=verify(deployment['module_source_sha256'])
    target=work/'yanqiansui-missing-actions.json'
    def raw():return path.read_text(encoding='utf-8',errors='replace')
    if finish_world:
        report=practice.read(target)
        assert report['roundtrip_passed'] and not report.get('world_finished')
        assert report['state_file']==state['state_file'] and report['previous_ordinary_sources']==sources
        assert report['lines']==raw()[report['log_offset']:report['log_end']].splitlines()
        names=[l.split('PLAYER_ENTRY_READY=',1)[1]for l in raw()[report['world_scope_offset']:].splitlines()if 'PLAYER_ENTRY_READY='in l]
        assert names==[ID,ID]
    else:
        assert not target.exists() and min(state['deadline_unix'],state['control_probe_expires_at'])-time.time()>430
        report={'state_file':state['state_file'],'log_offset':len(raw()),'checks':[],
                'roundtrip_passed':False,'world_finished':False,'previous_ordinary_sources':sources}
    def save():
        current=raw();report.update(log_end=len(current),lines=current[report['log_offset']:].splitlines())
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+chr(10),encoding='utf-8')
    def send(action,token,seconds=10):
        off=len(raw());menu.click(0,0,2560,1600,action)
        tail=wait_for(path,off,lambda t:token in t,seconds,True)
        assert token in tail,'Missing '+token
        return off,tail
    def skill(name,interrupt=False):
        result=subprocess.run([sys.executable,str(practice.ROOT/'tools/test_player_skill_batch.py'),name,
            *(['--interrupt']if interrupt else[])],cwd=practice.ROOT,timeout=100,capture_output=True,
            text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW)
        print(result.stdout,flush=True);assert result.returncode==0,result.stderr or result.stdout
    def choose(identifier,steps):
        for _ in range(abs(steps)):
            send('control_workbench_down'if steps>0 else'control_workbench_up','workbench_down success=true'if steps>0 else'workbench_up success=true')
        _,tail=send('control_workbench_confirm','PLAYER_ENTRY_READY='+identifier,95)
        assert 'WORKBENCH_BOSS_SELECTED='+identifier in tail
        assert all('OWNED_DESTROY_VERIFIED='+name+'|engine_unusable=true'in tail for name in OWNED)
        assert 'WORKBENCH_INPUT_RESTORED=true'in tail
        time.sleep(2)
    try:
        save()
        if finish_world:
            skill('skill_01')
            from collect_auto_world_reassembly import witness
            witness();report['world_finished']=True;report['checks'].append('new_world_skill_and_restoration')
            return 0
        send('control_enter','enter success=true state=ACTIVE')
        off,_=send('control_workbench_toggle','WORKBENCH_INPUT_LOCKED=')
        assert restoration_result(wait_for(path,off,lambda t:restoration_result(t,'auto_exit')['passed'],10),'auto_exit')['passed']
        choose(ID,2);report['checks'].append('active_ahua_to_yanqiansui_cleanup');save()
        start,_=send('control_enter','enter success=true state=ACTIVE')
        baseline=wait_for(path,start,lambda t:'CAMERA_ARM_YAW='in t,5);assert 'CAMERA_ARM_YAW='in baseline
        menu.click(0,0,2560,1600,'control_look')
        menu.click(0,0,2560,1600,'control_backward')
        samples=wait_for(path,start,lambda t:t.count('CAMERA_ARM_YAW=')>=3,9)
        assert samples.count('CAMERA_ARM_YAW=')>=3,'complete current camera samples required'
        off,_=send('control_workbench_toggle','WORKBENCH_INPUT_LOCKED=')
        assert restoration_result(wait_for(path,off,lambda t:restoration_result(t,'auto_exit')['passed'],10),'auto_exit')['passed']
        motion=movement_camera_proof(raw()[start:]);assert motion['passed'],'fresh movement/camera readback required'
        report['movement_camera']=motion;report['movement_log_offset']=start
        report['checks'].append('yanqiansui_movement_camera_restored');save()
        choose('ahua_guitoudao',-2)
        skill('skill_01');skill('skill_08',True)
        report['checks'].append('return_ahua_controls_restored');save()
        send('control_workbench_toggle','WORKBENCH_INPUT_LOCKED=');choose(ID,2)
        report['world_scope_offset']=raw().rfind('PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY='+ID)
        skill('skill_01')
        report['checks'].append('yanqiansui_pre_world_skill_restored')
        report['roundtrip_passed']=True
        return 0
    except Exception as error:
        report['error']=type(error).__name__+': '+str(error)
        current=raw();last=current.rfind('[PBZBossControl] enter success=true state=ACTIVE')
        if last>=report['log_offset'] and not restoration_result(current[last:])['passed']:
            try:
                menu.click(0,0,2560,1600,'control_exit')
                report['failure_restoration']=restoration_result(wait_for(path,last,lambda t:restoration_result(t,'exit')['passed'],8),'exit')
            except Exception as cleanup:report['cleanup_error']=str(cleanup)
        return 1
    finally:
        save();print(json.dumps({k:v for k,v in report.items()if k!='lines'},ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--finish-world',action='store_true')
    raise SystemExit(main(p.parse_args().finish_world))
