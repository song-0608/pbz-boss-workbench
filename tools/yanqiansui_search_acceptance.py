"""Versioned missing-only runner; retain the frozen integration and source gates."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from mod_installation import ROOT,MANIFEST,validate_package,digest
from build_yanqiansui_search_candidate import expected,verify as verify_candidate,MODULE,BASE
from four_boss_integration_workflow import modules,verify as verify_workflow,verify_current as verify_base

SOURCES=('tools/yanqiansui_search_acceptance.py','tests/test_yanqiansui_search_acceptance.py')


def verify_current(current,root=ROOT):
    _,_,_,_,identifier=expected(root)
    target=root/'runtime/release-candidates'/identifier
    manifest=verify_candidate(target,root)
    assert current==modules(manifest),'Exact bounded-search deployment required'
    base=validate_package(root/'runtime/release-candidates'/BASE)
    before=modules(base)
    assert set(current)==set(before)
    assert {n for n,d in current.items()if before[n]!=d}=={MODULE.removeprefix('PBZBossControl/Scripts/')}
    # Ability execution, actor grants, camera, input, performance and restoration
    # are byte-identical. Only a still-unaccepted terrain search is replaced.
    ordinary,sources=verify_base(before,root)
    sources=dict(sources,**manifest['search_sources'])
    sources.update({n:digest(root/n)for n in SOURCES})
    sources[(target/MANIFEST).relative_to(root).as_posix()]=digest(target/MANIFEST)
    return ordinary,sources


def run(workflow,finish=False):
    import test_four_boss_integration as frozen
    verify_workflow(workflow)
    frozen.verify_current=verify_current
    return frozen.main(workflow,'073_yanqiansui',finish_world=finish)


def collect(session,workflow):
    import collect_four_boss_integration as frozen
    verify_workflow(workflow)
    frozen.verify_current=verify_current
    return frozen.collect(session,workflow,'073_yanqiansui')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('verify','run','finish-world','collect'))
    p.add_argument('--workflow',type=Path,required=True);p.add_argument('--session');a=p.parse_args()
    workflow=a.workflow.resolve()
    if a.action=='verify':
        verify_workflow(workflow)
        _,_,_,_,identifier=expected()
        target=ROOT/'runtime/release-candidates'/identifier
        _,sources=verify_current(modules(verify_candidate(target)))
        print(json.dumps({'passed':True,'candidate':str(target),'sources':sources,
            'game_started':False,'ordinary_movement_world_accepted':False},ensure_ascii=False))
    elif a.action=='collect':
        assert a.session;print(json.dumps(collect(a.session,workflow),ensure_ascii=False))
    else:
        raise SystemExit(run(workflow,a.action=='finish-world'))
