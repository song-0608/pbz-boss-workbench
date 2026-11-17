"""Run targeted native-Lua simulations and existing regressions before one game session."""
import json
from pathlib import Path
import subprocess
import sys
import time

from boss_adaptation_workflow import ROOT, sha, write_json
from build_boss_profile_candidate import lua
import build_player_travel_candidate as candidate
import player_travel_workflow as workflow


def main():
    package = candidate.build(); manifest = candidate.verify(package)
    flow = workflow.build(package)
    work = ROOT / 'runtime/travel-repair-checks' / package.name
    work.mkdir(parents=True, exist_ok=True)
    modules = {name[len(candidate.PREFIX):-4].replace('/', '.'): (package / name).relative_to(ROOT).as_posix()
        for name in manifest['files'] if name.startswith(candidate.PREFIX) and name.endswith('.lua')}
    loader = work / 'regression.lua'
    loader.write_text('local modules=' + lua(modules) + '\n'
        'for name,path in pairs(modules)do package.preload[name]=assert(loadfile(path))end\n'
        'dofile(assert(arg[3]))\n', encoding='utf-8')
    syntax = work / 'syntax.lua'
    syntax.write_text('local files=' + lua([(package / n).relative_to(ROOT).as_posix()
        for n in manifest['files'] if n.endswith('.lua')]) + '\n'
        'for _,path in ipairs(files)do assert(loadfile(path))end\n'
        "print('PASS candidate Lua syntax: '..#files)\n", encoding='utf-8')
    executable = ROOT.parent / 'build/lua-harness/Release/lua-lab.exe'
    jobs = [('syntax', [str(executable), str(syntax)])]
    for name in ('player_travel_repair', 'player_controller_query', 'runtime', 'ue_calls', 'world_boundary', 'idle_world_watch',
                 'map_travel_guard', 'workbench_input', 'player_experience_runtime',
                 'player_action_input', 'target_transition', 'ue_host'):
        jobs.append((name, [str(executable), str(loader), '.', package.relative_to(ROOT).as_posix(),
                           'tests/test_' + name + '.lua']))
    for name in ('player_travel_candidate', 'player_travel_trial', 'player_overlay', 'player_status_stream',
                 'workbench_roster', 'workbench_session_status', 'workbench_cmd_entry'):
        command = ([sys.executable, '-B', '-X', 'utf8', 'tests/test_player_overlay.py']
                   if name == 'player_overlay' else
                   [sys.executable, '-B', '-X', 'utf8', '-m', 'unittest', 'discover',
                    '-s', 'tests', '-p', 'test_' + name + '.py'])
        jobs.append((name, command))
    checks = []
    for name, command in jobs:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, encoding='utf-8', errors='replace', timeout=45)
        checks.append(dict(name=name, passed=result.returncode == 0, output=(result.stdout + result.stderr).strip()))
        print(name + ': ' + ('PASS' if result.returncode == 0 else 'FAIL'), flush=True)
        if result.returncode:
            print(checks[-1]['output'], flush=True)
    record = dict(schema=1, candidate=str(package), candidate_manifest_sha256=sha(package / 'pbz-release.json'),
        workflow=str(flow), workflow_manifest_sha256=sha(flow / 'manifest.json'), checks=checks,
        passed=all(row['passed'] for row in checks), game_started=False, installed=False,
        runtime_verified=False, native_travel_verified=False, all_boss_skills_complete=False)
    report = ROOT / 'evidence/adaptation' / (package.name + '-offline.json')
    if report.exists():
        report = report.with_name(package.name + '-offline-' + str(time.time_ns()) + '.json')
    write_json(report, record)
    print(json.dumps(dict(report=str(report), passed=record['passed'], workflow=str(flow)), ensure_ascii=False))
    return 0 if record['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
