"""Compare complete game-thread timing windows from two closed, protected sessions."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import statistics

ROOT=Path(__file__).resolve().parents[1]


def windows(text):
    result=[]
    for line in text.splitlines():
        match=re.search(r'PBZ_PERF:WINDOW=state=(\w+)\|wall=([\d.]+)\|frames=(\d+)\|callback_ms=([\d.]+)\|max_ms=([\d.]+)\|at=(\d+)',line)
        if match:
            state,wall,frames,mean,maximum,at=match.groups()
            result.append(dict(state=state,wall=float(wall),frames=int(frames),callback_ms=float(mean),max_ms=float(maximum),at=int(at),costs={}))
        else:
            cost=re.search(r'PBZ_PERF:COST=([\w.]+)\|calls=(\d+)\|ms=([\d.]+)',line)
            if cost and result:
                name,count,ms=cost.groups();result[-1]['costs'][name]={'calls':int(count),'ms':float(ms)}
    return result


def summarize(rows):
    # Mixed enter/exit windows cannot stand in for steady ACTIVE performance.
    active=[r for r in rows if r['state']=='ACTIVE' and 4.9<=r['wall']<=6
            and r['frames']>0 and r['costs'].get('bridge.world_boundary',{}).get('calls')==r['frames']
            and r['costs'].get('bridge.context',{}).get('calls')==r['frames']]
    if len(active)<3:raise RuntimeError('At least three complete steady ACTIVE windows required')
    frames=sum(r['frames'] for r in active);elapsed=sum(r['wall'] for r in active)
    return {'windows':len(active),'seconds':elapsed,'frames':frames,'game_thread_ticks_per_second':frames/elapsed,
            'callback_mean_ms':sum(r['callback_ms']*r['frames'] for r in active)/frames,
            'callback_worst_ms':max(r['max_ms'] for r in active),
            'lookup_ms_per_frame':sum(r['costs'].get('find_exact',{}).get('ms',0)for r in active)/frames,
            'median_window_ticks_per_second':statistics.median(r['frames']/r['wall']for r in active),
            'selected_windows':active}


def load(session):
    if not re.fullmatch(r'\d{8}-\d{6}',session):raise ValueError('Exact session required')
    work=ROOT/'evidence/official-validation'/session
    state=json.loads((ROOT/'runtime'/('official-validation-'+session)/'state.json').read_text(encoding='utf-8'))
    post=json.loads((work/'postcheck.json').read_text(encoding='utf-8'))
    if not(state.get('restored') and post['validation_state']==state['state_file'] and not post['formal_files_changed']
           and not post['host_config_files_changed'] and post['host_registry_unchanged']
           and post['research_box_empty'] and post['research_loader_removed']):
        raise RuntimeError('Closed session and complete postcheck required')
    deployment=json.loads((work/'control-lifecycle-deployment.json').read_text(encoding='utf-8'))
    if not(deployment.get('performance_profile') and deployment.get('player_entry')):
        raise RuntimeError('Explicit read-only performance probe on ordinary player entry required')
    raw=(work/'UE4SS.log').read_bytes();text=raw.decode('utf-8',errors='replace')
    settings=(work/'performance-loader-settings.ini').read_bytes()
    expected=next(r['sha256']for r in state['ue4ss_loader_manifest']if r['physical_path'].endswith('UE4SS-settings.ini'))
    if hashlib.sha256(settings).hexdigest()!=expected:raise RuntimeError('Exact deployed loader configuration required')
    if any(t in text for t in ('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_','idle_world_check success=false')):
        raise RuntimeError('Runtime fault must be resolved before performance delivery')
    return {'session':session,'log_sha256':hashlib.sha256(raw).hexdigest(),
            'loader_settings_sha256':expected,'loader_settings':settings.decode('utf-8'),
            'module_source_sha256':deployment['module_source_sha256'],
            'assembly_source_sha256':deployment['assembly_source_sha256'],'summary':summarize(windows(text))}


def compare(before,after):
    if before['module_source_sha256']!=after['module_source_sha256'] or before['assembly_source_sha256']!=after['assembly_source_sha256']:
        raise RuntimeError('Identical gameplay Lua required for loader-only comparison')
    if 'loader_settings'in before or 'loader_settings'in after:
        old,new=before['loader_settings'],after['loader_settings']
        if old.count('bUseUObjectArrayCache = false')!=1 or old.replace('bUseUObjectArrayCache = false','bUseUObjectArrayCache = true')!=new:
            raise RuntimeError('Only native object cache flag may differ in the controlled comparison')
    a,b=before['summary'],after['summary']
    improvement=1-b['callback_mean_ms']/a['callback_mean_ms']
    return {'passed':improvement>=0.9 and b['callback_mean_ms']<5 and b['game_thread_ticks_per_second']>=50,
            'callback_cost_reduction_percent':100*improvement,
            'tick_rate_ratio':b['game_thread_ticks_per_second']/a['game_thread_ticks_per_second'],
            'metric':'one callback per game-thread EngineTick; not GPU presentation/FPS telemetry',
            'baseline':before,'fixed':after}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('baseline');parser.add_argument('fixed');args=parser.parse_args()
    result=compare(load(args.baseline),load(args.fixed));result['at']=datetime.now().astimezone().isoformat()
    target=ROOT/'evidence/adaptation/ahua-performance-comparison.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items()if k not in('baseline','fixed')},ensure_ascii=False,indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
