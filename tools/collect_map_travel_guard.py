"""仅验收LoadMap前同步恢复这一阶段，不把原始OpenLevel失败改写为完整切图成功。"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from control_action_evidence import control_identity,restoration_result
from mod_installation import ROOT,digest


def proof(segment):
    pre=re.search(r'MAP_TRAVEL_PRE_ACTIVE=([^|\r\n]+)\|address=(\d+)\|skill=nil',segment)
    begin=re.search(r'ACTIVE_WORLD_TRIAL_BEGIN=([^|\r\n]+)\|address=(\d+)',segment)
    requested=segment.find('ACTIVE_WORLD_TRIAL_REQUESTED=true')
    done=segment.find('MAP_TRAVEL_RESTORED_BEFORE_LOAD=true')
    identity=control_identity(segment[:pre.start()]if pre else'')
    restored=restoration_result(segment[:done]if done>=0 else'','auto_exit','map travel')
    result={'restoration':restored,'before_identity':identity,
        'same_captured_world':bool(pre and begin and identity and pre.groups()==begin.groups()
            and identity['world_id'].split('|',1)[1]==pre[1]+'|'+pre[2]),
        'ordered_preload_restoration':bool(pre and begin and 0<=begin.start()<requested<pre.start()<done),
        'fault_absent_before_load':done>=0 and not any(t in segment[:done]for t in
            ('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_','PBZ_CONTROL_RESTORE:FAILED=')),
        'scope':'只证明真实LoadMap pre-hook在旧World有效时同步恢复；不是完整跨图闭环',
        'full_travel_lifecycle_verified':False}
    result['passed']=bool(restored['passed']and all(result[k]for k in
        ('same_captured_world','ordered_preload_restoration','fault_absent_before_load')))
    return result


def collect(session):
    if not re.fullmatch(r'\d{8}-\d{6}',session):raise ValueError('Invalid session')
    state=json.loads((ROOT/'runtime'/('official-validation-'+session)/'state.json').read_text(encoding='utf-8'))
    work=Path(state['work']);post=json.loads((work/'postcheck.json').read_text(encoding='utf-8'))
    assert state.get('restored')and work.name==session and state['state_file']==post['validation_state']
    assert not post['formal_files_changed']and not post['host_config_files_changed']and post['host_registry_unchanged']
    assert post['research_box_empty']and post['research_loader_removed']
    raw=(work/'UE4SS.log').read_bytes();text=raw.decode('utf-8',errors='replace');results=[]
    for path in sorted(work.glob('active-world-actions-*.json')):
        witness=json.loads(path.read_text(encoding='utf-8'))
        assert witness['state_file']==state['state_file']
        start,end=witness['log_offset'],witness['log_end'];assert 0<=start<end<=len(text)
        assert hashlib.sha256(text[:end].encode('utf-8')).hexdigest()==witness['log_prefix_sha256']
        deployment=json.loads((work/witness['deployment_file']).read_text(encoding='utf-8'))
        assert deployment['player_entry']and deployment['scene_transition_trial']
        result=proof(text[start:end]);result.update(witness_file=path.name,witness_sha256=digest(path),
            module_source_sha256=deployment['module_source_sha256'],
            full_diagnostic_passed=witness['passed'],full_diagnostic_error=witness.get('error'))
        results.append(result)
    report={'session':session,'passed':any(r['passed']for r in results),'results':results,
        'log_sha256':hashlib.sha256(raw).hexdigest(),'complete_mod':False,'full_travel_lifecycle_verified':False}
    target=work/'map-travel-preload-acceptance.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(target),'preload_passed':report['passed'],'full_travel_lifecycle_verified':False},ensure_ascii=False))
    return 0 if report['passed']else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('session');raise SystemExit(collect(parser.parse_args().session))
