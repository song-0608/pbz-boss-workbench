"""Exercise new ordinary keys, four-role switching and native World recovery."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from boss_adaptation_workflow import ROOT,BUILD,sha,write_json
import boss_skill_player_workflow as workflow
import build_boss_skill_workbench as candidate
from candidate_effect_scope import local_effect
from collect_multi_boss_switching import exact_role_proof,movement_camera_proof
from collect_auto_world_reassembly import proof as world_proof
from control_action_evidence import restoration_result
from four_boss_integration_workflow import modules

IDS=('ahua_guitoudao','057_wanjun','073_yanqiansui','056_youlong')
EXTRA=('skill_06','skill_08','skill_07','teleport_left')
OWNED=('boss','boss_controller','target','target_controller','extra_target','extra_target_controller')
NAME='boss-skill-player-integration.json'


def run(flow,finish_world=False):
    frozen=workflow.verify(flow)
    sys.path.insert(0,str(flow))
    import ahua_practice as practice
    import research_game_menu as menu
    from test_player_skill_batch import wait_for
    owner,state=practice.owned_session();work=Path(state['work']);path=practice.log_path(state)
    assert owner['phase']=='armed' and owner.get('player_entry') and owner.get('workbench')
    package=Path(frozen['candidate']);manifest=candidate.verify(package)
    deployment=practice.read(work/'control-lifecycle-deployment.json')
    assert deployment['module_source_sha256']==modules(manifest)
    def raw():return path.read_text(encoding='utf-8',errors='replace')
    target=work/NAME
    if finish_world:
        report=practice.read(target)
        assert report['roundtrip_passed'] and not report['world_finished'] and not report.get('error')
        assert report['state_file']==state['state_file'] and report['workflow']==str(flow)
        assert report['lines']==raw()[report['log_offset']:report['log_end']].splitlines()
    else:
        assert not target.exists(),'Preserve every integration attempt'
        assert min(state['deadline_unix'],state['control_probe_expires_at'])-time.time()>550
        report=dict(state_file=state['state_file'],workflow=str(flow),candidate=str(package),
            candidate_manifest_sha256=sha(package/'pbz-release.json'),
            log_offset=len(raw()),checkpoints=[],roundtrip_passed=False,world_finished=False)
    def save():
        text=raw();report.update(log_end=len(text),lines=text[report['log_offset']:].splitlines())
        write_json(target,report)
    def send(action,token,seconds=10):
        start=len(raw());menu.click(0,0,2560,1600,action)
        tail=wait_for(path,start,lambda text:token in text,seconds,True)
        assert token in tail,'Missing '+token
        return start,tail
    def skill(names,interrupt=False):
        job=subprocess.run([sys.executable,'-X','utf8',str(flow/'test_player_skill_batch.py'),*names,
            *(['--interrupt'] if interrupt else [])],cwd=ROOT,capture_output=True,text=True,
            encoding='utf-8',errors='replace',timeout=230,creationflags=subprocess.CREATE_NO_WINDOW)
        print(job.stdout,flush=True);assert job.returncode==0,job.stderr or job.stdout
    def open_active():
        start,_=send('control_workbench_toggle','WORKBENCH_INPUT_LOCKED=')
        assert restoration_result(wait_for(path,start,lambda t:restoration_result(t,'auto_exit')['passed'],10),'auto_exit')['passed']
    def choose(current,wanted):
        steps=IDS.index(wanted)-IDS.index(current)
        for _ in range(abs(steps)):
            direction='down' if steps>0 else 'up'
            send('control_workbench_'+direction,'workbench_'+direction+' success=true')
        start,tail=send('control_workbench_confirm','PLAYER_ENTRY_READY='+wanted,95)
        assert 'WORKBENCH_BOSS_SELECTED='+wanted in tail and 'WORKBENCH_INPUT_RESTORED=true' in tail
        assert all('OWNED_DESTROY_VERIFIED='+n+'|engine_unusable=true' in tail for n in OWNED)
        time.sleep(2)
        return start
    try:
        save()
        if finish_world:
            assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',raw()[report['world_scope_offset']:])==[IDS[-1],IDS[-1]]
            skill(['skill_01']);report['world_action_end']=len(raw())
            proof=world_proof(raw()[report['world_scope_offset']:report['world_action_end']])
            assert proof['passed'],'Native World recovery proof incomplete'
            report['world_proof']=proof
            send('control_workbench_toggle','WORKBENCH_INPUT_LOCKED=');choose(IDS[-1],IDS[0])
            report['world_finished']=True
            return 0
        assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',raw())[-1]==IDS[0]
        send('control_enter','enter success=true state=ACTIVE');open_active()
        current=IDS[0]
        for wanted in IDS[1:]:
            if current!=IDS[0]:send('control_workbench_toggle','WORKBENCH_INPUT_LOCKED=')
            start=choose(current,wanted)
            skill(list(EXTRA));skill(list(EXTRA),True)
            report['checkpoints'].append(dict(boss=wanted,log_offset=start,log_end=len(raw())))
            current=wanted;save()
        start,_=send('control_enter','enter success=true state=ACTIVE')
        wait_for(path,start,lambda t:'CAMERA_ARM_YAW=' in t,5)
        menu.click(0,0,2560,1600,'control_look');menu.click(0,0,2560,1600,'control_backward')
        wait_for(path,start,lambda t:t.count('CAMERA_ARM_YAW=')>=3,9)
        open_active();motion=movement_camera_proof(raw()[start:]);assert motion['passed']
        report.update(movement_log_offset=start,movement_log_end=len(raw()),movement_camera=motion)
        choose(current,IDS[0]);skill(['skill_01']);skill(['skill_08'],True)
        send('control_workbench_toggle','WORKBENCH_INPUT_LOCKED=');choose(IDS[0],IDS[-1])
        report['world_scope_offset']=raw().rfind('PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY='+IDS[-1])
        skill(['skill_01']);report['roundtrip_passed']=True
        return 0
    except Exception as error:
        report['error']=type(error).__name__+': '+str(error)
        text=raw();start=text.rfind('[PBZBossControl] enter success=true state=ACTIVE')
        if start>=report['log_offset'] and not restoration_result(text[start:])['passed']:
            try:
                menu.click(0,0,2560,1600,'control_exit')
                report['failure_restoration']=restoration_result(wait_for(path,start,lambda t:restoration_result(t,'exit')['passed'],8),'exit')
            except Exception as cleanup:report['cleanup_error']=str(cleanup)
        return 1
    finally:
        save();print(json.dumps({k:v for k,v in report.items() if k not in ('lines','world_proof')},ensure_ascii=False),flush=True)


def collect(session,flow):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    frozen=workflow.verify(flow);package=Path(frozen['candidate']);manifest=candidate.verify(package)
    work=ROOT/'evidence/official-validation'/session;state_path=ROOT/'runtime'/('official-validation-'+session)/'state.json'
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    state=read(state_path);post=read(work/'postcheck.json')
    assert state['restored'] and Path(state['work'])==work and post['validation_state']==str(state_path)
    assert all(post[k] is True for k in ('validation_restored','research_box_empty','research_loader_removed','host_registry_unchanged'))
    assert not any(post[k] for k in ('formal_files_changed','host_config_files_changed','remaining_games'))
    deployments=list(work.glob('control-lifecycle-deployment-*.json'));assert len(deployments)==1
    deployment=read(deployments[0]);assert deployment['player_entry'] and not deployment.get('boss_candidate')
    assert deployment['grant']['exe_sha256']==BUILD and deployment['module_source_sha256']==modules(manifest)
    report=read(work/NAME);assert report['roundtrip_passed'] and report['world_finished'] and not report.get('error')
    assert report['state_file']==str(state_path) and report['workflow']==str(flow) and report['candidate']==str(package)
    assert report['candidate_manifest_sha256']==sha(package/'pbz-release.json')
    raw=(work/'UE4SS.log').read_text(encoding='utf-8',errors='replace')
    start,end=report['log_offset'],report['log_end'];assert 0<=start<end<=len(raw)
    segment=raw[start:end];assert report['lines']==segment.splitlines()
    assert not any(t in segment for t in ('state=FAULTED','ISSUE_','[Lua::execute_file]','HUD_UNAVAILABLE=','PBZ_CONTROL_RESTORE:FAILED='))
    assert re.findall(r'WORKBENCH_BOSS_SELECTED=([^\r\n]+)',segment)==[IDS[1],IDS[2],IDS[3],IDS[0],IDS[3],IDS[0]]
    assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',segment)==[IDS[1],IDS[2],IDS[3],IDS[0],IDS[3],IDS[3],IDS[0]]
    campaign=read(ROOT/manifest['skill_session']);by_id={r['id']:r for r in campaign['bosses']}
    actions=read(work/'player-extra-skill-actions.json');proofs=[]
    assert [r['boss'] for r in report['checkpoints']]==list(IDS[1:])
    for checkpoint in report['checkpoints']:
        identifier=checkpoint['boss'];a,b=checkpoint['log_offset'],checkpoint['log_end']
        assert start<=a<b<=end
        tail=raw[a:b];assert 'WORKBENCH_BOSS_SELECTED='+identifier in tail and 'WORKBENCH_INPUT_RESTORED=true' in tail
        assert all('OWNED_DESTROY_VERIFIED='+n+'|engine_unusable=true' in tail for n in OWNED)
        bundle=read(Path(by_id[identifier]['bundle'])/'manifest.json')
        expected={r['player_slot']:r['class_path'] for r in bundle['skill_expansion']['actions']}
        seen=set()
        for action in actions:
            x,y=action['log_offset'],action['log_end']
            if y<=a or x>=b:continue
            assert a<=x<y<=b and action['state_file']==str(state_path)
            assert action['lines']==raw[x:y].splitlines()
            skill=action['skill'];key=(skill,action['interrupt'])
            assert skill in expected and key not in seen;seen.add(key)
            proof=local_effect(exact_role_proof(raw,action,identifier,expected[skill]),raw[x:y])
            assert proof['active_cancel_and_restoration'] if action['interrupt'] else proof['natural_completion'] and proof['restoration']['passed']
            proofs.append(dict(boss=identifier,skill=skill,interrupt=action['interrupt'],proof=proof))
        assert seen=={(s,i) for s in EXTRA for i in (False,True)}
    motion=movement_camera_proof(raw[report['movement_log_offset']:report['movement_log_end']])
    assert motion==report['movement_camera'] and motion['passed']
    world=world_proof(raw[report['world_scope_offset']:report['world_action_end']])
    assert world==report['world_proof'] and world['passed']
    paths=[state_path,work/'postcheck.json',work/'UE4SS.log',work/NAME,work/'player-extra-skill-actions.json',
           deployments[0],flow/'manifest.json',package/'pbz-release.json',ROOT/'tools/boss_skill_player_acceptance.py']
    return dict(schema=1,session=session,passed=True,candidate=str(package),
        candidate_manifest_sha256=sha(package/'pbz-release.json'),module_source_sha256=modules(manifest),
        ordinary_extra_actions=proofs,movement_camera=motion,world_cycle=world,
        formal_postcheck_passed=True,sources={p.relative_to(ROOT).as_posix():sha(p) for p in paths})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('run','finish-world','collect','verify'))
    parser.add_argument('--workflow',type=Path,required=True);parser.add_argument('--session');args=parser.parse_args()
    flow=args.workflow.resolve()
    if args.action in ('run','finish-world'):raise SystemExit(run(flow,args.action=='finish-world'))
    result=collect(args.session,flow);path=ROOT/'evidence/official-validation'/args.session/'boss-skill-player-acceptance.json'
    if args.action=='verify':assert json.loads(path.read_text(encoding='utf-8'))==result
    else:
        assert not path.exists(),'Preserve collected receipt';write_json(path,result)
    print(json.dumps(dict(report=str(path),passed=result['passed'],ordinary_extra_actions=len(result['ordinary_extra_actions']))))
