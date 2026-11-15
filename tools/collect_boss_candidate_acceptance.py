"""Collect independent closed-session candidate evidence without editing playable flags."""
import argparse
import json
from pathlib import Path
import re
from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from collect_skill_acceptance import analyze
from collect_practice_stability import proof as stability_proof


def candidate_interval(raw,identifier):
    """分开已清理的落点重试与唯一实际交互装配，拒绝拼接多轮操控。"""
    ready=list(re.finditer(r'PBZ_CONTROL_LIFECYCLE:INTERACTIVE_READY=',raw))
    assert len(ready)==1,'one actual interactive assembly required'
    attempts=list(re.finditer(r'PBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT=(\d+)',raw[:ready[0].start()]))
    assert attempts and [int(a[1])for a in attempts]==list(range(1,len(attempts)+1))
    rejected=[]
    for a,b in zip(attempts,attempts[1:]):
        interval=raw[a.start():b.start()]
        assert 'INITIALIZATION_ATTEMPT_REJECTED='in interval and 'INITIALIZATION_RETRY='in interval
        assert not any(token in interval for token in ('CANDIDATE_LIVE_BINDING=',
            '[PBZBossControl] enter success=true','PBZ_CONTROL_LIFECYCLE:ISSUE_','RESTORE:FAILED='))
        labels=set(re.findall(r'OWNED_DESTROY_VERIFIED=([^|\r\n]+)\|engine_unusable=true',interval))
        assert {'boss','boss_controller','target','target_controller'}<=labels,'rejected layout cleanup required'
        rejected.append({'attempt':int(a[1]),'log_offset':a.start(),'log_end':b.start(),'cleanup_labels':sorted(labels)})
    begin=attempts[-1].start()
    marker='PBZ_CONTROL_LIFECYCLE:CANDIDATE_IDENTITY_READY='+identifier+'|'
    assert raw[begin:ready[0].start()].count(marker)==1,'one final exact candidate identity required'
    return begin,rejected


