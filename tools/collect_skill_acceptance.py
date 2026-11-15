"""关闭会话逐招重验原始区间与部署版本；不自动修改可玩标志。"""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from control_action_evidence import restoration_result
from player_keymap import ability_for_slot

ROOT=Path(__file__).resolve().parents[1]
SUBTREE_NAMES={'attack_01':'GA_AHua_Attack_01','homing_flower':'GA_AHua_Homing_Flower',
               'homing_flower_hard':'GA_AHua_Homing_Flower_Hard'}


def registered_subtree_class(skill):
    name=SUBTREE_NAMES.get(skill)
    return '/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/New/'+name+'.'+name+'_C'if name else None


def analyze(segment, skill):
    requested_begins=re.findall(r'KEY_SKILL_BEGIN='+re.escape(skill)+r'\|',segment)
    begin=re.search(r'KEY_SKILL_BEGIN='+re.escape(skill)+r'\|[^\r\n]*\|active=[1-9]\d*',segment)
    instance=re.search(r'SKILL_INSTANCE='+re.escape(skill)+r'\|active=true\|cancelable=(true|false)\|object=([^ ]+) ([^\r\n]+)',segment)
    observed=bool(len(requested_begins)==1 and begin and instance and begin.start()<instance.start())
    rows=re.finditer(r'KEY_SKILL_END='+re.escape(skill)+r'\|peak=(\d+)\|active=(\d+)\|natural=(true|false)'
        r'\|health_before=([\d.-]+)\|health_after=([\d.-]+)\|distance=([\d.eE+-]+)',segment)
    natural=None
    for row in rows:
        peak,active,ended,before,after,distance=row.groups()
        values=tuple(map(float,(before,after,distance)))
        if observed and instance.end()<row.start() and int(peak)>0 and int(active)==0 and ended=='true' and all(math.isfinite(v) and v>=0 for v in values):
            natural={'health_before':values[0],'health_after':values[1],'distance':values[2],
                'damage_observed':values[0]>values[1],'movement_observed':values[2]>1}
    cancelled=False
    if observed and instance[1]=='true':
        invoke=re.search(r'CANCEL_TRACE=invoking_cancel\|class=([^\r\n|]+\.'+re.escape(instance[2])+r')\|active=[1-9]\d*'
            r'\|[^\r\n]*\|instance='+re.escape(instance[2]+' '+instance[3])+r'(?:\r?\n|$)',segment[instance.end():])
        if invoke:
            tail=segment[instance.end()+invoke.end():]
            cleared=re.search(r'CANCEL_TRACE=activity_cleared\|class='+re.escape(invoke[1])+r'\|active=0\|',tail)
            if cleared:
                tail=tail[cleared.end():]
                result=tail.find('CANCEL_RESULT=true|active=0')
                cancelled=bool(result>=0 and restoration_result(tail[result:],'exit')['passed'])
    foreign=set(re.findall(r'KEY_SKILL_BEGIN=([^|\r\n]+)\|',segment))-{skill}
    if foreign or any(t in segment for t in ('state=FAULTED','PBZ_CONTROL_RESTORE:FAILED=','PBZ_CONTROL_LIFECYCLE:ISSUE_')):
        natural=None;cancelled=False
    return {'natural_completion':natural,'active_cancel_and_restoration':cancelled,
        'activation_instance_verified':observed,
        'ability_class_short':instance[2] if instance else None,'restoration':restoration_result(segment),
        'foreign_keyed_activations':sorted(foreign)}


def subtree_evidence(segment,skill,result,exact_class):
    """父能力实例及完整调度收尾必须属于同一动作；StopLogic结束父能力也可构成真实取消。"""
    if skill not in SUBTREE_NAMES:return result
    name=SUBTREE_NAMES[skill];expected=registered_subtree_class(skill)
    starts=list(re.finditer(r'COMBO_SCHEDULER_BEGIN=([^|\r\n]+)\|brain_tick=true\|outer_ai=false\|ai_tick=false\|limit=25',segment))
    active=re.search(r'KEY_SKILL_BEGIN='+re.escape(skill)+r'\|[^\r\n]*\|active=[1-9]\d*',segment)
    observed=re.search(r'COMBO_OBSERVED_ACTIVE='+re.escape(expected)+r'\|active=[1-9]\d*\|baseline=0',segment)
    valid=(exact_class==expected and len(starts)==1 and starts[0][1]==skill and active and observed
           and starts[0].start()<active.start() and starts[0].start()<observed.start()
           and result['activation_instance_verified']
           and result['ability_class_short']==name+'_C'and not result['foreign_keyed_activations']
           and not any(k in segment for k in ('state=FAULTED','PBZ_CONTROL_RESTORE:FAILED=','PBZ_CONTROL_LIFECYCLE:ISSUE_')))
    tail=segment[max(active.end(),observed.end()):]if active and observed else''
    natural_end=tail.find('COMBO_SCHEDULER_END=natural=true|all_grants_at_baseline=true|brain_tick=false')
    keyed_end=tail.find('KEY_SKILL_END='+skill+'|')
    if not(valid and 0<=natural_end<keyed_end):
        result['natural_completion']=None
    stop=tail.find('COMBO_TREE_STOP=');end=tail.find('COMBO_SCHEDULER_END=cancelled=true|all_grants_at_baseline=true|brain_tick=false')
    result['active_cancel_and_restoration']=bool(valid and 0<=stop<end and restoration_result(tail[end:],'exit')['passed'])
    result['scheduler_parent_verified']=bool(valid)
    return result


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def player_binding_verified(action,assembly,deployment):
    """普通入口按键需与部署快照及本轮实际注册同时一致。"""
    row=action.get('binding',{});skill=action.get('skill')
    try:expected=ability_for_slot(row.get('slot'))
    except (ValueError,TypeError):return False
    slot=row.get('slot')
    if not(deployment.get('player_entry') and not deployment.get('skill_lab')
           and expected==skill and row.get('skill')==skill):return False
    key=row.get('key')
    if not key or deployment.get('player_keymap',{}).get('skills',{}).get(slot)!=key:return False
    registrations=re.findall(r'PLAYER_BINDING=([^|\r\n]+)\|([^|\r\n]+)\|([^\r\n]+)',assembly)
    return [r for r in registrations if r[0]==slot]==[(slot,skill,key)]


