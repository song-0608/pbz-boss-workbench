"""用途：整理本轮真实按键、技能与镜头清理证据；只读取收尾后的日志，不更改验收字段。"""
import hashlib
import json
from pathlib import Path
import re
import sys
from control_action_evidence import cancellation_result, classify_stop, restoration_result, death_restoration_result
ROOT=Path(__file__).resolve().parents[1]

def read(path):return json.loads(path.read_text(encoding='utf-8'))

def main():
    owner=read(ROOT/'runtime/ahua-practice.json');state=read(Path(owner['state_file']))
    if owner['phase']!='closed' or not state.get('restored'):raise RuntimeError('Completed research session required')
    work=Path(state['work']);post=read(work/'postcheck.json')
    if post['validation_state']!=owner['state_file'] or post['formal_files_changed'] or not post['research_box_empty']:
        raise RuntimeError('Matching formal-file and isolation postcheck required')
    log=work/'UE4SS.log';text=log.read_text(encoding='utf-8',errors='replace')
    actions=read(work/'expanded-actions.json')if(work/'expanded-actions.json').exists()else[]
    # 用途：只产生新的审阅结论，不修改原始失败记录或技能验收开关。
    reviewed=[]
    for index, action in enumerate(actions):
        end=actions[index+1]['log_offset'] if index+1<len(actions) else len(text)
        segment=text[action['log_offset']:end]
        skill=action.get('interrupted_skill')
        passed=action.get('marker_observed') is True
        if skill: passed=passed and cancellation_result(segment,skill)
        restore=None
        if skill or action['action'] in ('exit','pause','death','death_skill08'):
            label={'pause':'menu_exit','death':'auto_exit','death_skill08':'auto_exit'}.get(action['action'],'exit')
            restore=(death_restoration_result(segment,action.get('native_death_trial',False),
                     'skill_08'if action['action']=='death_skill08'else None)
                     if action['action']in ('death','death_skill08')else restoration_result(segment,label))
            passed=passed and restore['passed']
        reviewed.append({'action':action['action'],'passed':passed,'completion_kind':classify_stop(segment),
                         'restoration':restore})
    samples=[]
    pattern=r'KEY_SKILL_END=(\w+)\|peak=(\d+)\|active=(\d+)\|natural=(true|false)\|health_before=([\d.-]+)\|health_after=([\d.-]+)\|distance=([\d.eE+-]+)'
    for skill,peak,active,natural,before,after,distance in re.findall(pattern,text):
        samples.append({'id':skill,'active_peak':int(peak),'active_after':int(active),'natural_finish':natural=='true',
            'health_before':float(before),'health_after':float(after),'damage_observed':float(before)>float(after),'position_delta':float(distance)})
    keys=re.findall(r'PLAYER_BINDING=(\w+)\|(\w+)\|([\w_]+)',text)
    faults=[line for line in text.splitlines()if any(token in line for token in ('state=FAULTED','ISSUE_','PBZ_CONTROL_RESTORE:FAILED='))]
    report={'session':str(work),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),
       'deployment':read(work/'control-lifecycle-deployment.json'),'actions':actions,'reviewed_actions':reviewed,'samples':samples,
       'deployment_history':[read(p)for p in sorted(work.glob('control-lifecycle-deployment-*.json'))],
       'actual_bindings':[{'slot':s,'skill':i,'key':k}for s,i,k in keys],
       'camera_engine_cleanup_count':text.count('CAMERA_CLEANUP_ENGINE_VERIFIED=true'),
       'old_observers_stopped':text.count('CAMERA_OBSERVATION_STOPPED=session ended'),
       'original_player_exit_deltas':re.findall(r'ORIGINAL_PLAYER_POSITION_DELTA=([^\r\n]+)',text),
       'original_player_new_active':re.findall(r'ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=(\d+)',text),
       'faults':faults,
       'initialization_rejections':[line for line in text.splitlines()if any(t in line for t in (
           'INITIALIZATION_ATTEMPT_REJECTED=','PREREQUISITE_NOT_READY='))],
       'native_owned_disposal_count':text.count('PBZ_CONTROL_RESTORE:OWNED_DISPOSAL_VERIFIED=true'),
       'native_death_disposal_verified':any(a['restoration']and a['restoration'].get('death_kind')=='native_owned_disposal'
           and a['passed']for a in reviewed),
       'native_death_requested_during_active_skill08_verified':any(a['action']=='death_skill08'and a['passed']
           and a['restoration']and a['restoration'].get('active_skill_at_request')=='skill_08'for a in reviewed),
       'active_skill_at_object_disposal_verified':False,
       'hp_depletion_death_verified':any(a['restoration']and a['restoration'].get('death_kind')=='health_depleted'
           and a['passed']for a in reviewed),
       'retirement_history':[read(p)for p in sorted(work.glob('same-process-retirement-*.json'))],
       'formal_files_changed':post['formal_files_changed'],'research_box_empty':post['research_box_empty'],
       'complete_boss_mod':False,'automatically_released':False}
    target=work/'controls-runtime-evidence.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(target),'samples':samples,'camera_cleanup_count':report['camera_engine_cleanup_count'],
        'fault_count':len(faults),'passed_actions':[a['action']for a in reviewed if a['passed']]},ensure_ascii=False,indent=2))

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
