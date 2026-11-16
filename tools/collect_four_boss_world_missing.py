"""Require a fresh native-menu World cycle on exact ordinary modules; reuse only accepted skills."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from boss_adaptation_workflow import ROOT,BUILD,sha,write_json
from four_boss_integration_workflow import verify as workflow_verify
from four_boss_ordinary_reuse import verify
from collect_auto_world_reassembly import proof as world_proof
from collect_multi_boss_switching import exact_role_proof
from candidate_effect_scope import local_effect


def collect(session,workflow):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    manifest=workflow_verify(workflow)
    state_path=ROOT/'runtime'/('official-validation-'+session)/'state.json'
    state=json.loads(state_path.read_text(encoding='utf-8'));work=ROOT/'evidence/official-validation'/session
    assert state['restored']and Path(state['work']).resolve()==work.resolve()
    def read(n):return json.loads((work/n).read_text(encoding='utf-8'))
    post=read('postcheck.json');assert post['validation_state']==str(state_path)
    assert all(post[k]for k in('research_box_empty','research_loader_removed','host_registry_unchanged'))
    assert not any(post[k]for k in('formal_files_changed','host_config_files_changed','remaining_games'))
    deployments=list(work.glob('control-lifecycle-deployment-*.json'));assert len(deployments)==1
    deployment=read(deployments[0].name)
    assert deployment['player_entry']and deployment['boss_id']=='ahua_guitoudao'and not deployment['boss_candidate']and not deployment['scene_transition_trial']
    assert deployment['grant']['exe_sha256']==BUILD
    ordinary,sources=verify(deployment['module_source_sha256'])
    action=read('youlong-world-missing.json')
    assert action['state_file']==str(state_path)and action['workflow']==str(workflow)
    assert action['previous_ordinary_sources']==sources and action['ready']and action['passed']and not action.get('error')
    raw=(work/'UE4SS.log').read_text(encoding='utf-8',errors='replace')
    a,b=action['log_offset'],action['log_end'];segment=raw[a:b];x=action['world_scope_offset']
    assert 0<=a<x<action['witness_log_end']<=b<=len(raw)and action['lines']==segment.splitlines()
    assert re.findall(r'WORKBENCH_BOSS_SELECTED=([^\r\n]+)',segment)==['056_youlong','ahua_guitoudao']
    ready=list(re.finditer(r'PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=([^\r\n]+)',segment))
    assert [r[1]for r in ready]==['056_youlong','056_youlong','ahua_guitoudao']
    assert x==a+ready[0].start()
    assert segment.count('WORKBENCH_INPUT_LOCKED=')==segment.count('WORKBENCH_INPUT_RESTORED=true')==2
    expected={'boss','boss_controller','target','target_controller','extra_target','extra_target_controller'}
    for text in(segment[:ready[0].start()],segment[ready[1].end():ready[2].start()]):
        assert set(re.findall(r'OWNED_DESTROY_VERIFIED=([^|\r\n]+)\|engine_unusable=true',text))==expected
    stamp=read('youlong-world-missing-witness.json')
    assert stamp['state_file']==str(state_path)and stamp['pre_pid']==stamp['post_pid']and stamp['log_end']==action['witness_log_end']
    assert hashlib.sha256(raw[:stamp['log_end']].encode('utf-8')).hexdigest()==stamp['log_prefix_sha256']
    world=world_proof(raw[x:stamp['log_end']]);assert world['passed']
    classes={p['skill']:p['exact_granted_class']for p in ordinary};proofs=[]
    for row in read('player-extra-skill-actions.json'):
        l,r=row['log_offset'],row['log_end']
        if not a<=l<r<=b:continue
        assert row['state_file']==str(state_path)and row['lines']==raw[l:r].splitlines()
        assert row['passed']and row['cast_dispatched']and row['stage']=='complete'and row['skill']=='skill_01'and not row['interrupt']
        proof=local_effect(exact_role_proof(raw,row,'056_youlong',classes['skill_01']),raw[l:r],3000)
        assert proof['local_displacement_verified']and proof['natural_completion']and proof['restoration']['passed']
        proofs.append(dict(proof,log_offset=l,log_end=r))
    assert len(proofs)==2 and proofs[0]['log_offset']<a+ready[1].start()<proofs[1]['log_offset']
    menu=read('settings-menu-actions.json')
    assert len([r for r in menu if r['purpose']=='control_menu_confirm'])==len([r for r in menu if r['purpose']=='control_menu_continue'])==1
    assert not any(k in segment for k in('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_','PBZ_CONTROL_RESTORE:FAILED='))
    paths=[state_path,work/'postcheck.json',work/'UE4SS.log',work/'youlong-world-missing.json',
        work/'youlong-world-missing-witness.json',work/'player-extra-skill-actions.json',work/'settings-menu-actions.json',*deployments,
        workflow/'manifest.json',*(workflow/n for n in manifest['files'])]
    for name in('native_menu_input.py','four_boss_ordinary_reuse.py','test_four_boss_world_missing.py',
                'collect_four_boss_world_missing.py','../tests/test_four_boss_ordinary_reuse.py'):
        paths.append((ROOT/'tools'/name).resolve())
    if (work/'native-menu-input-actions.json').exists():paths.append(work/'native-menu-input-actions.json')
    sources.update(manifest['source_files']);sources.update({p.relative_to(ROOT).as_posix():sha(p)for p in paths})
    for n,d in sources.items():assert sha(ROOT/n)==d
    result={'passed':True,'session':session,'id':'056_youlong','target_build_sha256':BUILD,
        'ordinary_roundtrip_verified':True,'ordinary_skills_verified':True,'new_profile_world_cycle_verified':True,
        'world_cycle':world,'skill_proofs':proofs,'reused_ordinary_skills':ordinary,
        'module_source_sha256':deployment['module_source_sha256'],'sources':sources,'complete_mod':False}
    output=ROOT/'research/boss-adaptation/developer-attempt-receipts'/('four-boss-youlong-world-'+session+'.json')
    assert not output.exists();write_json(output,result)
    return {'passed':True,'receipt':str(output),'world_cycle_verified':True,'complete_mod':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('session');p.add_argument('--workflow',type=Path,required=True);a=p.parse_args()
    print(json.dumps(collect(a.session,a.workflow.resolve()),ensure_ascii=False))
