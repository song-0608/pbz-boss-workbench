"""Consolidated original-menu World-cycle trial for the exact experience payload."""
import argparse
import json
from pathlib import Path
import re
import time

import ahua_practice as practice
from boss_adaptation_workflow import ROOT,sha,write_json
from collect_auto_world_reassembly import proof
from control_action_evidence import restoration_result
from four_boss_integration_workflow import modules
import player_experience_workflow as workflow
import build_player_experience_candidate as candidate
from test_player_experience_inputs import main as dispatch
from test_player_skill_batch import wait_for

NAME='player-experience-world-trial.json'


def run(flow,finish=False):
    frozen=workflow.verify(flow);package=Path(frozen['candidate']);manifest=candidate.verify(package)
    owner,state=practice.owned_session();work=Path(state['work']);path=practice.log_path(state)
    assert owner['phase']=='armed'and owner.get('player_entry')and owner.get('workbench')
    assert practice.read(work/'control-lifecycle-deployment.json')['module_source_sha256']==modules(manifest)
    def raw():return path.read_text(encoding='utf-8',errors='replace')
    target=work/NAME
    if finish:
        report=practice.read(target)
        assert report['pre_world_passed']and not report['passed']and not report.get('error')
        assert report['lines']==raw()[report['log_offset']:report['log_end']].splitlines()
        assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',raw()[report['world_scope_offset']:])==['ahua_guitoudao']*2
    else:
        assert not target.exists()and min(state['deadline_unix'],state['control_probe_expires_at'])-time.time()>450
        text=raw();ready=list(re.finditer(r'PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=ahua_guitoudao',text))
        assert ready and re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',text)[-1]=='ahua_guitoudao'
        report=dict(state_file=state['state_file'],workflow=str(flow),candidate=str(package),
            candidate_manifest_sha256=sha(package/'pbz-release.json'),world_scope_offset=ready[-1].start(),
            log_offset=len(text),pre_world_passed=False,passed=False)
    def save():
        text=raw();report.update(log_end=len(text),lines=text[report['log_offset']:].splitlines());write_json(target,report)
    def send(action):
        offset=len(raw());dispatch(flow,action);return offset
    try:
        offset=send('enter')
        tail=wait_for(path,offset,lambda s:'TARGET_CAMERA_LOCK=true|initial'in s,10)
        assert 'enter success=true state=ACTIVE'in tail and 'TARGET_CAMERA_LOCK=true|initial'in tail
        offset=send('shift_cast')
        tail=wait_for(path,offset,lambda s:bool(re.search(r'KEY_SKILL_END=skill_01\|peak=[1-9]\d*\|active=0\|natural=true\|',s)),40,True)
        assert 'slot1 success=true state=ACTIVE'in tail
        assert re.search(r'KEY_SKILL_BEGIN=skill_01\|[^\r\n]+\|active=[1-9]\d*',tail)
        assert re.search(r'KEY_SKILL_END=skill_01\|peak=[1-9]\d*\|active=0\|natural=true\|',tail)
        offset=send('exit');tail=wait_for(path,offset,lambda s:restoration_result(s,'exit')['passed'],10)
        assert restoration_result(tail,'exit')['passed']
        if finish:
            result=proof(raw()[report['world_scope_offset']:]);assert result['passed'],result
            report.update(world_cycle=result,passed=True)
        else:report['pre_world_passed']=True
        return 0
    except Exception as error:
        report['error']=type(error).__name__+': '+str(error)
        current=raw();last=current.rfind('[PBZBossControl] enter success=true state=ACTIVE')
        if last>=report['log_offset']and not restoration_result(current[last:])['passed']:
            try:send('exit')
            except Exception as cleanup:report['cleanup_error']=str(cleanup)
        return 1
    finally:save();print(json.dumps({k:v for k,v in report.items()if k not in ('lines','world_cycle')},ensure_ascii=False))


def collect(session,flow):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    frozen=workflow.verify(flow);package=Path(frozen['candidate']);manifest=candidate.verify(package)
    work=ROOT/'evidence/official-validation'/session;state_path=ROOT/'runtime'/('official-validation-'+session)/'state.json'
    state=practice.read(state_path);post=practice.read(work/'postcheck.json')
    assert state['restored']and post['validation_state']==str(state_path)and Path(state['work'])==work
    assert all(post[k]is True for k in ('research_box_empty','research_loader_removed','host_registry_unchanged'))
    assert not post['formal_files_changed']and not post['host_config_files_changed']
    deployments=list(work.glob('control-lifecycle-deployment-*.json'));assert len(deployments)==1
    assert practice.read(deployments[0])['module_source_sha256']==modules(manifest)
    report=practice.read(work/NAME);assert report['passed']and report['pre_world_passed']and not report.get('error')
    assert report['state_file']==str(state_path)and report['workflow']==str(flow)and report['candidate']==str(package)
    assert report['candidate_manifest_sha256']==sha(package/'pbz-release.json')
    raw_path=work/'UE4SS.log';raw=raw_path.read_text(encoding='utf-8',errors='replace')
    assert report['lines']==raw[report['log_offset']:report['log_end']].splitlines()
    result=proof(raw[report['world_scope_offset']:report['log_end']]);assert result['passed']and result==report['world_cycle']
    menu=practice.read(work/'settings-menu-actions.json')
    confirm=[a for a in menu if a['purpose']=='control_menu_confirm'];continued=[a for a in menu if a['purpose']=='control_menu_continue']
    assert len(confirm)==len(continued)==1 and confirm[0]['at']<continued[0]['at']
    paths=[state_path,work/'postcheck.json',raw_path,work/NAME,work/'settings-menu-actions.json',
           *deployments,flow/'manifest.json',package/'pbz-release.json',ROOT/'tools/player_experience_world.py']
    receipt=dict(schema=1,passed=True,session=session,candidate=str(package),candidate_manifest_sha256=sha(package/'pbz-release.json'),
        world_cycle=result,sources={p.relative_to(ROOT).as_posix():sha(p)for p in paths},complete_mod=False)
    output=work/'player-experience-world-acceptance.json'
    if output.exists():assert practice.read(output)==receipt
    else:write_json(output,receipt)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('begin','finish','collect'))
    p.add_argument('workflow',type=Path);p.add_argument('--session');a=p.parse_args();flow=a.workflow.resolve()
    if a.action=='collect':print(json.dumps(collect(a.session,flow),ensure_ascii=False))
    else:raise SystemExit(run(flow,a.action=='finish'))
