"""Exact three-profile registry; reuse only unchanged native ability execution."""
import argparse
import json
from pathlib import Path
from mod_installation import ROOT,MANIFEST,digest,validate_package
from build_youlong_workbench_candidate import expected,verify as verify_candidate,BASE,SOURCES,REGISTRY,PREVIEW
from four_boss_integration_workflow import modules,verify as verify_workflow
from four_boss_ordinary_reuse import verify as verify_ordinary


def verify_current(current,root=ROOT):
    _,_,_,_,identifier=expected(root)
    candidate=root/'runtime/release-candidates'/identifier
    manifest=verify_candidate(candidate,root)
    assert current==modules(manifest),'Exact three-profile deployment required'
    base=validate_package(root/'runtime/release-candidates'/BASE);before=modules(base)
    assert set(current)==set(before)
    assert {n for n,d in current.items()if before[n]!=d}=={
        REGISTRY.removeprefix('PBZBossControl/Scripts/'),PREVIEW.removeprefix('PBZBossControl/Scripts/')}
    ordinary,sources=verify_ordinary(before,root)
    sources=dict(sources,**{n:digest(root/n)for n in SOURCES})
    sources[(candidate/MANIFEST).relative_to(root).as_posix()]=digest(candidate/MANIFEST)
    return ordinary,sources


def collect(session,workflow):
    import collect_four_boss_world_missing as frozen
    verify_workflow(workflow)
    frozen.verify=verify_current
    return frozen.collect(session,workflow)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('verify','collect'))
    p.add_argument('--workflow',type=Path,required=True);p.add_argument('--session');a=p.parse_args()
    workflow=a.workflow.resolve();verify_workflow(workflow)
    if a.action=='collect':
        assert a.session;print(json.dumps(collect(a.session,workflow),ensure_ascii=False))
    else:
        _,_,_,_,identifier=expected();target=ROOT/'runtime/release-candidates'/identifier
        actions,sources=verify_current(modules(verify_candidate(target)))
        print(json.dumps({'passed':True,'candidate':str(target),'ordinary_actions_reparsed':len(actions),
            'sources':sources,'exact_registry_world_accepted':False,'game_started':False},ensure_ascii=False))
