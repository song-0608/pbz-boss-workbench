"""在一轮已装配试验台顺序验收明确候选；所有输入仍由原唯一输入工具执行。"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import ahua_practice as practice
import research_game_menu as menu
from control_action_evidence import restoration_result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('candidates',nargs='+')
    parser.add_argument('--interrupt',action='store_true')
    args=parser.parse_args()
    owner,state=practice.owned_session()
    assert owner['phase']=='armed' and owner['skill_lab']
    path=practice.log_path(state)
    initial=path.read_text(encoding='utf-8',errors='replace')[owner['log_offset']:]
    available=re.findall(r'LAB_CANDIDATE_AVAILABLE=([\w_]+)',initial)
    assert len(set(args.candidates))==len(args.candidates)<=24 and set(args.candidates)<=set(available)
    environment=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
    results=[]
    for candidate in args.candidates:
        current=path.read_text(encoding='utf-8',errors='replace')[owner['log_offset']:]
        if any(t in current for t in ('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_','INTERACTIVE_END=')):
            break
        if min(state['deadline_unix'],state['control_probe_expires_at']-20)-time.time()<100:
            print('Leaving cleanup margin; no further skill inputs.',flush=True);break
        if args.interrupt and results and results[-1]['exit_code']==0:
            entered=subprocess.run([sys.executable,str(practice.ROOT/'tools/test_ahua_expanded_runtime.py'),'enter'],
                env=environment,capture_output=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
            if entered.returncode:
                print('Reentry failed; no further skill inputs.',flush=True);break
        print(('Cancel ' if args.interrupt else 'Cast ')+candidate,flush=True)
        run=subprocess.run([sys.executable,str(practice.ROOT/'tools/test_ahua_skill_lab.py'),
            'interrupt' if args.interrupt else 'cast','--candidate',candidate],env=environment,
            capture_output=True,timeout=150,creationflags=subprocess.CREATE_NO_WINDOW)
        row={'candidate':candidate,'exit_code':run.returncode,
             'output':run.stdout.decode('utf-8',errors='replace'),'stderr':run.stderr.decode('utf-8',errors='replace')}
        results.append(row)
        print(candidate+': '+('observed' if run.returncode==0 else 'rejected or incomplete'),flush=True)
        rejected_without_activation = (re.search(r'lab_cast success=false state=ACTIVE reason=(?:game state/cooldown rejected skill|target rejected: [^\r\n]+|target lock unavailable|target no longer available)',row['output'])
            and 'KEY_SKILL_BEGIN=' not in row['output'] and 'state=FAULTED' not in row['output'])
        if run.returncode and not rejected_without_activation:
            break
    ending_offset=len(path.read_text(encoding='utf-8',errors='replace'))
    cleanup_error=None
    if not args.interrupt or not results or results[-1]['exit_code']:
        try:
            menu.click(0,0,2560,1600,'control_exit')
            until=time.monotonic()+6
            while time.monotonic()<until:
                tail=path.read_text(encoding='utf-8',errors='replace')[ending_offset:]
                if restoration_result(tail,'exit')['passed']:
                    break
                time.sleep(.15)
            else:cleanup_error='Complete F10 restoration readback missing'
        except RuntimeError as error:
            cleanup_error=str(error)
    target=Path(state['work'])/('skill-batch-cancel.json' if args.interrupt else 'skill-batch-cast.json')
    target.write_text(json.dumps({'state_file':state['state_file'],'requested':args.candidates,'results':results,'cleanup_error':cleanup_error},
        ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (target.with_stem(target.stem+'-'+str(time.time_ns()))).write_bytes(target.read_bytes())
    print('Saved '+str(target),flush=True)
    return 0 if not cleanup_error and len(results)==len(args.candidates) and all(r['exit_code']==0 for r in results) else 1


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
