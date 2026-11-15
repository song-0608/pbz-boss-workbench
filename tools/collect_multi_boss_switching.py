"""从已关闭会话的原始证据核对双Boss普通玩家切换；不启动游戏或修改可玩标记。"""
import argparse
import json
import math
from pathlib import Path
import re
from boss_adaptation_workflow import ROOT,BUILD,sha,write_json
from collect_skill_acceptance import analyze
from control_action_evidence import restoration_result

CHECKS=['open_active_workbench_restores_ahua','ahua_to_wanjun_owned_cleanup',
        'wanjun_ordinary_bindings_natural_cancel_restored','wanjun_to_ahua_owned_cleanup',
        'ahua_controls_restored_after_roundtrip']


def retry_sources(actions,work,raw):
    """只接受精确阶段、保留原始失败收据的无破坏重试。"""
    paths=[]
    if actions.get('resumed_from'):
        camera=actions['resumed_from']=='multi-boss-switching-camera-first-attempt.json'
        entry=actions['resumed_from']=='multi-boss-switching-entry-first-attempt.json'
        assert camera or entry
        path=work/actions['resumed_from'];previous=json.loads(path.read_text(encoding='utf-8'))
        assert sha(path)==actions['resumed_from_sha256']
        assert previous['passed'] is False and previous['error']==(
            'ordinary WanJun actual movement/camera change not verified' if camera else 'skill_01: Entry not verified\n')
        assert previous['checks']==CHECKS[:3 if camera else 2] and not previous.get('resumed_from')
        assert previous['state_file']==actions['state_file'] and previous['log_offset']==actions['log_offset']
        assert previous['log_end']<=actions['resume_log_offset']<actions['camera_after_input_offset']<actions['log_end']
        assert previous['lines']==raw[previous['log_offset']:previous['log_end']].splitlines()
        if entry:
            pending=raw[previous['log_offset']:actions['resume_log_offset']].rsplit('PLAYER_ENTRY_READY=057_wanjun',1)
            assert len(pending)==2
            assert 'stop moving before entering boss control; velocity=' in pending[1]
            assert not any(k in pending[1] for k in ('KEY_SKILL_BEGIN=','enter success=true',
                'PLAYER_ENTRY_READY=','WORKBENCH_BOSS_SELECTED=','state=FAULTED','PBZ_CONTROL_RESTORE:FAILED='))
        fresh=raw[actions['camera_after_input_offset']:actions['log_end']]
        assert fresh.find('CAMERA_ARM_YAW=')>=0 and fresh.find('CAMERA_ARM_YAW=')<fresh.find('WORKBENCH_INPUT_LOCKED=')
        paths.append(path)
    if actions.get('completion_resumed_from'):
        assert actions['completion_resumed_from']=='multi-boss-switching-ahua-settling-attempt.json'
        path=work/actions['completion_resumed_from'];previous=json.loads(path.read_text(encoding='utf-8'))
        assert sha(path)==actions['completion_resumed_from_sha256']
        assert previous['passed'] is False and previous['error']=='skill_01: Entry not verified\n'
        assert previous['checks']==CHECKS[:4] and not previous.get('completion_resumed_from')
        assert previous['state_file']==actions['state_file'] and previous['log_offset']==actions['log_offset']
        for key in ('resumed_from','resumed_from_sha256','resume_log_offset','camera_after_input_offset'):
            assert previous.get(key)==actions.get(key)
        assert previous['log_end']<=actions['completion_resume_log_offset']<actions['log_end']
        assert previous['lines']==raw[previous['log_offset']:previous['log_end']].splitlines()
        pending=raw[previous['log_offset']:actions['completion_resume_log_offset']].rsplit('PLAYER_ENTRY_READY=ahua_guitoudao',1)
        assert len(pending)==2 and 'stop moving before entering boss control; velocity=' in pending[1]
        assert not any(k in pending[1] for k in ('KEY_SKILL_BEGIN=','enter success=true','PLAYER_ENTRY_READY=',
            'WORKBENCH_BOSS_SELECTED=','state=FAULTED','PBZ_CONTROL_RESTORE:FAILED='))
        paths.append(path)
    return paths


