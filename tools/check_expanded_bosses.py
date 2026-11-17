"""Build and exercise expansion bundles entirely offline."""
import hashlib
import json
import subprocess
import sys

from boss_adaptation_workflow import ROOT,sha,write_json
from build_boss_profile_candidate import lua
import expanded_boss_developer_bundle as bundle
import expanded_boss_developer_workflow as workflow


def check():
    source_names=sorted(set((*bundle.SOURCES,*workflow.SOURCES,'tools/check_expanded_bosses.py')))
    sources={name:sha(ROOT/name)for name in source_names}
    key=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()[:16]
    work=ROOT/'runtime/expanded-boss-offline'/key;work.mkdir(parents=True,exist_ok=True)
    checks=[];packages=[];executable=ROOT.parent/'build/lua-harness/Release/lua-lab.exe'
    for identifier in bundle.REVIEWS:
        target=bundle.build(identifier);flow=workflow.build(target);value,_=bundle.definition(identifier)
        config=work/(identifier+'.lua');config.write_text('return '+lua(value)+'\n',encoding='utf-8')
        job=subprocess.run([str(executable),'tests/test_expanded_boss_candidate.lua',
            target.relative_to(ROOT).as_posix()+'/boss_candidate.lua',config.relative_to(ROOT).as_posix()],
            cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
        checks.append(dict(id=identifier,passed=job.returncode==0,output=job.stdout+job.stderr))
        packages.append(dict(id=identifier,bundle=target.relative_to(ROOT).as_posix(),
            manifest_sha256=sha(target/'manifest.json'),workflow=flow.relative_to(ROOT).as_posix(),
            workflow_manifest_sha256=sha(flow/'manifest.json'),metadata_pool=len(value['ability_pool']),
            native_grants_verified=False,activation_verified=False,playable=False))
    job=subprocess.run([sys.executable,'-B','-X','utf8','-m','unittest',
        'tests.test_expanded_boss_developer','tests.test_collect_player_experience'],cwd=ROOT,
        capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
    checks.append(dict(id='python_regressions',passed=job.returncode==0,output=job.stdout+job.stderr))
    assert all(sha(ROOT/name)==digest for name,digest in sources.items())
    report=dict(schema=1,passed=all(row['passed']for row in checks),checks=checks,packages=packages,
        sources=sources,game_started=False,installed=False,new_playable_bosses=0,runtime_acceptance_current=False)
    target=ROOT/'evidence/adaptation'/('expanded-boss-offline-'+key+'.json');write_json(target,report)
    print(json.dumps(dict(report=str(target),passed=report['passed'],packages=packages,game_started=False),ensure_ascii=False))
    for row in checks:
        if not row['passed']:print(row['output'])
    return report['passed']


if __name__=='__main__':raise SystemExit(0 if check()else 1)