def player_boss_id(assembly):
    from player_settings import BOSSES
    rows=re.findall(r'PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=([^\r\n]+)',assembly)
    assert len(rows)==1 and rows[0]in BOSSES,'one exact current player Boss assembly required'
    return rows[0]


def collect(session,player_entry=False):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    state=read(ROOT/'runtime'/('official-validation-'+session)/'state.json')
    work=Path(state['work']);assert state.get('restored') and work.name==session
    post=read(work/'postcheck.json')
    assert post['validation_state']==state['state_file'] and not post['formal_files_changed']
    assert not post['host_config_files_changed'] and post['host_registry_unchanged']
    assert post['research_box_empty'] and post['research_loader_removed']
    raw=(work/'UE4SS.log').read_bytes();text=raw.decode('utf-8',errors='replace')
    deployments=[read(p) for p in work.glob('control-lifecycle-deployment-*.json')]
    actions=read(work/('player-extra-skill-actions.json'if player_entry else'skill-lab-actions.json'))
    results=[]
    for action in actions:
        kind=('interrupt'if action['interrupt']else'cast')if player_entry else action['action']
        if kind=='next':continue
        assert action['state_file']==state['state_file']
        start=action['log_offset'];end=action.get('log_end')
        if end is None:
            assert action['lines'],'old action without interval end requires original lines'
            last=action['lines'][-1];end=text.index(last,start)+len(last)
        assert 0<=start<end<=len(text)
        segment=text[start:end]
        assert all(line in segment for line in action['lines'])
        stamp=re.search(r'\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)',segment);assert stamp
        began=datetime.fromisoformat(stamp[1]).replace(tzinfo=datetime.fromisoformat(action['at']).tzinfo)
        deployment=max((d for d in deployments if datetime.fromisoformat(d['at'])<=began),key=lambda d:d['at'])
        ready_prefix=text[:start].rsplit('PBZ_CONTROL_LIFECYCLE:DEFERRED_ACTOR=',1)[-1]
        if player_entry:
            assert player_binding_verified(action,ready_prefix,deployment),'player binding not confirmed by current deployment and registration'
        else:assert deployment['skill_lab']
        skill=action['skill']if player_entry else action['candidate_before_input'];result=analyze(segment,skill)
        short=result['ability_class_short']
        grants=re.findall(r'GRANTED_ABILITY=[^ ]+ ([^\r\n]+)',ready_prefix)
        exact=[p for p in grants if p.rsplit('.',1)[-1]==short] if short else []
        if skill in SUBTREE_NAMES:
            result=subtree_evidence(segment,skill,result,exact[0]if len(exact)==1 else None)
        result.update(skill=skill,action=kind,log_offset=start,log_end=end,
            boss_id=player_boss_id(ready_prefix)if player_entry else None,
            exact_granted_class=exact[0] if len(exact)==1 else None,
            module_source_sha256=deployment['module_source_sha256'],deployment_at=deployment['at'])
        assert not(result['natural_completion'] or result['active_cancel_and_restoration']) or len(exact)==1
        results.append(result)
    target=work/('player-skill-acceptance-evidence.json'if player_entry else'skill-acceptance-evidence.json')
    target.write_text(json.dumps({'session':session,'log_sha256':hashlib.sha256(raw).hexdigest(),
        'actions':results,'complete_mod':False},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(target),'actions':len(results),'natural':sum(bool(r['natural_completion']) for r in results),
        'cancelled':sum(r['active_cancel_and_restoration'] for r in results)},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('session');parser.add_argument('--player-entry',action='store_true')
    args=parser.parse_args();collect(args.session,args.player_entry)
