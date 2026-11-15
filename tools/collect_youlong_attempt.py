"""Independently archive one closed native YouLong control milestone, never unlock a player Boss."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from boss_adaptation_workflow import ROOT,BUILD,sha,write_json
from collect_boss_candidate_acceptance import candidate_interval
from collect_skill_acceptance import analyze
from candidate_effect_scope import local_effect
from collect_practice_stability import proof as stability_proof
from collect_multi_boss_switching import movement_camera_proof
from control_action_evidence import restoration_result
from mod_installation import installed_package
import youlong_developer_bundle as bundle
import youlong_developer_workflow as workflow


def actions_proof(raw,actions,state_file,begin,bindings):
    proofs=[];seen=set()
    final=raw[begin:]
    assert final.count('CANDIDATE_IDENTITY_READY=056_youlong|')==1
    assert final.count('INTERACTIVE_READY=')==1 and 'PLAYER_ENTRY_READY='not in final
    for action in actions:
        assert action['state_file']==state_file
        a,b=action['log_offset'],action['log_end'];assert begin<=a<b<=len(raw)
        assert action['lines']==raw[a:b].splitlines(),'Exact current raw action interval required'
        key=(action['skill'],action['interrupt']);assert key not in seen,'One action per role and phase'
        seen.add(key);skill=action['skill'];assert skill in bindings
        assert action['passed'] and action['cast_dispatched']and action['stage']=='complete'
        registered=action['binding'];prefix=raw[begin:a]
        rows=re.findall(r'PLAYER_BINDING=([^|\r\n]+)\|([^|\r\n]+)\|([^\r\n]+)',prefix)
        assert [r for r in rows if r[0]==registered['slot']]==[(registered['slot'],skill,registered['key'])]
        result=local_effect(analyze(raw[a:b],skill),raw[a:b],3000)
        expected=bindings[skill]
        assert result['ability_class_short']==expected.rsplit('.',1)[-1]and result['activation_instance_verified']
        grants=re.findall(r'GRANTED_ABILITY=[^ ]+ ([^\r\n]+)',prefix)
        assert [p for p in grants if p.rsplit('.',1)[-1]==result['ability_class_short']]==[expected]
        assert result['local_displacement_verified']
        assert result['active_cancel_and_restoration']if action['interrupt']else result['natural_completion']and result['restoration']['passed']
        proofs.append(dict(result,skill=skill,interrupt=action['interrupt'],exact_granted_class=expected,
            class_matches_live_binding=True,log_offset=a,log_end=b))
    assert seen=={(skill,phase)for skill in bindings for phase in (False,True)}
    return proofs


def collect(session,workflow_path,root=ROOT):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    manifest=workflow.verify(workflow_path,root)
    state_path=root/'runtime'/('official-validation-'+session)/'state.json'
    state=bundle.read(state_path);work=root/'evidence/official-validation'/session
    assert state['restored']and Path(state['work']).resolve()==work.resolve()
    post=bundle.read(work/'postcheck.json')
    assert post['validation_state']==str(state_path)
    assert all(post[k]for k in ('research_box_empty','research_loader_removed','host_registry_unchanged'))
    assert not any(post[k]for k in ('formal_files_changed','host_config_files_changed','remaining_games'))
    deployment_paths=list(work.glob('control-lifecycle-deployment-*.json'));assert len(deployment_paths)==1
    deployment=bundle.read(deployment_paths[0])
    assert deployment['boss_candidate']==bundle.ID and not deployment['player_entry']
    assert deployment['grant']['exe_sha256']==BUILD
    assert deployment['candidate_identity_grant']==manifest['candidate_grant']
    assert deployment['developer_bundle']==manifest['bundle']
    frozen=bundle.read(Path(manifest['bundle'])/'manifest.json')
    expected={n.removeprefix('Scripts/'):h for n,h in frozen['base_mod_files'].items()
        if n.startswith('Scripts/')and n!='Scripts/main.lua'}
    expected['boss_candidate.lua']=frozen['overrides']['Scripts/boss_candidate.lua']
    assert deployment['module_source_sha256']==expected
    raw=(work/'UE4SS.log').read_text(encoding='utf-8',errors='replace')
    begin,rejected=candidate_interval(raw,bundle.ID);segment=raw[begin:]
    identity='CANDIDATE_IDENTITY_READY='+bundle.ID+'|'+frozen['definition']['class_path']+'|'+frozen['definition']['config_path']
    assert segment.count(identity)==1
    rows=re.findall(r'CANDIDATE_LIVE_BINDING=([^|\r\n]+)\|([^|\r\n]+)\|([^\r\n]+)',segment)
    assert len(rows)==4 and all(r[0]==bundle.ID for r in rows)
    bindings={r[1]:r[2]for r in rows};assert set(bindings)=={'skill_01','heavy_01','skill_02','dash'}
    assert all(v in frozen['definition']['ability_pool']for v in bindings.values())
    actions=bundle.read(work/'player-extra-skill-actions.json')
    proofs=actions_proof(raw,actions,str(state_path),begin,bindings)
    milestone=bundle.read(work/'boss-candidate-milestone.json')
    assert milestone['passed']and milestone['state_file']==str(state_path)and milestone['candidate']==bundle.ID
    assert not milestone.get('natural_session')and not milestone.get('resumed_from')
    stable=stability_proof(segment,session,frozen['definition']['display_name']);assert stable['passed']
    motion_segment=segment[segment.rfind('[PBZBossControl] enter success=true state=ACTIVE'):]
    motion=movement_camera_proof(motion_segment)
    assert motion['passed']and restoration_result(motion_segment,'exit')['passed']
    assert all('OWNED_DESTROY_VERIFIED='+n+'|engine_unusable=true'in motion_segment for n in
        ('boss','boss_controller','target','target_controller','extra_target','extra_target_controller'))
    # Run the frozen workflow's original collector only after the independent checks.
    accepted=work/'boss-candidate-acceptance.json'
    if not accepted.exists():
        result=subprocess.run([sys.executable,str(workflow_path/'collect_boss_candidate_acceptance.py'),session,bundle.ID],
            cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        assert result.returncode==0,result.stdout+result.stderr
    report=bundle.read(accepted)
    assert report['base_control_accepted']and report['playable']is False
    assert report['module_source_sha256']==expected and set(report['accepted_skills'])==set(bindings)
    assert report['stability']==stable and report['rejected_layout_attempts']==rejected
    paths=[state_path,work/'postcheck.json',work/'UE4SS.log',work/'player-extra-skill-actions.json',
        work/'boss-candidate-milestone.json',accepted,*deployment_paths,workflow_path/'manifest.json',
        *(workflow_path/n for n in manifest['files']),Path(manifest['bundle'])/'manifest.json',
        Path(manifest['bundle'])/'boss_candidate.lua',root/'tools/collect_youlong_attempt.py']
    sources={p.relative_to(root).as_posix():sha(p)for p in paths}
    sources.update(frozen['evidence']);sources.update(frozen['source_files']);sources.update(manifest['source_files'])
    for name,digest in sources.items():assert sha(root/name)==digest,'Evidence changed before archive: '+name
    result={'schema_version':1,'session':session,'id':bundle.ID,'target_build_sha256':BUILD,
        'base_control_accepted':True,'live_grants_verified':True,'ordinary_switching_accepted':False,
        'world_cycle_verified':False,'playable':False,'complete_mod':False,'formal_postcheck_passed':True,
        'module_source_sha256':expected,'bindings':bindings,'actions':proofs,'movement_camera':motion,
        'stability':stable,'rejected_layout_attempts':rejected,'sources':sources}
    output=root/'research/boss-adaptation/developer-attempt-receipts'/('youlong-'+session+'.json')
    assert not output.exists(),'Preserve collected YouLong attempt'
    write_json(output,result)
    return {'receipt':str(output),'base_control_accepted':True,'playable':False,'stability':stable}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('session');parser.add_argument('--workflow',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(collect(args.session,args.workflow.resolve()),ensure_ascii=False))