def collect(session,identifier):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    state_path=ROOT/'runtime'/('official-validation-'+session)/'state.json'
    state=json.loads(state_path.read_text(encoding='utf-8'));work=Path(state['work'])
    assert state.get('restored') and work.name==session
    post_path=work/'postcheck.json';post=json.loads(post_path.read_text(encoding='utf-8'))
    assert post['validation_state']==str(state_path)
    assert post['research_box_empty'] and post['research_loader_removed'] and post['host_registry_unchanged']
    assert not post['formal_files_changed'] and not post['host_config_files_changed']
    deployments=[json.loads(p.read_text(encoding='utf-8')) for p in work.glob('control-lifecycle-deployment-*.json')]
    selected=[d for d in deployments if d.get('boss_candidate')==identifier]
    assert len(selected)==1,'One exact candidate assembly required'
    deployment=selected[0]
    source_paths=[p for p in work.glob('control-lifecycle-deployment-*.json')
        if json.loads(p.read_text(encoding='utf-8'))==deployment]
    assert len(source_paths)==1
    assert not deployment['player_entry'] and deployment['grant']['exe_sha256']==BUILD
    grant_keys=('boss_candidate','identity_receipt_sha256')
    if deployment.get('developer_bundle'):
        from build_boss_developer_bundle import validate
        assert deployment['candidate_identity_grant']==validate(identifier,Path(deployment['developer_bundle']))
        grant_keys+=('ability_metadata_receipt_sha256','developer_bundle_sha256','developer_max_displacement_cm')
        bundle=json.loads((Path(deployment['developer_bundle'])/'manifest.json').read_text(encoding='utf-8'))
        assert deployment['module_source_sha256']['boss_candidate.lua']==bundle['overrides']['Scripts/boss_candidate.lua']
        source_paths += [Path(deployment['developer_bundle'])/name for name in ('manifest.json','boss_candidate.lua')]
    assert deployment['candidate_identity_grant']=={k:deployment['grant'][k] for k in grant_keys}
    raw_path=work/'UE4SS.log';raw=raw_path.read_text(encoding='utf-8',errors='replace')
    begin,rejected=candidate_interval(raw,identifier)
    segment=raw[begin:]
    bindings={}
    for boss,skill,path in re.findall(r'CANDIDATE_LIVE_BINDING=([^|\r\n]+)\|([^|\r\n]+)\|([^\r\n]+)',segment):
        assert boss==identifier and skill not in bindings
        bindings[skill]=path
    assert bindings
    milestone_path=work/'boss-candidate-milestone.json'
    milestone=json.loads(milestone_path.read_text(encoding='utf-8'))
    reused={};reused_sources={}
    if milestone.get('natural_session'):
        from boss_candidate_retry import previous_natural
        reused,reused_sources=previous_natural(milestone['natural_session'],identifier,deployment['module_source_sha256'])
        assert reused_sources==milestone['previous_natural_sources']
        assert all(bindings.get(k)==v['exact_granted_class'] for k,v in reused.items())
    actions_path=work/'player-extra-skill-actions.json'
    actions=json.loads(actions_path.read_text(encoding='utf-8'))
    results=[dict(v,reused_from_session=milestone['natural_session'])for v in reused.values()]
    for action in actions:
        if action['log_offset']<begin:continue
        assert action['state_file']==str(state_path)
        start,end=action['log_offset'],action['log_end']
        assert begin<=start<end<=len(raw)
        interval=raw[start:end]
        assert action['lines'] and all(line in interval for line in action['lines'])
        skill=action['skill'];assert skill in bindings
        result=analyze(interval,skill)
        if deployment.get('developer_bundle'):
            from candidate_effect_scope import local_effect
            result=local_effect(result,interval,deployment['grant']['developer_max_displacement_cm'])
        path=bindings[skill]
        result['exact_granted_class']=path
        result['class_matches_live_binding']=result['ability_class_short']==path.rsplit('.',1)[-1]
        result.update(skill=skill,interrupt=action['interrupt'],log_offset=start,log_end=end)
        results.append(result)
    metadata_path=ROOT/'research/boss-adaptation/dossiers'/(identifier+'.json')
    metadata=json.loads(metadata_path.read_text(encoding='utf-8'))['metadata_identity']
    skills={}
    for skill,path in bindings.items():
        natural=[r for r in results if r['skill']==skill and not r['interrupt'] and r['class_matches_live_binding'] and r['restoration']['passed'] and r['natural_completion']]
        cancelled=[r for r in results if r['skill']==skill and r['interrupt'] and r['class_matches_live_binding'] and r['active_cancel_and_restoration']]
        skills[skill]={'class_path':path,'natural_completion_verified':bool(natural),
            'cancellation_runtime_verified':bool(cancelled),
            'gameplay_verified':any(r['natural_completion']['damage_observed'] for r in natural),
            'movement_runtime_verified':any(r['natural_completion']['movement_observed'] for r in natural)}
    stability=stability_proof(segment,session,metadata['display_name'])
    assert milestone['state_file']==str(state_path) and milestone['candidate']==identifier
    last_enter=segment.rfind('[PBZBossControl] enter success=true state=ACTIVE')
    movement_segment=segment[last_enter:] if last_enter>=0 else ''
    positions=re.findall(r'CONTROLLED_BOSS_POSITION_DELTA=([\d.eE+-]+)',movement_segment)
    control_yaws=[float(v) for v in re.findall(r'CAMERA_CONTROL_YAW=([\d.eE+-]+)',movement_segment)]
    arm_yaws=[float(v) for v in re.findall(r'CAMERA_ARM_YAW=([\d.eE+-]+)',movement_segment)]
    movement_camera={'movement_verified':bool(positions and float(positions[-1])>1),
        'camera_rotation_verified':bool(len(control_yaws)>=2 and len(arm_yaws)>=2
            and abs(control_yaws[-1]-control_yaws[0])>0.1
            and abs(arm_yaws[-1]-arm_yaws[0])>0.1),
        'milestone_passed':milestone['passed'] is True}
    cleanup={name:('OWNED_DESTROY_VERIFIED='+name+'|engine_unusable=true') in segment
             for name in ('boss','boss_controller','target','target_controller','extra_target','extra_target_controller')}
    accepted_skills={k:v for k,v in skills.items() if v['natural_completion_verified'] and v['cancellation_runtime_verified']
                     and(v['gameplay_verified']or v['movement_runtime_verified'])}
    result={'schema_version':1,'session':session,'id':identifier,'target_build_sha256':BUILD,
        'metadata_identity':metadata,'module_source_sha256':deployment['module_source_sha256'],
        'skills':skills,'actions':results,'stability':stability,'cleanup':cleanup,'movement_camera':movement_camera,
        'rejected_layout_attempts':rejected,
        'base_control_accepted':bool(accepted_skills and stability['passed'] and all(cleanup.values())
            and all(movement_camera.values())),
        'accepted_skills':accepted_skills,'playable':False,
        'pending':['Ordinary player Boss switching and world-cycle acceptance are separate gates.'],
        'sources':{**reused_sources,**{str(p.relative_to(ROOT)):sha(p) for p in (raw_path,state_path,post_path,actions_path,milestone_path,*source_paths)}}}
    output=work/'boss-candidate-acceptance.json';write_json(output,result)
    print(json.dumps({'report':str(output),'base_control_accepted':result['base_control_accepted'],
        'accepted_skills':list(accepted_skills),'stability_passed':stability['passed'],'playable':False},ensure_ascii=False))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session');parser.add_argument('identifier')
    args=parser.parse_args();collect(args.session,args.identifier)
