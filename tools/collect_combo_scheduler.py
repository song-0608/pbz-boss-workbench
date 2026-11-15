"""保存指定已关闭研究会话的连招调度证据；失败不改写、不自动开放玩家技能。"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def collect(session):
    if not re.fullmatch(r'\d{8}-\d{6}',session):raise ValueError('Exact session directory required')
    state=json.loads((ROOT/'runtime'/('official-validation-'+session)/'state.json').read_text(encoding='utf-8'))
    work=Path(state['work'])
    if not state.get('restored')or work.name!=session:raise RuntimeError('Matching closed research session required')
    post=json.loads((work/'postcheck.json').read_text(encoding='utf-8'))
    if (post['validation_state']!=state['state_file']or post['formal_files_changed']or post['host_config_files_changed']
            or not post['research_box_empty']or not post['research_loader_removed']or not post['host_registry_unchanged']):
        raise RuntimeError('Matching clean teardown required')
    raw=(work/'UE4SS.log').read_bytes();text=raw.decode('utf-8',errors='replace')
    deployments=[json.loads(p.read_text(encoding='utf-8'))for p in sorted(work.glob('control-lifecycle-deployment-*.json'))]
    if not any(d.get('combo_scheduler_trial')is True for d in deployments):raise RuntimeError('Explicit deployed scheduler scope required')
    attempts=[]
    for index,segment in enumerate(text.split('PBZ_CONTROL_LIFECYCLE:COMBO_SCHEDULER_BEGIN=')[1:],1):
        ended=re.search(r'KEY_SKILL_END=attack_01\|peak=(\d+)\|active=(\d+)\|natural=(true|false)\|health_before=([\d.-]+)\|health_after=([\d.-]+)',segment)
        natural=bool(ended and int(ended[1])>0 and int(ended[2])==0 and ended[3]=='true'
            and 'COMBO_SCHEDULER_END=natural=true|all_grants_at_baseline=true|brain_tick=false'in segment)
        active=bool(re.search(r'KEY_SKILL_BEGIN=attack_01\|[^\r\n]*\|active=[1-9]\d*',segment))
        cancelled=bool(active and 'COMBO_SCHEDULER_END=cancelled=true|all_grants_at_baseline=true|brain_tick=false'in segment
            and 'exit success=true state=OFF'in segment and 'ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0'in segment)
        attempts.append({'index':index,'parent_observed_active':active,'natural_completion':natural,
            'damage_observed':bool(natural and float(ended[4])>float(ended[5])),'active_exit_verified':cancelled,
            'observed_abilities':sorted(set(re.findall(r'COMBO_OBSERVED_ACTIVE=([^|\r\n]+)',segment))),
            'scheduler_tick_states':re.findall(r'PBZ_COMBO_SCHEDULER:STATE=([^\r\n]+)',segment),
            'diagnostics':[line for line in segment.splitlines()if any(k in line for k in (
                'COMBO_', 'PBZ_REMOTE_VERIFY', 'state=FAULTED','CANCEL_RESULT=false','KEY_SKILL_END=attack_01'))]})
    result={'at':datetime.now().astimezone().isoformat(),'session':session,'source_log_sha256':hashlib.sha256(raw).hexdigest(),
        'attempts':attempts,'deployment_sources':deployments,'formal_files_changed':[], 'research_box_empty':True,
        'default_player_attack_unlocked':False,'complete_mod':False}
    target=work/'combo-scheduler-runtime-evidence.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(target),'attempts':[{k:v for k,v in a.items()if k not in ('diagnostics',)}for a in attempts]},ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('session');collect(parser.parse_args().session)
