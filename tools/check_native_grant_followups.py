"""Check and freeze two follow-up pools offline; never installs or launches them."""
import hashlib
import json
import subprocess
import sys

from boss_adaptation_workflow import ROOT, sha, write_json
from build_boss_profile_candidate import lua
import native_grant_developer_bundle as bundle
import native_grant_developer_workflow as workflow


def check():
    sources = {n: sha(ROOT / n) for n in sorted(set((*bundle.SOURCES, *workflow.SOURCES,
        'tools/check_native_grant_followups.py')))}
    key = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()[:16]
    work = ROOT / 'runtime/native-grant-offline' / key; work.mkdir(parents=True, exist_ok=True)
    checks, packages = [], []
    executable = ROOT.parent / 'build/lua-harness/Release/lua-lab.exe'
    for identifier in bundle.REVIEWS:
        target = bundle.build(identifier); flow = workflow.build(target)
        value, _ = bundle.definition(identifier)
        config = work / (identifier + '.lua')
        config.write_text('return ' + lua(value) + '\n', encoding='utf-8')
        command = [str(executable), 'tests/test_native_grant_candidate.lua',
                   (target / 'boss_candidate.lua').relative_to(ROOT).as_posix(), config.relative_to(ROOT).as_posix()]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=30)
        checks.append(dict(id=identifier, passed=result.returncode == 0, output=result.stdout + result.stderr))
        packages.append(dict(id=identifier, action_kind=value['followup_action_kind'],
            bundle=target.relative_to(ROOT).as_posix(), manifest_sha256=sha(target / 'manifest.json'),
            workflow=flow.relative_to(ROOT).as_posix(), workflow_manifest_sha256=sha(flow / 'manifest.json'),
            metadata_pool=len(value['ability_pool']), native_grants_current=False,
            activation_verified=False, damage_verified=False, playable=False))
    command = [sys.executable, '-B', '-X', 'utf8', '-m', 'unittest',
               'tests.test_native_grant_developer', 'tests.test_native_grant_metadata_workflow',
               'tests.test_boss_native_grant_followup']
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=60)
    checks.append(dict(id='python_regressions', passed=result.returncode == 0, output=result.stdout + result.stderr))
    assert all(sha(ROOT / n) == digest for n, digest in sources.items())
    report = dict(schema=1, passed=all(r['passed'] for r in checks), checks=checks, packages=packages,
                  sources=sources, game_started=False, installed=False, new_playable_bosses=0,
                  runtime_acceptance_current=False)
    target = ROOT / 'evidence/adaptation' / ('native-grant-followups-offline-' + key + '.json')
    if target.exists(): assert json.loads(target.read_bytes()) == report, 'preserve previous report'
    else: write_json(target, report)
    print(json.dumps(dict(report=str(target), passed=report['passed'], packages=packages), ensure_ascii=False))
    for row in checks:
        if not row['passed']: print(row['output'])
    return report['passed']


if __name__ == '__main__': raise SystemExit(0 if check() else 1)
