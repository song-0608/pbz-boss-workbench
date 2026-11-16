"""Fresh YouLong original-menu World lifecycle only; do not repeat accepted ordinary skills."""
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
from four_boss_integration_workflow import verify as verify_workflow
from four_boss_ordinary_reuse import verify
from control_action_evidence import restoration_result

ID='056_youlong'


def main(workflow,finish=False):
    verify_workflow(workflow);owner,state=practice.owned_session();work=Path(state['work']);path=practice.log_path(state)
    deployment=practice.read(work/'control-lifecycle-deployment.json')
    assert owner['phase']=='armed'and owner.get('player_entry')and owner.get('workbench')
    assert deployment['player_entry']and not deployment['boss_candidate']and deployment['boss_id']=='ahua_guitoudao'
    _,sources=verify(deployment['module_source_sha256']);target=work/'youlong-world-missing.json'
    def raw():return path.read_text(encoding='utf-8',errors='replace')
    if finish:
        report=practice.read(target)
        assert report['ready']and not report['passed']and not report.get('error')
        assert report['state_file']==state['state_file']and report['workflow']==str(workflow)and report['previous_ordinary_sources']==sources
        assert report['lines']==raw()[report['log_offset']:report['log_end']].splitlines()
        assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',raw()[report['world_scope_offset']:])==[ID,ID]
    else:
        assert not target.exists()and min(state['deadline_unix'],state['control_probe_expires_at'])-time.time()>210
        assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',raw())[-1]=='ahua_guitoudao'
        report={'state_file':state['state_file'],'workflow':str(workflow),'previous_ordinary_sources':sources,
            'log_offset':len(raw()),'ready':False,'passed':False}
    def save():
        text=raw();report.update(log_end=len(text),lines=text[report['log_offset']:].splitlines())
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def send(action,token,seconds=10):
        off=len(raw());menu.click(0,0,2560,1600,action)
        tail=wait_for(path,off,lambda t:token in t,seconds,True);assert token in tail,'Missing '+token
        return off,tail
    def skill():
        r=subprocess.run([sys.executable,str(workflow/'test_player_skill_batch.py'),'skill_01'],cwd=practice.ROOT,
            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
        print(r.stdout,flush=True);assert r.returncode==0,r.stdout+r.stderr
    def choose(wanted,down):
        send('control_workbench_toggle','WORKBENCH_INPUT_LOCKED=')
        for _ in range(3):send('control_workbench_down'if down else'control_workbench_up',
            'workbench_down success=true'if down else'workbench_up success=true')
        _,tail=send('control_workbench_confirm','PLAYER_ENTRY_READY='+wanted,95)
        assert 'WORKBENCH_BOSS_SELECTED='+wanted in tail and 'WORKBENCH_INPUT_RESTORED=true'in tail
        assert all('OWNED_DESTROY_VERIFIED='+n+'|engine_unusable=true'in tail for n in
            ('boss','boss_controller','target','target_controller','extra_target','extra_target_controller'))
        time.sleep(2)
    try:
        save()
        if finish:
            skill()
            from collect_auto_world_reassembly import witness
            witness();stamp=work/'youlong-world-missing-witness.json';assert not stamp.exists()
            stamp.write_bytes((work/'auto-world-witness.json').read_bytes())
            report['witness_log_end']=practice.read(stamp)['log_end']
            choose('ahua_guitoudao',False);report['passed']=True;return 0
        choose(ID,True)
        report['world_scope_offset']=raw().rfind('PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY='+ID)
        skill();report['ready']=True;return 0
    except Exception as error:
        report['error']=type(error).__name__+': '+str(error)
        text=raw();last=text.rfind('[PBZBossControl] enter success=true state=ACTIVE')
        if last>=report['log_offset']and not restoration_result(text[last:])['passed']:
            try:
                menu.click(0,0,2560,1600,'control_exit')
                report['failure_restoration']=restoration_result(wait_for(path,last,lambda t:restoration_result(t,'exit')['passed'],8),'exit')
            except Exception as cleanup:report['cleanup_error']=str(cleanup)
        return 1
    finally:save();print(json.dumps({k:v for k,v in report.items()if k!='lines'},ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workflow',type=Path,required=True);p.add_argument('--finish-world',action='store_true');a=p.parse_args()
    raise SystemExit(main(a.workflow.resolve(),a.finish_world))
