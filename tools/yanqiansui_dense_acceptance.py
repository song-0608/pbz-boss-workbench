"""Keep ordinary integration gates; accept only the exact denser terrain module."""
import argparse
import json
from pathlib import Path
from mod_installation import ROOT, MANIFEST, digest
from four_boss_integration_workflow import modules, verify as verify_workflow
from build_yanqiansui_dense_candidate import expected, verify as verify_candidate
from build_yanqiansui_terrain_candidate import verify as verify_base, CORE
from yanqiansui_terrain_acceptance import verify_current as verify_previous


def verify_current(current,root=ROOT):
    target=root/'runtime/release-candidates'/expected(root)[-1]
    manifest=verify_candidate(target,root)
    assert current==modules(manifest),'Exact denser terrain deployment required'
    base_path=root/'runtime/release-candidates'/manifest['dense_search_base']
    before=modules(verify_base(base_path,root))
    assert set(current)==set(before)
    assert {n for n in before if current[n]!=before[n]}=={CORE.removeprefix('PBZBossControl/Scripts/')}
    actions,sources=verify_previous(before,root)
    sources.update(manifest['dense_search_sources'])
    sources[(target/MANIFEST).relative_to(root).as_posix()]=digest(target/MANIFEST)
    return actions,sources


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('verify','run','finish-world','collect'))
    parser.add_argument('--workflow',type=Path,required=True)
    parser.add_argument('--session')
    args=parser.parse_args();workflow=args.workflow.resolve();verify_workflow(workflow)
    if args.action=='verify':
        target=ROOT/'runtime/release-candidates'/expected()[-1]
        actions,_=verify_current(modules(verify_candidate(target)))
        print(json.dumps({'passed':True,'candidate':str(target),'ordinary_actions_reparsed':len(actions),'game_started':False}))
    elif args.action=='collect':
        import collect_four_boss_integration as frozen
        frozen.verify_current=verify_current
        print(json.dumps(frozen.collect(args.session,workflow,'073_yanqiansui'),ensure_ascii=False))
    else:
        import test_four_boss_integration as frozen
        frozen.verify_current=verify_current
        raise SystemExit(frozen.main(workflow,'073_yanqiansui',finish_world=args.action=='finish-world'))