def movement_camera_proof(segment):
    positions=[float(v)for v in re.findall(r'CONTROLLED_BOSS_POSITION_DELTA=([\d.eE+-]+)',segment)]
    control=[float(v)for v in re.findall(r'CAMERA_CONTROL_YAW=([\d.eE+-]+)',segment)]
    arm=[float(v)for v in re.findall(r'CAMERA_ARM_YAW=([\d.eE+-]+)',segment)]
    finite=all(math.isfinite(v)for v in positions+control+arm)
    result={'movement_delta':positions[-1]if positions else None,'control_yaws':control,'arm_yaws':arm}
    result['passed']=bool(finite and positions and positions[-1]>1 and len(control)>=2 and len(arm)>=2
        and abs(control[-1]-control[0])>0.1 and abs(arm[-1]-arm[0])>0.1
        and 'KEY_SKILL_BEGIN='not in segment)
    return result


def exact_role_proof(raw,action,boss,expected_class):
    """同名技能必须匹配当前角色、实际按键注册及精确授予类。"""
    start,end=action['log_offset'],action['log_end']
    assembly=raw[:start].rsplit('PBZ_CONTROL_LIFECYCLE:DEFERRED_ACTOR=',1)[-1]
    ready=re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',assembly)
    assert ready==[boss], 'action must belong to one completed current Boss assembly'
    binding=action['binding']
    registrations=re.findall(r'PLAYER_BINDING=([^|\r\n]+)\|([^|\r\n]+)\|([^\r\n]+)',assembly)
    assert [r for r in registrations if r[0]==binding['slot']]==[(binding['slot'],action['skill'],binding['key'])]
    proof=analyze(raw[start:end],action['skill'])
    short=proof['ability_class_short']
    grants=re.findall(r'GRANTED_ABILITY=[^ ]+ ([^\r\n]+)',assembly)
    matches=[p for p in grants if p.rsplit('.',1)[-1]==short]if short else[]
    assert matches==[expected_class] and short==expected_class.rsplit('.',1)[-1], 'current Boss ability class mismatch'
    return dict(proof,exact_granted_class=expected_class,class_matches_live_binding=True)


