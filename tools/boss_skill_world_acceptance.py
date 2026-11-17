"""A separate, bounded native World cycle for the exact skill candidate."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import boss_skill_player_workflow as workflow
import build_boss_skill_workbench as candidate
from boss_adaptation_workflow import ROOT,BUILD,sha,write_json
from collect_auto_world_reassembly import proof as world_proof
from four_boss_integration_workflow import modules

NAME='boss-skill-world-integration.json'
IDS=('ahua_guitoudao','057_wanjun','073_yanqiansui','056_youlong')
OWNED=('boss','boss_controller','target','target_controller','extra_target','extra_target_controller')


def run(flow,finish=False):
    frozen=workflow.verify(flow);package=Path(frozen['candidate']);manifest=candidate.verify(package)
    sys.path.insert(0,str(flow))
    import ahua_practice as practice
    import research_game_menu as menu
    from test_player_skill_batch import wait_for
    owner,state=practice.owned_session();work=Path(state['work']);path=practice.log_path(state)
    assert owner['phase']=='armed' and owner.get('player_entry') and owner.get('workbench')
    assert practice.read(work/'control-lifecycle-deployment.json')['module_source_sha256']==modules(manifest)
    def raw():return path.read_text(encoding='utf-8',errors='replace')
    target=work/NAME
    if finish:
        report=practice.read(target)
        assert report['pre_world_passed'] and not report['passed'] and not report.get('error')
        assert report['lines']==raw()[report['log_offset']:report['log_end']].splitlines()
    else:
        assert not target.exists()
        assert min(state['deadline_unix'],state['control_probe_expires_at'])-time.time()>450
        report=dict(state_file=state['state_file'],workflow=str(flow),candidate=str(package),
            candidate_manifest_sha256=sha(package/'pbz-release.json'),log_offset=len(raw()),
            pre_world_passed=False,passed=False)
    def save():
        text=raw();report.update(log_end=len(text),lines=text[report['log_offset']:].splitlines());write_json(target,report)
    def send(action,token,seconds=10):
        off=len(raw());menu.click(0,0,2560,1600,action)
        tail=wait_for(path,off,lambda t:token in t,seconds,True)
        assert token in tail,'Missing '+token
        return tail
    def choose(current,wanted):
        send('control_workbench_toggle','WORKBENCH_INPUT_LOCKED=')
        step=IDS.index(wanted)-IDS.index(current)
        direction='down' if step>0 else 'up'
        for _ in range(abs(step)):send('control_workbench_'+direction,'workbench_'+direction+' success=true')
        tail=send('control_workbench_confirm','PLAYER_ENTRY_READY='+wanted,95)
        assert 'WORKBENCH_BOSS_SELECTED='+wanted in tail and 'WORKBENCH_INPUT_RESTORED=true' in tail
        assert all('OWNED_DESTROY_VERIFIED='+n+'|engine_unusable=true' in tail for n in OWNED)
        time.sleep(2)
    def skill():
        job=subprocess.run([sys.executable,'-X','utf8',str(flow/'test_player_skill_batch.py'),'skill_01'],
            cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=100,
            creationflags=subprocess.CREATE_NO_WINDOW)
        print(job.stdout,flush=True);assert job.returncode==0,job.stderr or job.stdout
    try:
        if finish:
            assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',raw()[report['world_scope_offset']:])==[IDS[-1],IDS[-1]]
            skill();report['world_action_end']=len(raw())
            proof=world_proof(raw()[report['world_scope_offset']:report['world_action_end']])
            assert proof['passed'],proof
            report['world_cycle']=proof
            choose(IDS[-1],IDS[0]);report['passed']=True
        else:
            assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',raw())[-1]==IDS[0]
            choose(IDS[0],IDS[-1])
            report['world_scope_offset']=raw().rfind('PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY='+IDS[-1])
            skill();report['pre_world_passed']=True
        return 0
    except Exception as error:
        report['error']=type(error).__name__+': '+str(error);return 1
    finally:
        save();print(json.dumps({k:v for k,v in report.items() if k not in ('lines','world_cycle')},ensure_ascii=False),flush=True)


def collect(session,flow):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    frozen=workflow.verify(flow);package=Path(frozen['candidate']);manifest=candidate.verify(package)
    work=ROOT/'evidence/official-validation'/session;state_path=ROOT/'runtime'/('official-validation-'+session)/'state.json'
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    state=read(state_path);post=read(work/'postcheck.json')
    assert state['restored'] and post['validation_state']==str(state_path) and Path(state['work'])==work
    assert all(post[k] is True for k in ('validation_restored','research_box_empty','research_loader_removed','host_registry_unchanged'))
    assert not any(post[k] for k in ('formal_files_changed','host_config_files_changed','remaining_games'))
    deployments=list(work.glob('control-lifecycle-deployment-*.json'));assert len(deployments)==1
    deployed=read(deployments[0]);assert deployed['player_entry'] and not deployed.get('boss_candidate')
    assert deployed['grant']['exe_sha256']==BUILD and deployed['module_source_sha256']==modules(manifest)
    report=read(work/NAME);assert report['passed'] and report['pre_world_passed'] and not report.get('error')
    assert report['state_file']==str(state_path) and report['workflow']==str(flow) and report['candidate']==str(package)
    assert report['candidate_manifest_sha256']==sha(package/'pbz-release.json')
    raw=(work/'UE4SS.log').read_text(encoding='utf-8',errors='replace')
    a,b=report['log_offset'],report['log_end'];assert 0<=a<b<=len(raw)
    assert report['lines']==raw[a:b].splitlines()
    assert re.findall(r'WORKBENCH_BOSS_SELECTED=([^\r\n]+)',raw[a:b])==[IDS[-1],IDS[0]]
    assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',raw[a:b])==[IDS[-1],IDS[-1],IDS[0]]
    proof=world_proof(raw[report['world_scope_offset']:report['world_action_end']])
    assert proof['passed'] and proof==report['world_cycle']
    menu=read(work/'settings-menu-actions.json')
    confirm=[r for r in menu if r['purpose']=='control_menu_confirm']
    continued=[r for r in menu if r['purpose']=='control_menu_continue']
    assert len(confirm)==len(continued)==1 and confirm[0]['at']<continued[0]['at']
    paths=[state_path,work/'postcheck.json',work/'UE4SS.log',work/NAME,work/'settings-menu-actions.json',
        deployments[0],flow/'manifest.json',package/'pbz-release.json',ROOT/'tools/boss_skill_world_acceptance.py']
    return dict(passed=True,session=session,world_cycle=proof,candidate=str(package),
        sources={p.relative_to(ROOT).as_posix():sha(p) for p in paths})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('run','finish-world','collect'))
    parser.add_argument('--workflow',type=Path,required=True);parser.add_argument('--session');args=parser.parse_args()
    flow=args.workflow.resolve()
    if args.action!='collect':raise SystemExit(run(flow,args.action=='finish-world'))
    print(json.dumps(collect(args.session,flow),ensure_ascii=False))
