"""Freeze three single-player skill batches and run backend checks before launch."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import boss_skill_expansion as expansion
import boss_skill_workflow as workflow
from boss_adaptation_workflow import ROOT,sha,write_json
from mod_installation import active_mod_root,assert_closed

REPORT='evidence/adaptation/boss-skill-expansion-offline.json'
TESTS=('test_boss_skill_expansion.py','test_boss_skill_workflow.py','test_boss_skill_session.py',
       'test_candidate_effect_scope.py','test_mod_installation.py','test_performance_comparison.py')
SOURCES=('tools/prepare_boss_skill_milestone.py','tools/collect_boss_skill_session.py',
    *expansion.SOURCES,*workflow.SOURCES,*('tests/'+name for name in TESTS))


def freeze(root=ROOT):
    assert_closed(root)
    base=active_mod_root(root)
    rows=[]
    for item in expansion.read(root/expansion.QUEUE)['bosses']:
        identifier=item['id'];bundle=expansion.build(identifier,root=root)
        flow=workflow.build(bundle,root=root)
        rows.append(dict(id=identifier,bundle=bundle.relative_to(root).as_posix(),
            bundle_manifest_sha256=sha(bundle/'manifest.json'),
            workflow=flow.relative_to(root).as_posix(),workflow_manifest_sha256=sha(flow/'manifest.json'),
            actions=expansion.read(bundle/'manifest.json')['skill_expansion']['actions']))
    return dict(schema=1,bosses=rows,source_sha256={n:sha(root/n) for n in sorted(set(SOURCES))},
        base_mod_source_sha256={p.relative_to(base).as_posix():sha(p) for p in sorted(base.rglob('*.lua'))},
        expected_new_actions=12,expected_action_trials=24,game_started=False,deployed=False,
        playable=False,network_scope='deferred',runtime_acceptance_current=False)


def prepare(root=ROOT):
    plan=freeze(root);checks=[]
    jobs=[(name,[sys.executable,'-X','utf8',str(root/'tests'/name)]) for name in TESTS]
    lua=root.parent/'build/lua-harness/Release/lua-lab.exe'
    for row in plan['bosses']:
        jobs.append((row['id']+'_native_grants',[str(lua),str(root/'tests/test_boss_skill_candidate.lua'),
            str(root/row['bundle'])]))
    for label,command in jobs:
        result=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8',
            errors='replace',timeout=120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        checks.append(dict(name=label,passed=result.returncode==0,output=result.stdout+result.stderr))
        print(label+': '+('PASS' if result.returncode==0 else 'FAIL'),flush=True)
    assert plan==freeze(root),'Skill batch changed while checks were running'
    report=dict(plan,at=datetime.now().astimezone().isoformat(),checks=checks,
                passed=all(row['passed'] for row in checks))
    write_json(root/REPORT,report)
    assert report['passed'],'Backend checks failed; do not launch'
    write_json(root/'runtime/next-boss-skill-milestone.json',dict(
        report=REPORT,report_sha256=sha(root/REPORT),bosses=plan['bosses'],game_started=False,
        expected_single_process=True,network_scope='deferred',playable=False))
    return report


def verify(root=ROOT):
    report=expansion.read(root/REPORT);plan=freeze(root)
    assert all(report[k]==v for k,v in plan.items())
    assert report['passed'] is True and all(row['passed'] is True for row in report['checks'])
    assert [row['name'] for row in report['checks']]==[*TESTS,
        *(row['id']+'_native_grants' for row in plan['bosses'])]
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--verify',action='store_true')
    args=parser.parse_args();report=verify() if args.verify else prepare()
    print(json.dumps(dict(report=REPORT,passed=report['passed'],bosses=len(report['bosses']),
        expected_new_actions=report['expected_new_actions'],game_started=False),ensure_ascii=False))
