"""Retain cleaned clearance refusals while replaying one successful skill assembly."""
from datetime import datetime
import inspect
import argparse
import json
from pathlib import Path
import re
import types

import collect_boss_skill_session as original
import boss_skill_expansion as expansion
from boss_adaptation_workflow import ROOT,sha


def refused_before_extra_target(text):
    parts=text.split('PBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT=')[1:]
    assert len(parts)==3, 'Exactly three cleaned clearance refusals required'
    for part in parts:
        assert 'no verified 9m same-level movement clearance within 192 navigation queries' in part
        assert all('OWNED_DESTROY_VERIFIED='+n+'|engine_unusable=true' in part
                   for n in ('boss','boss_controller','target','target_controller'))
        assert not any(t in part for t in ('enter success=true','INTERACTIVE_READY=',
            'PLAYER_ENTRY_READY=','state=FAULTED','ISSUE_','DESTROY_SKIPPED'))
    assert 'PREREQUISITE_RETRY_SAFE=true' in parts[-1]
    assert 'END=initialization rejected before takeover; original player restoration verified' in parts[-1]


def select_deployment(paths,raw,milestone):
    if len(paths)==1:return paths,[]
    ordered=sorted(paths,key=lambda p:expansion.read(p)['at'])
    cutoff=datetime.fromisoformat(milestone['started_at'])
    assert all(datetime.fromisoformat(expansion.read(p)['at'])<cutoff for p in ordered)
    chosen=ordered[-1];current=expansion.read(chosen)
    rows=list(re.finditer(r'^\[([^]]+)\]',raw,re.M))
    for index,path in enumerate(ordered[:-1]):
        previous=expansion.read(path);following=expansion.read(ordered[index+1])
        for key in ('boss_candidate','developer_bundle','module_source_sha256','assembly_source_sha256'):
            assert previous[key]==current[key], 'Retry changed the exact skill assembly'
        start=datetime.fromisoformat(previous['at']);end=datetime.fromisoformat(following['at'])
        positions=[row.start() for row in rows
                   if start.replace(tzinfo=None)<=datetime.fromisoformat(row[1])<end.replace(tzinfo=None)]
        assert positions and max(positions)<milestone['log_offset']
        tail=[row.start() for row in rows if row.start()>max(positions)]
        segment=raw[min(positions):min(tail) if tail else len(raw)]
        refused_before_extra_target(segment)
    return [chosen],ordered[:-1]


def collect(session,root=ROOT):
    work=root/'evidence/official-validation'/session
    attempts=list(work.glob('control-lifecycle-deployment-*.json'))
    ids=[expansion.read(p).get('boss_candidate') for p in attempts]
    if len(ids)==len(set(ids)):
        return original.collect(session,root)
    source=inspect.getsource(original.collect)
    old="        assert len(deployments)==1,'One exact expansion assembly per Boss required'"
    assert source.count(old)==1
    source=source.replace(old,"        deployments,rejected=select_deployment(deployments,raw,milestone)\n"
        "        for path in rejected:sources[path.relative_to(root).as_posix()]=sha(path)\n"+old)
    module=types.ModuleType('closed_clearance_retry_collector')
    module.__dict__.update(vars(original));module.select_deployment=select_deployment
    exec(compile(source,__file__+':retained_refusals','exec'),module.__dict__)
    result=module.collect(session,root)
    result['sources']['tools/collect_boss_skill_retry_session.py']=sha(root/'tools/collect_boss_skill_retry_session.py')
    result['cleaned_clearance_refusals_retained']=True
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('session')
    parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    result=collect(args.session);path=ROOT/'evidence/official-validation'/args.session/'boss-skill-session.json'
    if args.verify:assert expansion.read(path)==result
    else:
        assert not path.exists(),'Preserve collected attempt';original.write_json(path,result)
    print(json.dumps(dict(report=str(path),all_twelve_accepted=result['all_twelve_accepted'],
        bosses=[dict(id=r['id'],passed=r['all_four_accepted']) for r in result['bosses']]),ensure_ascii=False))
