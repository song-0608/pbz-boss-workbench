"""Replay closed experience input receipts; partial checks never publish a release."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, sha, write_json
from collect_boss_metadata_jobs import repository_path
from control_action_evidence import restoration_result
from four_boss_integration_workflow import modules
from mod_installation import MANIFEST
import player_experience_workflow as workflow
import build_player_experience_candidate as candidate

IDS=('ahua_guitoudao','057_wanjun','073_yanqiansui','056_youlong')
BAD=('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_','PBZ_CONTROL_RESTORE:FAILED=',
     '[Lua::execute_file]','HUD_UNAVAILABLE=')


def ordered(text,patterns):
    cursor=0
    for pattern in patterns:
        match=re.search(pattern,text[cursor:])
        if not match:return False
        cursor+=match.end()
    return True


def analyze(raw,dispatches):
    """Confine each observed result to its own input window, never the next input."""
    assert dispatches and all(type(d['log_offset'])is int for d in dispatches)
    offsets=[d['log_offset']for d in dispatches]
    assert offsets==sorted(set(offsets)) and 0<=offsets[0]<offsets[-1]<len(raw)
    trials=[]
    for index,dispatch in enumerate(dispatches):
        start=dispatch['log_offset'];end=offsets[index+1]if index+1<len(offsets)else len(raw)
        interval=raw[start:end]
        ready=re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',raw[:start])
        assert ready and ready[-1]in IDS,'Actual current player-entry identity required'
        row=dict(action=dispatch['action'],boss=ready[-1],log_offset=start,log_end=end,passed=False)
        if row['action']=='enter':
            row['passed']=ordered(interval,(r'\[PBZBossControl\] enter success=true state=ACTIVE',
                r'TARGET_CAMERA_LOCK=true\|initial'))
        elif row['action']=='shift_cast':
            row['passed']=ordered(interval,(r'\[PBZBossControl\] slot1 success=true state=ACTIVE',
                r'KEY_SKILL_BEGIN=skill_01\|[^\r\n]+\|active=[1-9]\d*',
                r'KEY_SKILL_END=skill_01\|peak=[1-9]\d*\|active=0\|natural=true\|'))
            finish=re.search(r'KEY_SKILL_END=skill_01\|[^\r\n]+',interval)
            row['native_finish']=finish[0]if finish else None
        elif row['action']=='exit':
            row['restoration']=restoration_result(interval,'exit');row['passed']=row['restoration']['passed']
        elif row['action']=='lock':
            lock=re.findall(r'TARGET_CAMERA_LOCK=(true|false)\|manual',interval)
            row['enabled']=lock[0]=='true'if len(lock)==1 else None
            row['passed']=len(lock)==1 and 'lock_target success=true state=ACTIVE'in interval
        elif row['action']=='cycle_target':
            requested=re.search(r'target_request success=true state=ACTIVE reason=requested; awaiting readback: ([^\r\n]+)',interval)
            verified=re.search(r'target verified: ([^\r\n]+)',interval)
            row['passed']=bool(requested and verified and requested.end()<verified.start()and requested[1]==verified[1])
        elif row['action']=='workbench':
            entered=raw[:start].rfind('[PBZBossControl] enter success=true state=ACTIVE')
            exited=max(raw[:start].rfind('[PBZBossControl] '+x+' success=true')for x in ('exit','auto_exit','menu_exit'))
            active=entered>exited
            row['active_takeover']=active
            row['restoration']=restoration_result(interval,'auto_exit','open Boss workbench')if active else None
            row['passed']='WORKBENCH_INPUT_LOCKED='in interval and (not active or row['restoration']['passed'])
        elif row['action']in ('up','down'):
            row['passed']='workbench_'+row['action']+' success=true'in interval
        elif row['action']=='confirm':
            selected=re.findall(r'WORKBENCH_BOSS_SELECTED=([^\r\n]+)',interval)
            row['selected_boss']=selected[0]if len(selected)==1 else None
            row['passed']=len(selected)==1 and selected[0]in IDS and ordered(interval,(
                r'WORKBENCH_INPUT_RESTORED=true','WORKBENCH_BOSS_SELECTED='+re.escape(selected[0]),
                'PLAYER_ENTRY_READY='+re.escape(selected[0])))
        elif row['action']=='close':
            row['passed']='WORKBENCH_INPUT_RESTORED=true'in interval
        row['passed']=bool(row['passed']and not any(token in interval for token in BAD))
        trials.append(row)
    roles={identifier:{name:any(t['boss']==identifier and t['action']==action and t['passed']for t in trials)
        for name,action in (('initial_lock','enter'),('shift_movement_native_cast','shift_cast'),('f10_restoration','exit'))}
        for identifier in IDS}
    # Ahua's first cast was restored by opening the workbench; keep that distinction explicit.
    roles[IDS[0]]['workbench_restoration']=any(t['boss']==IDS[0]and t['action']=='workbench'
        and t.get('active_takeover')and t['passed']for t in trials)
    feature_checks=dict(four_role_shift_casts=all(r['shift_movement_native_cast']for r in roles.values()),
        four_role_initial_lock=all(r['initial_lock']for r in roles.values()),
        four_role_f10_restoration=all(r['f10_restoration']for r in roles.values()),
        manual_lock_off_on=[t.get('enabled')for t in trials if t['action']=='lock'and t['passed']]==[False,True],
        target_switch=any(t['action']=='cycle_target'and t['passed']for t in trials),
        workbench_restores_active_takeover=roles[IDS[0]]['workbench_restoration'],
        selection_roundtrip=[t.get('selected_boss')for t in trials if t['action']=='confirm'and t['passed']]
            ==list(IDS[1:])+[IDS[0]],all_dispatch_results=all(t['passed']for t in trials))
    return dict(trials=trials,roles=roles,feature_checks=feature_checks,
        feature_trial_passed=all(feature_checks.values()),world_reload_verified=False,
        focus_loss_runtime_verified=False,runtime_acceptance_current=False,complete_mod=False)


def collect(session,flow,root=ROOT):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    frozen=workflow.verify(flow,root);package=Path(frozen['candidate']);manifest=candidate.verify(package,root)
    state_path=repository_path(root,'runtime/official-validation-'+session+'/state.json')
    state=json.loads(state_path.read_bytes());work=repository_path(root,'evidence/official-validation/'+session)
    assert state.get('restored')is True and Path(state['work']).resolve()==work.resolve()
    post=work/'postcheck.json';closed=json.loads(post.read_bytes())
    assert closed['validation_state']==str(state_path)
    assert all(closed[k]is True for k in ('research_box_empty','research_loader_removed','host_registry_unchanged'))
    assert not closed['formal_files_changed']and not closed['host_config_files_changed']
    deployment_paths=list(work.glob('control-lifecycle-deployment-*.json'));assert len(deployment_paths)==1
    deployment=json.loads(deployment_paths[0].read_bytes())
    assert deployment['player_entry']and not deployment['boss_candidate']
    assert Path(deployment['mod_source_directory']).resolve()==package/'PBZBossControl'
    assert deployment['module_source_sha256']==modules(manifest)
    raw_path=work/'UE4SS.log';raw=raw_path.read_text(encoding='utf-8',errors='replace')
    pairs=[];sources=[state_path,post,raw_path,*deployment_paths,package/MANIFEST,flow/'manifest.json']
    for path in sorted(work.glob('experience-dispatch-*.json')):
        data=json.loads(path.read_bytes())
        assert data['state_file']==str(state_path)and Path(data['workflow']).resolve()==flow
        assert data['candidate_manifest_sha256']==sha(package/MANIFEST)
        assert data['input_sent']is True and not data.get('error')and not data['gameplay_verified']
        assert datetime.fromisoformat(data['dispatch_at']).timestamp()<data['gate_expires_at']
        assert data['gate_expires_at']-10<deployment['grant']['expires_at']-20
        gate=data.copy()
        for key in ('dispatch_at','native_dispatch'):gate.pop(key,None)
        gate['input_sent']=False
        matching=[]
        for gate_path in work.glob('experience-input-*.json'):
            if json.loads(gate_path.read_bytes())==gate:matching.append(gate_path)
        assert len(matching)==1,'Exact independent pre-dispatch gate receipt required'
        pairs.append(data);sources.extend([path,*matching])
    pairs.sort(key=lambda d:d['log_offset']);result=analyze(raw,pairs)
    # Preserve the failed early-read runner and verify the continuation against the raw log.
    attempts=[]
    for name in ('experience-role-roundtrip.json','experience-role-continuation.json','experience-world-cycle.json'):
        path=work/name
        if not path.exists():continue
        data=json.loads(path.read_bytes());assert data['state_file']==str(state_path)
        if 'lines'in data:
            assert data['lines']==raw[data['log_offset']:data['log_end']].splitlines()
        attempts.append(dict(file=path.relative_to(root).as_posix(),passed=data['passed'],error=data.get('error')))
        sources.append(path)
    result.update(schema=1,session=session,candidate=str(package),candidate_manifest_sha256=sha(package/MANIFEST),
        workflow=str(flow),module_source_sha256=modules(manifest),attempt_history=attempts,
        pending=['Original-menu World reload and fresh takeover','Focus-loss runtime restoration'],
        new_playable_bosses=0,installed=False,sources={p.relative_to(root).as_posix():sha(p)for p in sources})
    result['collector_sha256']=sha(root/'tools/collect_player_experience.py')
    target=work/('player-experience-features-'+result['collector_sha256'][:16]+'.json')
    if target.exists():assert json.loads(target.read_bytes())==result,'Preserve immutable collected feature attempt'
    else:write_json(target,result)
    return target,result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('session');p.add_argument('workflow',type=Path)
    a=p.parse_args();path,result=collect(a.session,a.workflow.resolve())
    print(json.dumps(dict(report=str(path),feature_trial_passed=result['feature_trial_passed'],
        feature_checks=result['feature_checks'],runtime_acceptance_current=False),ensure_ascii=False))
