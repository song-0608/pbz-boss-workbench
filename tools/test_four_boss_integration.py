"""Missing ordinary integration milestones, sharing one guarded research launch."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import ahua_practice as practice
import research_game_menu as menu
from test_player_skill_batch import wait_for
from control_action_evidence import restoration_result
from collect_multi_boss_switching import movement_camera_proof
from four_boss_integration_workflow import verify,verify_current

IDS=('ahua_guitoudao','057_wanjun','073_yanqiansui','056_youlong')
OWNED=('boss','boss_controller','target','target_controller','extra_target','extra_target_controller')


def main(workflow,identifier,finish_world=False,refusal=False):
    verify(workflow)
    owner,state=practice.owned_session();work=Path(state['work']);path=practice.log_path(state)
    assert owner['phase']=='armed'and owner.get('player_entry')and owner.get('workbench')
    deployment=practice.read(work/'control-lifecycle-deployment.json')
    old,old_sources=verify_current(deployment['module_source_sha256'])
    def raw():return path.read_text(encoding='utf-8',errors='replace')
    target=work/('four-boss-refusal.json'if refusal else identifier+'-ordinary-integration.json')
    if finish_world:
        report=practice.read(target)
        assert report['roundtrip_passed']and not report['world_finished']and not report.get('error')
        assert report['state_file']==state['state_file']and report['workflow']==str(workflow)
        assert report['lines']==raw()[report['log_offset']:report['log_end']].splitlines()
        assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',raw()[report['world_scope_offset']:])==[identifier,identifier]
    else:
        assert not target.exists(),'Preserve existing attempt'
        assert min(state['deadline_unix'],state['control_probe_expires_at'])-time.time()> (60 if refusal else 310)
        report={'state_file':state['state_file'],'workflow':str(workflow),'boss':identifier,
            'log_offset':len(raw()),'checks':[],'roundtrip_passed':False,'world_finished':False,
            'previous_ordinary_sources':old_sources}
    def save():
        text=raw();report.update(log_end=len(text),lines=text[report['log_offset']:].splitlines())
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def send(action,token,seconds=10):
        off=len(raw());menu.click(0,0,2560,1600,action)
        tail=wait_for(path,off,lambda t:token in t,seconds,True)
        assert token in tail,'Missing '+token
        return off,tail
    def skill(names,interrupt=False):
        result=subprocess.run([sys.executable,str(workflow/'test_player_skill_batch.py'),*names,
            *(['--interrupt']if interrupt else[])],cwd=practice.ROOT,capture_output=True,text=True,
            encoding='utf-8',errors='replace',timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
        print(result.stdout,flush=True);assert result.returncode==0,result.stderr or result.stdout
    def opened_active():
        off,_=send('control_workbench_toggle','WORKBENCH_INPUT_LOCKED=')
        proof=restoration_result(wait_for(path,off,lambda t:restoration_result(t,'auto_exit')['passed'],10),'auto_exit')
        assert proof['passed'];return off
    def move_cursor(current,wanted):
        steps=IDS.index(wanted)-IDS.index(current)
        for _ in range(abs(steps)):
            send('control_workbench_down'if steps>0 else'control_workbench_up',
                'workbench_down success=true'if steps>0 else'workbench_up success=true')
    def choose(current,wanted):
        move_cursor(current,wanted)
        off,tail=send('control_workbench_confirm','PLAYER_ENTRY_READY='+wanted,95)
        assert 'WORKBENCH_BOSS_SELECTED='+wanted in tail
        assert 'WORKBENCH_INPUT_RESTORED=true'in tail
        assert all('OWNED_DESTROY_VERIFIED='+n+'|engine_unusable=true'in tail for n in OWNED)
        time.sleep(2);return off
    try:
        save()
        if finish_world:
            skill(['skill_01'])
            from collect_auto_world_reassembly import witness
            witness()
            stamp=work/(identifier+'-world-witness.json');assert not stamp.exists()
            stamp.write_bytes((work/'auto-world-witness.json').read_bytes())
            report['world_finished']=True;report['checks'].append('new_world_skill_restored')
            send('control_workbench_toggle','WORKBENCH_INPUT_LOCKED=');choose(identifier,'ahua_guitoudao')
            report['checks'].append('final_return_ahua');return 0
        assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',raw())[-1]=='ahua_guitoudao'
        send('control_enter','enter success=true state=ACTIVE');opened_active()
        report['checks'].append('active_ahua_open_restores_player')
        if refusal:
            move_cursor('ahua_guitoudao','073_yanqiansui')
            off,tail=send('control_workbench_confirm','WORKBENCH_SELECTION_REJECTED=073_yanqiansui|',20)
            assert not any(k in tail for k in ('OWNED_DESTROY_VERIFIED=','WORKBENCH_BOSS_SELECTED=','SPAWN_ATTEMPT=','WORKBENCH_INPUT_RESTORED=true'))
            report['refusal_log_offset']=off
            send('control_workbench_close','WORKBENCH_INPUT_RESTORED=true')
            # Cursor persists even after a refused selection; normalize to Ahua without reassembly.
            send('control_workbench_toggle','WORKBENCH_INPUT_LOCKED=')
            move_cursor('073_yanqiansui','ahua_guitoudao')
            send('control_workbench_confirm','WORKBENCH_INPUT_RESTORED=true')
            skill(['skill_01']);report['checks'].append('refusal_preserves_current_ahua_and_controls')
            report['refusal_passed']=True;return 0
        choose('ahua_guitoudao',identifier);report['checks'].append('new_boss_selected_with_cleanup');save()
        if identifier=='056_youlong':
            skill(['skill_01','heavy_01','skill_02','dash'])
            skill(['skill_01','heavy_01','skill_02','dash'],True)
            report['checks'].append('four_ordinary_natural_and_cancel')
        else:report['checks'].append('eight_ordinary_skills_reparsed_from_closed_evidence')
        start,_=send('control_enter','enter success=true state=ACTIVE')
        wait_for(path,start,lambda t:'CAMERA_ARM_YAW='in t,5)
        menu.click(0,0,2560,1600,'control_look');menu.click(0,0,2560,1600,'control_backward')
        wait_for(path,start,lambda t:t.count('CAMERA_ARM_YAW=')>=3,9)
        opened_active();motion=movement_camera_proof(raw()[start:]);assert motion['passed']
        report.update(movement_log_offset=start,movement_camera=motion)
        report['checks'].append('new_boss_movement_camera_restored');save()
        choose(identifier,'ahua_guitoudao');skill(['skill_01']);skill(['skill_08'],True)
        report['checks'].append('return_ahua_controls_restored');save()
        send('control_workbench_toggle','WORKBENCH_INPUT_LOCKED=');choose('ahua_guitoudao',identifier)
        report['world_scope_offset']=raw().rfind('PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY='+identifier)
        skill(['skill_01']);report['checks'].append('new_boss_pre_world_skill_restored')
        report['roundtrip_passed']=True;return 0
    except Exception as error:
        report['error']=type(error).__name__+': '+str(error)
        text=raw();last=text.rfind('[PBZBossControl] enter success=true state=ACTIVE')
        if last>=report['log_offset']and not restoration_result(text[last:])['passed']:
            try:
                menu.click(0,0,2560,1600,'control_exit')
                report['failure_restoration']=restoration_result(wait_for(path,last,lambda t:restoration_result(t,'exit')['passed'],8),'exit')
            except Exception as cleanup:report['cleanup_error']=str(cleanup)
        return 1
    finally:
        save();print(json.dumps({k:v for k,v in report.items()if k!='lines'},ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workflow',type=Path,required=True)
    p.add_argument('--boss',choices=IDS[2:],default='056_youlong')
    group=p.add_mutually_exclusive_group();group.add_argument('--finish-world',action='store_true');group.add_argument('--refusal',action='store_true')
    a=p.parse_args();raise SystemExit(main(a.workflow.resolve(),a.boss,a.finish_world,a.refusal))
