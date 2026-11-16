"""Independently collect closed ordinary integration; never publish a candidate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from boss_adaptation_workflow import ROOT,BUILD,sha,write_json
from four_boss_integration_workflow import verify,verify_current,CANDIDATE,modules
from mod_installation import validate_package
from collect_multi_boss_switching import exact_role_proof,movement_camera_proof
from collect_auto_world_reassembly import proof as world_proof
from candidate_effect_scope import local_effect
from control_action_evidence import restoration_result

OWNED={'boss','boss_controller','target','target_controller','extra_target','extra_target_controller'}


def refusal_proof(raw,action,state_file):
    assert action['state_file']==state_file and action.get('refusal_passed')and not action.get('error')
    assert action['checks']==['active_ahua_open_restores_player','refusal_preserves_current_ahua_and_controls']
    a,b=action['log_offset'],action['log_end'];x=action['refusal_log_offset']
    assert 0<=a<x<b<=len(raw)and action['lines']==raw[a:b].splitlines()
    segment=raw[a:b]
    assert segment.count('WORKBENCH_SELECTION_REJECTED=073_yanqiansui|')==1
    assert not any(t in segment for t in ('SPAWN_ATTEMPT=','OWNED_DESTROY_VERIFIED=','WORKBENCH_BOSS_SELECTED=','PLAYER_ENTRY_READY='))
    assert segment.count('WORKBENCH_INPUT_LOCKED=')==segment.count('WORKBENCH_INPUT_RESTORED=true')==2
    assert restoration_result(segment[:x-a],'auto_exit')['passed']
    return {'passed':True,'current_assembly_preserved':True,'input_restored':True,'log_offset':a,'log_end':b}


def collect(session,workflow,identifier,refusal=False):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    manifest=verify(workflow)
    state_path=ROOT/'runtime'/('official-validation-'+session)/'state.json'
    state=json.loads(state_path.read_text(encoding='utf-8'));work=ROOT/'evidence/official-validation'/session
    assert state['restored']and Path(state['work']).resolve()==work.resolve()
    def read(name):return json.loads((work/name).read_text(encoding='utf-8'))
    post=read('postcheck.json');assert post['validation_state']==str(state_path)
    assert all(post[k]for k in ('research_box_empty','research_loader_removed','host_registry_unchanged'))
    assert not any(post[k]for k in ('formal_files_changed','host_config_files_changed','remaining_games'))
    deployments=list(work.glob('control-lifecycle-deployment-*.json'));assert len(deployments)==1
    deployment=read(deployments[0].name)
    assert deployment['player_entry']and deployment['boss_id']=='ahua_guitoudao'
    assert not deployment['boss_candidate']and not deployment['scene_transition_trial']
    assert deployment['grant']['exe_sha256']==BUILD
    old,sources=verify_current(deployment['module_source_sha256'])
    raw=(work/'UE4SS.log').read_text(encoding='utf-8',errors='replace')
    action_name='four-boss-refusal.json'if refusal else identifier+'-ordinary-integration.json'
    action=read(action_name)
    assert action['workflow']==str(workflow)and action['previous_ordinary_sources']==sources
    from build_ahua_acceptance_matrix import capabilities
    classes={'ahua_guitoudao':{r['skill']:r['class_path']for r in capabilities()},
        '073_yanqiansui':{r['skill']:r['exact_granted_class']for r in old}}
    candidate=validate_package(ROOT/'runtime/release-candidates'/CANDIDATE)
    receipt=json.loads((ROOT/candidate['youlong_attempt_receipt']).read_text(encoding='utf-8'))
    classes['056_youlong']=receipt['bindings']
    paths=[state_path,work/'postcheck.json',work/'UE4SS.log',work/action_name,work/'player-extra-skill-actions.json',*deployments]
    a,b=action['log_offset'],action['log_end'];segment=raw[a:b]
    assert 0<=a<b<=len(raw)and action['state_file']==str(state_path)and action['lines']==segment.splitlines()
    if refusal:
        behavior=refusal_proof(raw,action,str(state_path));expected=[('ahua_guitoudao','skill_01',False)]
    else:
        expected_checks=['active_ahua_open_restores_player','new_boss_selected_with_cleanup',
            'four_ordinary_natural_and_cancel'if identifier=='056_youlong'else'eight_ordinary_skills_reparsed_from_closed_evidence',
            'new_boss_movement_camera_restored','return_ahua_controls_restored','new_boss_pre_world_skill_restored',
            'new_world_skill_restored','final_return_ahua']
        assert action['checks']==expected_checks and action['roundtrip_passed']and action['world_finished']and not action.get('error')
        selected=re.findall(r'WORKBENCH_BOSS_SELECTED=([^\r\n]+)',segment)
        assert selected==[identifier,'ahua_guitoudao',identifier,'ahua_guitoudao']
        ready=list(re.finditer(r'PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=([^\r\n]+)',segment))
        assert [r[1]for r in ready]==[identifier,'ahua_guitoudao',identifier,identifier,'ahua_guitoudao']
        assert action['world_scope_offset']==a+ready[2].start()
        assert segment.count('WORKBENCH_INPUT_LOCKED=')==segment.count('WORKBENCH_INPUT_RESTORED=true')==4
        for text in (segment[:ready[0].start()],segment[ready[0].end():ready[1].start()],
                     segment[ready[1].end():ready[2].start()],segment[ready[3].end():ready[4].start()]):
            assert set(re.findall(r'OWNED_DESTROY_VERIFIED=([^|\r\n]+)\|engine_unusable=true',text))==OWNED
        assert restoration_result(segment[:ready[0].start()],'auto_exit')['passed']
        motion_text=raw[action['movement_log_offset']:a+ready[1].start()]
        motion=movement_camera_proof(motion_text)
        assert motion['passed']and motion==action['movement_camera']and restoration_result(motion_text,'auto_exit')['passed']
        stamp_name=identifier+'-world-witness.json';stamp=read(stamp_name)
        assert stamp['state_file']==str(state_path)and stamp['pre_pid']==stamp['post_pid']and stamp['log_end']<=b
        assert hashlib.sha256(raw[:stamp['log_end']].encode('utf-8')).hexdigest()==stamp['log_prefix_sha256']
        world=world_proof(raw[action['world_scope_offset']:stamp['log_end']]);assert world['passed']
        paths.append(work/stamp_name)
        behavior={'passed':True,'ordinary_roundtrip_verified':True,'input_layers_recovered':True,
            'owned_object_cleanup_verified':True,'movement_camera':motion,'world_cycle':world,'new_profile_world_cycle_verified':True}
        expected=[]
        if identifier=='056_youlong':
            expected.extend((identifier,s,i)for i in(False,True)for s in('skill_01','heavy_01','skill_02','dash'))
        expected.extend([('ahua_guitoudao','skill_01',False),('ahua_guitoudao','skill_08',True),
            (identifier,'skill_01',False),(identifier,'skill_01',False)])
    proofs=[]
    for row in read('player-extra-skill-actions.json'):
        x,y=row['log_offset'],row['log_end']
        if not a<=x<y<=b:continue
        assert row['state_file']==str(state_path)and row['lines']==raw[x:y].splitlines()
        assert row['passed']and row['cast_dispatched']and row['stage']=='complete'
        boss=re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',raw[:x])[-1]
        proof=local_effect(exact_role_proof(raw,row,boss,classes[boss][row['skill']]),raw[x:y],3000)
        assert proof['local_displacement_verified']
        assert proof['active_cancel_and_restoration']if row['interrupt']else proof['natural_completion']and proof['restoration']['passed']
        proofs.append(dict(proof,boss=boss,skill=row['skill'],interrupt=row['interrupt'],log_offset=x,log_end=y))
    assert [(p['boss'],p['skill'],p['interrupt'])for p in proofs]==expected
    assert not any(t in segment for t in ('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_','HUD_UNAVAILABLE=','PBZ_CONTROL_RESTORE:FAILED='))
    paths.extend([workflow/'manifest.json',*(workflow/n for n in manifest['files'])])
    sources.update({p.relative_to(ROOT).as_posix():sha(p)for p in paths});sources.update(manifest['source_files'])
    for n,d in sources.items():assert sha(ROOT/n)==d
    result=dict(behavior,session=session,id='selection-refusal'if refusal else identifier,target_build_sha256=BUILD,
        module_source_sha256=deployment['module_source_sha256'],skill_proofs=proofs,
        reused_ordinary_skills=old if identifier=='073_yanqiansui'and not refusal else[],sources=sources,complete_mod=False)
    output=ROOT/'research/boss-adaptation/developer-attempt-receipts'/('four-boss-'+result['id']+'-'+session+'.json')
    assert not output.exists(),'Preserve collected result';write_json(output,result)
    return {'passed':True,'receipt':str(output),'complete_mod':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('session');p.add_argument('--workflow',type=Path,required=True)
    p.add_argument('--boss',choices=('073_yanqiansui','056_youlong'),default='056_youlong');p.add_argument('--refusal',action='store_true')
    a=p.parse_args();print(json.dumps(collect(a.session,a.workflow.resolve(),a.boss,a.refusal),ensure_ascii=False))
