"""Collect fresh switching/movement/World proof and independently reparse unchanged skill evidence."""
import argparse
import json
from pathlib import Path
import re
import hashlib
from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from collect_multi_boss_switching import exact_role_proof,movement_camera_proof
from collect_auto_world_reassembly import proof as world_proof
from control_action_evidence import restoration_result
from yanqiansui_skill_reuse import verify

ID='073_yanqiansui'
CHECKS=['active_ahua_to_yanqiansui_cleanup','yanqiansui_movement_camera_restored',
        'return_ahua_controls_restored','yanqiansui_pre_world_skill_restored','new_world_skill_and_restoration']


def collect(session):
    assert re.fullmatch('[0-9]{8}-[0-9]{6}',session)
    state_path=ROOT/'runtime'/('official-validation-'+session)/'state.json'
    state=json.loads(state_path.read_text(encoding='utf-8'));work=Path(state['work'])
    assert state['restored'] and work.name==session
    def read(name):return json.loads((work/name).read_text(encoding='utf-8'))
    post=read('postcheck.json')
    assert post['validation_state']==str(state_path)
    assert all(post[k]for k in ('research_box_empty','research_loader_removed','host_registry_unchanged'))
    assert not any(post[k]for k in ('formal_files_changed','host_config_files_changed','remaining_games'))
    deployments=list(work.glob('control-lifecycle-deployment-*.json'));assert len(deployments)==1
    deployment=read(deployments[0].name)
    assert deployment['player_entry'] and deployment['boss_id']=='ahua_guitoudao'
    assert not deployment['boss_candidate'] and not deployment['scene_transition_trial']
    assert deployment['grant']['exe_sha256']==BUILD
    old_skills,old_sources=verify(deployment['module_source_sha256'])
    action=read('yanqiansui-missing-actions.json')
    assert action['state_file']==str(state_path) and action['roundtrip_passed'] and action['world_finished']
    assert action['checks']==CHECKS and not action.get('error') and action['previous_ordinary_sources']==old_sources
    raw=(work/'UE4SS.log').read_text(encoding='utf-8',errors='replace')
    a,b=action['log_offset'],action['log_end'];segment=raw[a:b]
    assert 0<=a<action['movement_log_offset']<action['world_scope_offset']<b<=len(raw)
    assert action['lines']==segment.splitlines()
    selections=[l.split('WORKBENCH_BOSS_SELECTED=',1)[1]for l in segment.splitlines()if 'WORKBENCH_BOSS_SELECTED='in l]
    assert selections==[ID,'ahua_guitoudao',ID]
    ready=list(re.finditer('PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=',segment))
    names=[segment[r.end():].splitlines()[0]for r in ready]
    assert names==[ID,'ahua_guitoudao',ID,ID]
    assert action['world_scope_offset']==a+ready[2].start()
    assert segment.count('WORKBENCH_INPUT_LOCKED=')==segment.count('WORKBENCH_INPUT_RESTORED=true')==3
    for interval in (segment[:ready[0].start()],segment[ready[0].end():ready[1].start()],segment[ready[1].end():ready[2].start()]):
        assert all('OWNED_DESTROY_VERIFIED='+n+'|engine_unusable=true'in interval for n in
            ('boss','boss_controller','target','target_controller','extra_target','extra_target_controller'))
    assert restoration_result(segment[:ready[0].start()],'auto_exit')['passed']
    movement=raw[action['movement_log_offset']:a+ready[1].start()]
    motion=movement_camera_proof(movement)
    assert motion['passed'] and motion==action['movement_camera'] and restoration_result(movement,'auto_exit')['passed']
    assert segment.count('NAVIGATION_CLEARANCE_VERIFIED=radius=900|samples=24|queries=')==3
    from build_ahua_acceptance_matrix import capabilities
    classes={'ahua_guitoudao':{r['skill']:r['class_path']for r in capabilities()},
             ID:{p['skill']:p['exact_granted_class']for p in old_skills}}
    proofs=[]
    for row in read('player-extra-skill-actions.json'):
        x,y=row['log_offset'],row['log_end']
        if not a<=x<y<=b:continue
        assert row['passed'] and row['cast_dispatched'] and row['state_file']==str(state_path)
        assert row['lines']==raw[x:y].splitlines()
        boss=[l.split('PLAYER_ENTRY_READY=',1)[1]for l in raw[:x].splitlines()if 'PLAYER_ENTRY_READY='in l][-1]
        p=exact_role_proof(raw,row,boss,classes[boss][row['skill']])
        assert p['active_cancel_and_restoration'] if row['interrupt'] else p['natural_completion'] and p['restoration']['passed']
        proofs.append(dict(p,boss=boss,skill=row['skill'],interrupt=row['interrupt']))
    assert [(p['boss'],p['skill'],p['interrupt'])for p in proofs]==[
        ('ahua_guitoudao','skill_01',False),('ahua_guitoudao','skill_08',True),(ID,'skill_01',False),(ID,'skill_01',False)]
    witness=read('auto-world-witness.json')
    assert witness['state_file']==str(state_path) and witness['pre_pid']==witness['post_pid']
    assert hashlib.sha256(raw[:witness['log_end']].encode('utf-8')).hexdigest()==witness['log_prefix_sha256']
    assert witness['log_end']<=b
    world=world_proof(raw[action['world_scope_offset']:witness['log_end']]);assert world['passed']
    menu=read('settings-menu-actions.json')
    assert len([r for r in menu if r['purpose']=='control_menu_confirm'])==len([r for r in menu if r['purpose']=='control_menu_continue'])==1
    assert not any(t in segment for t in ('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_','HUD_UNAVAILABLE=','PBZ_CONTROL_RESTORE:FAILED='))
    paths=[state_path,work/'postcheck.json',work/'UE4SS.log',work/'yanqiansui-missing-actions.json',
        work/'player-extra-skill-actions.json',work/'auto-world-witness.json',work/'settings-menu-actions.json',*deployments]
    result={'passed':True,'session':session,'id':ID,'target_build_sha256':BUILD,
        'ordinary_roundtrip_verified':True,'input_layers_recovered':True,'owned_object_cleanup_verified':True,
        'movement_camera':motion,'world_cycle':world,'new_profile_world_cycle_verified':True,
        'module_source_sha256':deployment['module_source_sha256'],'reused_ordinary_skills':old_skills,
        'current_skill_proofs':proofs,'complete_mod':False,
        'sources':dict(old_sources,**{p.relative_to(ROOT).as_posix():sha(p)for p in paths})}
    out=work/'yanqiansui-missing-acceptance.json';assert not out.exists();write_json(out,result)
    return {'report':str(out),'passed':True}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('session')
    print(json.dumps(collect(p.parse_args().session),ensure_ascii=False))
