"""Archive passed sub-milestones from an incomplete ordinary attempt, never mark World passed."""
import argparse
import json
from pathlib import Path
import re
from boss_adaptation_workflow import ROOT,BUILD,sha,write_json
from four_boss_integration_workflow import verify,verify_current,CANDIDATE
from mod_installation import validate_package
from collect_multi_boss_switching import exact_role_proof,movement_camera_proof
from candidate_effect_scope import local_effect
from control_action_evidence import restoration_result


def collect(session,workflow):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    manifest=verify(workflow);state_path=ROOT/'runtime'/('official-validation-'+session)/'state.json'
    state=json.loads(state_path.read_text(encoding='utf-8'));work=ROOT/'evidence/official-validation'/session
    assert state['restored']and Path(state['work']).resolve()==work.resolve()
    def read(n):return json.loads((work/n).read_text(encoding='utf-8'))
    post=read('postcheck.json');assert post['validation_state']==str(state_path)
    assert all(post[k]for k in('research_box_empty','research_loader_removed','host_registry_unchanged'))
    assert not any(post[k]for k in('formal_files_changed','host_config_files_changed','remaining_games'))
    deployments=list(work.glob('control-lifecycle-deployment-*.json'));assert len(deployments)==1
    deployment=read(deployments[0].name);assert deployment['player_entry']and not deployment['boss_candidate']
    assert deployment['boss_id']=='ahua_guitoudao'and deployment['grant']['exe_sha256']==BUILD
    _,sources=verify_current(deployment['module_source_sha256'])
    name='056_youlong-ordinary-integration.json';action=read(name)
    assert action['state_file']==str(state_path)and action['workflow']==str(workflow)
    assert action['roundtrip_passed']and not action['world_finished']and not action.get('error')
    assert action['previous_ordinary_sources']==sources
    assert action['checks']==['active_ahua_open_restores_player','new_boss_selected_with_cleanup',
        'four_ordinary_natural_and_cancel','new_boss_movement_camera_restored',
        'return_ahua_controls_restored','new_boss_pre_world_skill_restored']
    raw=(work/'UE4SS.log').read_text(encoding='utf-8',errors='replace')
    a,b=action['log_offset'],action['log_end'];segment=raw[a:b]
    assert 0<=a<action['movement_log_offset']<action['world_scope_offset']<b<=len(raw)
    assert action['lines']==segment.splitlines()
    assert re.findall(r'WORKBENCH_BOSS_SELECTED=([^\r\n]+)',segment)==['056_youlong','ahua_guitoudao','056_youlong']
    ready=list(re.finditer(r'PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=([^\r\n]+)',segment))
    assert [r[1]for r in ready]==['056_youlong','ahua_guitoudao','056_youlong']
    assert action['world_scope_offset']==a+ready[-1].start()
    assert segment.count('WORKBENCH_INPUT_LOCKED=')==segment.count('WORKBENCH_INPUT_RESTORED=true')==3
    expected={'boss','boss_controller','target','target_controller','extra_target','extra_target_controller'}
    for text in(segment[:ready[0].start()],segment[ready[0].end():ready[1].start()],segment[ready[1].end():ready[2].start()]):
        assert set(re.findall(r'OWNED_DESTROY_VERIFIED=([^|\r\n]+)\|engine_unusable=true',text))==expected
    assert restoration_result(segment[:ready[0].start()],'auto_exit')['passed']
    motion_text=raw[action['movement_log_offset']:a+ready[1].start()]
    motion=movement_camera_proof(motion_text)
    assert motion['passed']and motion==action['movement_camera']and restoration_result(motion_text,'auto_exit')['passed']
    candidate=validate_package(ROOT/'runtime/release-candidates'/CANDIDATE)
    receipt=json.loads((ROOT/candidate['youlong_attempt_receipt']).read_text(encoding='utf-8'))
    from build_ahua_acceptance_matrix import capabilities
    classes={'056_youlong':receipt['bindings'],'ahua_guitoudao':{r['skill']:r['class_path']for r in capabilities()}}
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
    assert [(p['boss'],p['skill'],p['interrupt'])for p in proofs]==[
        *(('056_youlong',s,i)for i in(False,True)for s in('skill_01','heavy_01','skill_02','dash')),
        ('ahua_guitoudao','skill_01',False),('ahua_guitoudao','skill_08',True),('056_youlong','skill_01',False)]
    later=raw[b:]
    assert 'WORLD_REASSEMBLY_AWAITING_GAMEPLAY='not in later
    menu=read('settings-menu-actions.json')
    assert any(r['purpose']=='control_menu_pause'for r in menu)
    assert not any(r['purpose']in('control_menu_confirm','control_menu_continue')for r in menu)
    assert not any(k in raw[a:]for k in('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_','PBZ_CONTROL_RESTORE:FAILED='))
    paths=[state_path,work/'postcheck.json',work/'UE4SS.log',work/name,work/'player-extra-skill-actions.json',
        work/'settings-menu-actions.json',*deployments,workflow/'manifest.json',*(workflow/n for n in manifest['files']),
        ROOT/'tools/collect_four_boss_attempt.py']
    sources.update(manifest['source_files']);sources.update({p.relative_to(ROOT).as_posix():sha(p)for p in paths})
    for n,d in sources.items():assert sha(ROOT/n)==d
    result={'session':session,'id':'056_youlong','target_build_sha256':BUILD,
        'ordinary_skills_verified':True,'ordinary_roundtrip_verified':True,'movement_camera':motion,
        'new_profile_world_cycle_verified':False,'native_player_menu_verified':False,
        'formal_postcheck_passed':True,'playable':False,'complete_mod':False,
        'limitation':'Original menu did not visibly open after restored OFF; no world transition performed.',
        'module_source_sha256':deployment['module_source_sha256'],'actions':proofs,'sources':sources}
    output=ROOT/'research/boss-adaptation/developer-attempt-receipts'/('four-boss-youlong-'+session+'.json')
    assert not output.exists();write_json(output,result)
    return {'receipt':str(output),'ordinary_skills_verified':True,'ordinary_roundtrip_verified':True,'world_cycle_verified':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('session');p.add_argument('--workflow',type=Path,required=True);a=p.parse_args()
    print(json.dumps(collect(a.session,a.workflow.resolve()),ensure_ascii=False))