def collect(session):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    state_path=ROOT/'runtime'/('official-validation-'+session)/'state.json'
    state=json.loads(state_path.read_text(encoding='utf-8'));work=Path(state['work'])
    assert state.get('restored') and work.name==session
    post_path=work/'postcheck.json';post=json.loads(post_path.read_text(encoding='utf-8'))
    assert post['validation_state']==str(state_path)
    assert all(post[k] for k in ('research_box_empty','research_loader_removed','host_registry_unchanged'))
    assert not any(post[k] for k in ('formal_files_changed','host_config_files_changed','remaining_games'))
    deployments=list(work.glob('control-lifecycle-deployment-*.json'))
    assert len(deployments)==1,'one deployment without manual rearm required'
    deployment=json.loads(deployments[0].read_text(encoding='utf-8'))
    assert deployment['player_entry'] and not deployment.get('boss_candidate') and deployment['grant']['exe_sha256']==BUILD
    source=work/'UE4SS.log';raw=source.read_text(encoding='utf-8',errors='replace')
    action_path=work/'multi-boss-switching-actions.json'
    actions=json.loads(action_path.read_text(encoding='utf-8'))
    assert actions['state_file']==str(state_path) and actions['passed'] is True
    start,end=actions['log_offset'],actions['log_end'];assert 0<=start<end<=len(raw)
    segment=raw[start:end];assert actions['lines']==segment.splitlines()
    assert actions['checks']==CHECKS
    retries=retry_sources(actions,work,raw)
    assert re.findall(r'WORKBENCH_BOSS_SELECTED=([^\r\n]+)',segment)==['057_wanjun','ahua_guitoudao']
    ready=list(re.finditer(r'PLAYER_ENTRY_READY=([^\r\n]+)',segment))
    assert [r[1] for r in ready]==['057_wanjun','ahua_guitoudao']
    expected_locks=3 if actions.get('resumed_from')=='multi-boss-switching-camera-first-attempt.json' else 2
    assert segment.count('WORKBENCH_INPUT_LOCKED=')==segment.count('WORKBENCH_INPUT_RESTORED=true')==expected_locks
    expected={'boss','boss_controller','target','target_controller','extra_target','extra_target_controller'}
    for interval in (segment[:ready[0].start()],segment[ready[0].end():ready[1].start()]):
        assert {r for r in re.findall(r'OWNED_DESTROY_VERIFIED=([^|\r\n]+)\|engine_unusable=true',interval)}==expected
        assert restoration_result(interval,'auto_exit')['passed']
    assert not any(token in segment for token in ('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_',
        'HUD_UNAVAILABLE=','PBZ_CONTROL_RESTORE:FAILED='))
    wanjun_segment=segment[ready[0].end():ready[1].start()]
    movement_segment=wanjun_segment[wanjun_segment.rfind('[PBZBossControl] enter success=true state=ACTIVE'):]
    movement=movement_camera_proof(movement_segment)
    assert movement['passed'],'ordinary WanJun movement and camera readback required'
    skill_path=work/'player-extra-skill-actions.json';skill_actions=json.loads(skill_path.read_text(encoding='utf-8'))
    base_path=ROOT/'evidence/official-validation/20261115-100319/boss-candidate-acceptance.json'
    base=json.loads(base_path.read_text(encoding='utf-8'))
    assert base['base_control_accepted'] and base['id']=='057_wanjun'
    from build_ahua_acceptance_matrix import capabilities
    classes={'ahua_guitoudao':{r['skill']:r['class_path']for r in capabilities()},
             '057_wanjun':{k:r['class_path']for k,r in base['accepted_skills'].items()}}
    proofs=[]
    rejected=[]
    for action in skill_actions:
        a,b=action['log_offset'],action['log_end']
        if not start<=a<b<=end:continue
        assert action['state_file']==str(state_path) and action['lines']==raw[a:b].splitlines()
        if not action.get('cast_dispatched',True):
            assert action['passed'] is False and 'KEY_SKILL_BEGIN='not in raw[a:b]
            rejected.append({'log_offset':a,'log_end':b,'failure_kind':action['failure_kind']})
            continue
        boss='057_wanjun'if a<start+ready[1].start() else'ahua_guitoudao'
        proof=exact_role_proof(raw,action,boss,classes[boss][action['skill']])
        proofs.append(dict(proof,boss=boss,skill=action['skill'],interrupt=action['interrupt']))
    required={(boss,skill,interrupt) for boss,skills in [('057_wanjun',('skill_01','heavy_01','skill_02','dash'))]
              for skill in skills for interrupt in (False,True)}
    required|={('ahua_guitoudao','skill_01',False),('ahua_guitoudao','skill_08',True)}
    accepted={(p['boss'],p['skill'],True) for p in proofs
              if p['interrupt'] and p['active_cancel_and_restoration']}
    accepted|={(p['boss'],p['skill'],False)for p in proofs
               if not p['interrupt'] and p['natural_completion'] and p['restoration']['passed']}
    assert required<=accepted,'ordinary character-specific skill checks incomplete'
    result={'passed':True,'session':session,'boss_ids':['ahua_guitoudao','057_wanjun'],
        'target_build_sha256':BUILD,'module_source_sha256':deployment['module_source_sha256'],
        'ordinary_roundtrip_verified':True,'input_layers_recovered':True,
        'owned_object_cleanup_verified':True,'wanjun_movement_camera':movement,'skill_proofs':proofs,
        'undispatched_attempts':rejected,
        'sources':{str(p.relative_to(ROOT)):sha(p)for p in (state_path,post_path,source,action_path,skill_path,base_path,*deployments,*retries)}}
    target=work/'multi-boss-switching-acceptance.json';write_json(target,result)
    print(json.dumps({'passed':True,'report':str(target)},ensure_ascii=False))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('session');collect(parser.parse_args().session)
