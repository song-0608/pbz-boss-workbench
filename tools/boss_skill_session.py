"""Same-process skill batches advance only after exact owned cleanup is observed."""
import re
from control_action_evidence import restoration_result
from collect_skill_acceptance import analyze
from collect_practice_stability import proof as stability_proof
from collect_boss_candidate_acceptance import candidate_interval
from candidate_effect_scope import local_effect

OWNED=('boss','boss_controller','target','target_controller','extra_target','extra_target_controller')


def complete_assembly(text):
    if text.count('PBZ_CONTROL_LIFECYCLE:INTERACTIVE_READY=')!=1:
        return False
    if text.count('PBZ_CONTROL_LIFECYCLE:INTERACTIVE_END=')!=1:
        return False
    end=text.index('PBZ_CONTROL_LIFECYCLE:INTERACTIVE_END=')
    ready=text.index('PBZ_CONTROL_LIFECYCLE:INTERACTIVE_READY=')
    if end<=ready or any(token in text for token in (
        'state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_',
        'PBZ_CONTROL_RESTORE:FAILED=','DESTROY_SKIPPED','[Lua::execute_file]')):
        return False
    if not all('OWNED_DESTROY_VERIFIED='+name+'|engine_unusable=true' in text[ready:end]
               for name in OWNED):
        return False
    enter=text.rfind('[PBZBossControl] enter success=true state=ACTIVE',ready,end)
    return enter>=0 and restoration_result(text[enter:end])['passed']


def evaluate(raw,start,end,identifier,session,expected,actions,display_name):
    """Evaluate one bounded assembly, keeping global action offsets exact."""
    assert type(start) is int and type(end) is int and 0<=start<end<=len(raw)
    segment=raw[start:end]
    begin,rejected=candidate_interval(segment,identifier)
    bindings={}
    for boss,skill,path in re.findall(r'CANDIDATE_LIVE_BINDING=([^|\r\n]+)\|([^|\r\n]+)\|([^\r\n]+)',segment[begin:]):
        assert boss==identifier and skill not in bindings,'Mixed or duplicate skill binding'
        bindings[skill]=path
    assert bindings==expected,'The assembly did not bind the four frozen actions'
    rows=[];seen=set()
    for action in actions:
        a,b=action['log_offset'],action['log_end']
        if b<=start or a>=end:continue
        assert start<=a<b<=end,'Action crosses an assembly boundary'
        interval=raw[a:b]
        assert action['lines']==interval.splitlines(),'Action is not the exact raw interval'
        skill=action['skill'];assert skill in bindings
        key=(skill,action['interrupt']);assert type(key[1]) is bool and key not in seen
        seen.add(key)
        result=local_effect(analyze(interval,skill),interval)
        result.update(skill=skill,interrupt=action['interrupt'],log_offset=a,log_end=b,
            exact_granted_class=bindings[skill])
        assert result['ability_class_short']==bindings[skill].rsplit('.',1)[-1],'Wrong skill instance'
        rows.append(result)
    skills={}
    for skill,path in bindings.items():
        natural=[row for row in rows if row['skill']==skill and not row['interrupt']
                 and row['natural_completion'] and row['restoration']['passed']]
        cancel=[row for row in rows if row['skill']==skill and row['interrupt']
                and row['active_cancel_and_restoration']]
        skills[skill]=dict(class_path=path,activation_runtime_verified=bool(natural and cancel),
            natural_completion_verified=bool(natural),cancellation_runtime_verified=bool(cancel),
            gameplay_verified=any(row['natural_completion']['damage_observed'] for row in natural),
            movement_runtime_verified=any(row['natural_completion']['movement_observed'] for row in natural))
    accepted={k:v for k,v in skills.items() if v['natural_completion_verified']
              and v['cancellation_runtime_verified'] and (v['gameplay_verified'] or v['movement_runtime_verified'])}
    stability=stability_proof(segment[begin:],session,display_name)
    enter=segment.rfind('[PBZBossControl] enter success=true state=ACTIVE')
    movement=segment[enter:] if enter>=0 else ''
    positions=[float(v) for v in re.findall(r'CONTROLLED_BOSS_POSITION_DELTA=([\d.eE+-]+)',movement)]
    control=[float(v) for v in re.findall(r'CAMERA_CONTROL_YAW=([\d.eE+-]+)',movement)]
    arm=[float(v) for v in re.findall(r'CAMERA_ARM_YAW=([\d.eE+-]+)',movement)]
    movement_camera=dict(movement_verified=bool(positions and positions[-1]>1),
        camera_rotation_verified=bool(len(control)>=2 and len(arm)>=2 and
            abs(control[-1]-control[0])>.1 and abs(arm[-1]-arm[0])>.1))
    cleanup=complete_assembly(segment[begin:])
    return dict(id=identifier,log_offset=start,log_end=end,skills=skills,accepted_skills=accepted,
        actions=rows,stability=stability,movement_camera=movement_camera,
        owned_cleanup_and_restoration_verified=cleanup,rejected_layout_attempts=rejected,
        all_four_accepted=bool(len(accepted)==4 and len(rows)==8 and stability['passed']
                              and cleanup and all(movement_camera.values())),playable=False)
