"""同线程活动技能销毁请求与失效对象恢复证据；不声称销毁后仍在读活动实例。"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from control_action_evidence import restoration_result

ROOT=Path(__file__).resolve().parents[1]


def proof(text):
    active=re.search(r'OWNED_DISPOSAL_ACTIVE_INSTANCE=skill_08\|active=([1-9]\d*)\|object=([^\r\n]+)',text)
    instance=re.search(r'SKILL_INSTANCE=skill_08\|active=true\|cancelable=(?:true|false)\|object=([^\r\n]+)',text)
    boss=re.search(r'CONTROL_PARTICIPANT=boss\|([^|\r\n]+)\|address=(\d+)\|class=',text)
    request=re.search(r'OWNED_DISPOSAL_REQUEST=([^|\r\n]+)\|address=(\d+)',text)
    end=text.find('OWNED_DISPOSAL_ENGINE_UNUSABLE=true')
    retired=text.find('PBZ_CONTROL_RESTORE:OWNED_DISPOSAL_VERIFIED=true',end)
    restored=restoration_result(text,'auto_exit','owned boss disposed')
    result={'exact_active_instance':bool(active and instance and active[2]==instance[1] and 'Default__'not in active[2]),
        'exact_owned_actor':bool(boss and request and boss.groups()==request.groups()),
        'ordered_synchronous_disposal':bool(instance and active and request and instance.end()<active.start()<request.start()<end<retired),
        'restoration':restored,'active_count_at_destroy_request':int(active[1])if active else None,
        'post_disposal_spec_reads_claimed':False}
    result['passed']=bool(all(result[k]for k in('exact_active_instance','exact_owned_actor','ordered_synchronous_disposal'))
        and restored['passed'] and text.find('CONTROLLED_BOSS_DISPOSED=true',retired)>retired
        and not any(k in text for k in('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_','PBZ_CONTROL_RESTORE:FAILED=')))
    return result


def collect(session):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    state=json.loads((ROOT/'runtime'/('official-validation-'+session)/'state.json').read_text(encoding='utf-8'))
    work=Path(state['work']);assert state.get('restored')and work.name==session
    post=json.loads((work/'postcheck.json').read_text(encoding='utf-8'))
    assert post['validation_state']==state['state_file']and not post['formal_files_changed']
    assert not post['host_config_files_changed']and post['host_registry_unchanged']
    assert post['research_box_empty']and post['research_loader_removed']
    witness=json.loads((work/'active-disposal-actions.json').read_text(encoding='utf-8'))
    assert witness['state_file']==state['state_file']
    raw=(work/'UE4SS.log').read_bytes();text=raw.decode('utf-8',errors='replace')
    start,end=witness['log_offset'],witness['log_end'];assert 0<=start<end<=len(text)
    deployment=json.loads((work/witness['deployment_file']).read_text(encoding='utf-8'))
    assert deployment['active_skill_disposal_trial']and not deployment['player_entry']
    result=proof(text[start:end]);result.update(session=session,log_sha256=hashlib.sha256(raw).hexdigest(),
        module_source_sha256=deployment['module_source_sha256'],complete_mod=False)
    target=work/'active-disposal-evidence.json';target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(target),'passed':result['passed']},ensure_ascii=False));return 0 if result['passed']else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('session');raise SystemExit(collect(parser.parse_args().session))
