"""Offline package, syntax, catalogue and regression checks before the single integration session."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from boss_adaptation_workflow import ROOT, sha, write_json
from build_boss_profile_candidate import lua
import build_expanded_boss_candidate as candidate
import expanded_boss_integration_workflow as workflow
from collect_expanded_boss_player import SOURCES as COLLECTOR_SOURCES, historical_profile_base

TESTS = ('test_expanded_boss_profile', 'test_expanded_boss_integration', 'test_expanded_boss_world',
         'test_player_experience_input_release', 'test_mod_installation', 'test_player_target_readiness',
         'test_published_boss_workflow', 'test_expanded_boss_player')
SOURCES = tuple(sorted(set((*candidate.SOURCES, *workflow.SOURCES, *COLLECTOR_SOURCES,
    'tools/check_expanded_boss_integration.py', 'tools/select_expanded_boss.py',
    'tools/release_expanded_boss_workbench.py', 'tools/published_boss_workflow.py', 'tools/boss_workbench_v5_window.py',
    'tools/verify_boss_workbench_v5.py',
    'tests/test_expanded_boss_catalog.lua', *('tests/' + name + '.py' for name in TESTS)))))


def check(package):
    with historical_profile_base(package):
        return _check(package)


def _check(package):
    manifest = candidate.verify(package); flow = workflow.build(package)
    sources = {name: sha(ROOT / name) for name in SOURCES}
    identity = dict(candidate_manifest_sha256=sha(package / 'pbz-release.json'), source_files=sources,
                    workflow_manifest_sha256=sha(flow / 'manifest.json'))
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    work = ROOT / 'runtime/expanded-player-offline' / key; work.mkdir(parents=True, exist_ok=True)
    syntax = work / 'syntax.lua'; syntax.write_text('\n'.join(
        'assert(loadfile(' + json.dumps((package / n).relative_to(ROOT).as_posix()) + '))'
        for n in manifest['files'] if n.endswith('.lua')) + '\n', encoding='utf-8')
    expected = []
    for addition in manifest['expansion_profiles']:
        report = json.loads((ROOT / addition['evidence']).read_bytes()); identity_row = report['metadata_identity']
        expected.append(dict(id=addition['id'], name=identity_row['display_name'], count=len(addition['skills']),
            class_path=identity_row['class_path'], config_path=identity_row['config_path'],
            skills={k:v['class_path'] for k,v in report['accepted_skills'].items()}))
    config = work / 'expected.lua'; config.write_text('return ' + lua(expected) + '\n', encoding='utf-8')
    executable = ROOT.parent / 'build/lua-harness/Release/lua-lab.exe'
    jobs = [('all_lua_syntax', [str(executable), str(syntax)]),
            ('independent_catalog', [str(executable), 'tests/test_expanded_boss_catalog.lua', str(package), str(config)]),
            ('python_regressions', [sys.executable, '-B', '-X', 'utf8', '-m', 'unittest',
                                    *('tests.' + name for name in TESTS)])]
    checks = []
    for name, command in jobs:
        job = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
        checks.append(dict(name=name, passed=job.returncode == 0, output=job.stdout + job.stderr))
        print(name + ': ' + ('PASS' if job.returncode == 0 else 'FAIL'), flush=True)
        if job.returncode: print(job.stdout + job.stderr, flush=True)
    assert sources == {name:sha(ROOT / name) for name in SOURCES}
    report = dict(schema=1, candidate=str(package), workflow=str(flow), **identity,
        checks=checks, passed=all(r['passed'] for r in checks), installed=False, game_started=False)
    target = ROOT / 'evidence/adaptation' / ('expanded-player-offline-' + key + '.json')
    if target.exists(): assert json.loads(target.read_bytes()) == report
    else: write_json(target, report)
    return target, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('candidate', type=Path)
    args = parser.parse_args(); path, report = check(args.candidate.resolve())
    print(json.dumps(dict(report=str(path), passed=report['passed'], workflow=report['workflow']), ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)
