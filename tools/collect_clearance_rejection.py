"""Archive a closed terrain refusal as failure evidence, without promoting the Boss."""
import argparse
import json
from pathlib import Path
import re
from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from control_action_evidence import restoration_result
from mod_installation import validate_package
from yanqiansui_skill_reuse import verify

ID='073_yanqiansui'
REASON='no verified 9m same-level movement clearance within 192 navigation queries; move to open ground'


def proof(segment):
    marker='PBZ_CONTROL_LIFECYCLE:WORKBENCH_BOSS_SELECTED='+ID
    assert segment.count(marker)==1
    before,after=segment.split(marker)
    restored=restoration_result(before,'auto_exit');assert restored['passed']
    assert before.count('WORKBENCH_INPUT_LOCKED=')==before.count('WORKBENCH_INPUT_RESTORED=true')==1
    assert all('OWNED_DESTROY_VERIFIED='+n+'|engine_unusable=true'in after for n in
        ('boss','boss_controller','target','target_controller','extra_target','extra_target_controller'))
    rejected=[l for l in after.splitlines()if 'INITIALIZATION_ATTEMPT_REJECTED='in l]
    assert len(rejected)==3 and all(REASON in l for l in rejected)
    assert 'PREREQUISITE_RETRY_SAFE=true'in after
    assert 'END=initialization rejected before takeover; original player restoration verified'in after
    assert not any(k in after for k in ('PLAYER_ENTRY_READY=','SPAWNED=','enter success=true','KEY_SKILL_BEGIN=',
        'ISSUE_','state=FAULTED','PBZ_CONTROL_RESTORE:FAILED='))
    return {'clearance_refusal_verified':True,'initialization_attempts':3,
        'previous_player_restoration':restored,'owned_cleanup_verified':True,
        'candidate_takeover_attempted':False,'candidate_spawned':False,
        'ordinary_roundtrip_verified':False,'movement_camera_verified':False,
        'world_cycle_verified':False,'playable':False}


def collect(session,root=ROOT):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    state_path=root/'runtime'/('official-validation-'+session)/'state.json'
    state=json.loads(state_path.read_text(encoding='utf-8'))
    work=root/'evidence/official-validation'/session
    assert state['restored'] and Path(state['work']).resolve()==work.resolve()
    def read(name):return json.loads((work/name).read_text(encoding='utf-8'))
    post=read('postcheck.json')
    assert post['validation_state']==str(state_path)
    assert all(post[k]for k in ('research_box_empty','research_loader_removed','host_registry_unchanged'))
    assert not any(post[k]for k in ('formal_files_changed','host_config_files_changed','remaining_games'))
    deployments=list(work.glob('control-lifecycle-deployment-*.json'));assert len(deployments)==1
    deployment=read(deployments[0].name)
    assert deployment['player_entry'] and deployment['boss_id']=='ahua_guitoudao'
    assert deployment['grant']['exe_sha256']==BUILD
    assert not deployment['boss_candidate'] and not deployment['scene_transition_trial']
    _,previous=verify(deployment['module_source_sha256'],root)
    action=read('yanqiansui-missing-actions.json')
    assert action['state_file']==str(state_path) and action['checks']==[]
    assert action['roundtrip_passed'] is False and action['world_finished'] is False
    assert action['error']=='AssertionError: Missing PLAYER_ENTRY_READY='+ID
    assert action['previous_ordinary_sources']==previous
    raw=(work/'UE4SS.log').read_text(encoding='utf-8',errors='replace')
    a,b=action['log_offset'],action['log_end'];assert 0<=a<b<=len(raw)
    assert action['lines']==raw[a:b].splitlines()
    result=proof(raw[a:b])
    base=root/'runtime/release-candidates/ahua-boss-workbench-v2-dev-8d16f4d84200822e'
    package=validate_package(base)
    expected={n.removeprefix('PBZBossControl/Scripts/'):h for n,h in package['files'].items()
        if n.startswith('PBZBossControl/Scripts/') and n!='PBZBossControl/Scripts/main.lua'}
    assert deployment['module_source_sha256']==expected
    files=[state_path,work/'postcheck.json',work/'UE4SS.log',work/'yanqiansui-missing-actions.json',
        work/'practice-position-actions.json',*deployments,root/'tools/collect_clearance_rejection.py']
    result.update(schema_version=1,id=ID,session=session,target_build_sha256=BUILD,
        candidate_release=package['release_id'],module_source_sha256=expected,
        formal_postcheck_passed=True,complete_mod=False,
        sources=dict(previous,**{p.relative_to(root).as_posix():sha(p)for p in files}))
    output=root/'research/boss-adaptation/developer-attempt-receipts'/(session+'.json')
    assert not output.exists(),'Preserve archived attempts'
    write_json(output,result)
    return {'receipt':str(output),'clearance_refusal_verified':True,'playable':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('session')
    print(json.dumps(collect(parser.parse_args().session),ensure_ascii=False))
