"""离线编排缺项，再于新装配集中执行；不启动游戏、不续期、不重试。"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import ahua_practice as practice
from mod_installation import ROOT, active_mod_root
from run_ahua_milestone_acceptance import validate_start
from collect_release_readiness import collect
from ahua_catalog_plan import make_plan


def main():
    parser=argparse.ArgumentParser();parser.add_argument('batch',choices=('a','b'))
    parser.add_argument('--plan-only',action='store_true',help='仅从已关闭且同源码的实证编排缺项，不操作游戏')
    args=parser.parse_args()
    source=active_mod_root()
    plan=make_plan(collect(source.parent),args.batch)
    if args.plan_only:
        target=ROOT/'evidence/adaptation'/('ahua-catalog-plan-'+args.batch+'.json')
        target.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'plan':str(target),'actions':plan['action_count'],
            'phases':{p['name']:[a['request']for a in p['actions']]for p in plan['phases']},
            'game_started':False},ensure_ascii=False,indent=2))
        return 0
    if not plan['action_count']:
        print('本批没有缺失动作，不发送按键。',flush=True);return 0
    owner,state=practice.owned_session();path=practice.log_path(state);work=Path(state['work'])
    text=path.read_text(encoding='utf-8',errors='replace')
    validate_start(owner,state,text[owner['log_offset']:],time.time())
    modules={p.relative_to(source/'Scripts').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
             for p in (source/'Scripts').rglob('*.lua') if p.name!='main.lua'}
    deployment=max(work.glob('control-lifecycle-deployment-*.json'),key=lambda p:p.stat().st_mtime_ns)
    if practice.read(deployment)['module_source_sha256']!=modules:
        raise RuntimeError('Live deployment differs from immutable installed source')
    if sorted(owner['actual_bindings'],key=lambda r:r['slot'])!=sorted(plan['expected_bindings'],key=lambda r:r['slot']):
        raise RuntimeError('Planned bindings differ from current live deployment')
    if plan['module_source_sha256']!=modules:
        raise RuntimeError('Offline missing-evidence plan differs from installed source')
    if any(practice.read(p).get('assembly_log_offset')==owner['log_offset'] for p in work.glob('catalog-batch-*.json')):
        raise RuntimeError('One catalog batch per assembly; preserve the existing result')
    report={'at':datetime.now().astimezone().isoformat(),'state_file':state['state_file'],
            'batch':args.batch,'plan':plan,'assembly_log_offset':owner['log_offset'],'module_source_sha256':modules,'phases':[],
            'game_launch_requested':False,'game_restart_requested':False,'passed':False}
    target=work/('catalog-batch-'+args.batch+'-'+datetime.now().strftime('%H%M%S-%f')+'.json')
    def save():target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        for phase in plan['phases']:
            skills=[row['request'] for row in phase['actions']]
            if not skills:continue
            interrupt=phase['interrupt'];label=phase['name']
            print('全目录补验 '+args.batch.upper()+'：'+label,flush=True)
            run=subprocess.run([sys.executable,str(ROOT/'tools/test_player_skill_batch.py'),*skills,
                                *(['--interrupt'] if interrupt else [])],cwd=ROOT,timeout=510,
                               creationflags=subprocess.CREATE_NO_WINDOW,capture_output=True,
                               text=True,encoding='utf-8',errors='replace')
            print(run.stdout,flush=True)
            if run.stderr:print(run.stderr,file=sys.stderr,flush=True)
            report['phases'].append({'name':label,'skills':skills,'exit_code':run.returncode});save()
            if run.returncode:raise RuntimeError(label+' failed; no retry and no game restart')
        report['passed']=True
    except Exception as error:
        report['error']=str(error)
    finally:
        final=(path if path.exists()else work/'UE4SS.log').read_text(encoding='utf-8',errors='replace')
        report['log_end']=len(final);report['log_prefix_sha256']=hashlib.sha256(final.encode('utf-8')).hexdigest()
        save();print(json.dumps({'report':str(target),'passed':report['passed'],'error':report.get('error')},ensure_ascii=False),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
