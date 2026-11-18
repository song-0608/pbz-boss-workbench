"""Run offline regressions; source-only mode never freezes or deploys a candidate."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from boss_adaptation_workflow import ROOT, sha, write_json
from build_boss_profile_candidate import lua
import build_player_travel_candidate as candidate
import player_travel_workflow as workflow


def check(package, manifest, flow=None, *, source_only=False):
    key = manifest['release_id']
    work = ROOT / 'runtime/travel-repair-checks' / (key + '-source-' + str(time.time_ns()) if source_only else key)
    work.mkdir(parents=True, exist_ok=True)
    def test_path(path):
        return path.as_posix() if source_only else path.relative_to(ROOT).as_posix()
    modules = {name[len(candidate.PREFIX):-4].replace('/', '.'): test_path(package / name)
        for name in manifest['files'] if name.startswith(candidate.PREFIX) and name.endswith('.lua')}
    loader = work / 'regression.lua'
    loader.write_text('local modules=' + lua(modules) + '\n'
        'for name,path in pairs(modules)do package.preload[name]=assert(loadfile(path))end\n'
        'dofile(assert(arg[3]))\n', encoding='utf-8')
    syntax = work / 'syntax.lua'
    syntax.write_text('local files=' + lua([test_path(package / n)
        for n in manifest['files'] if n.endswith('.lua')]) + '\n'
        'for _,path in ipairs(files)do assert(loadfile(path))end\n'
        "print('PASS candidate Lua syntax: '..#files)\n", encoding='utf-8')
    executable = ROOT.parent / 'build/lua-harness/Release/lua-lab.exe'
    jobs = [('syntax', [str(executable), str(syntax)])]
    for name in ('player_travel_repair', 'player_controller_query', 'player_controller_owner', 'player_reassembly', 'player_native_travel_trial',
                 'player_assembly_tasks', 'player_retirement_budget', 'player_map_lifecycle', 'player_map_initialization',
                 'player_target_diagnostics', 'runtime', 'ue_calls', 'ue_combat', 'world_boundary', 'idle_world_watch',
                 'map_travel_guard', 'workbench_input', 'player_experience_runtime',
                 'player_action_input', 'target_transition', 'ue_host'):
        jobs.append((name, [str(executable), str(loader), '.', test_path(package),
                           'tests/test_' + name + '.lua']))
    for name in ('player_travel_candidate', 'player_travel_trial', 'player_travel_progress', 'player_overlay', 'player_status_stream',
                 'workbench_roster', 'workbench_session_status', 'workbench_cmd_entry', 'player_source_checks'):
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
    record = dict(schema=1, source_only=source_only,
        candidate=None if source_only else str(package),
        candidate_manifest_sha256=None if source_only else sha(package / 'pbz-release.json'),
        workflow=None if source_only else str(flow),
        workflow_manifest_sha256=None if source_only else sha(flow / 'manifest.json'),
        source_sha256=manifest['travel_repair_identity']['sources'], payload_sha256=manifest['files'], checks=checks,
        passed=all(row['passed'] for row in checks), game_started=False, installed=False,
        runtime_verified=False, native_travel_verified=False, all_boss_skills_complete=False)
    report = ROOT / 'evidence/adaptation' / (key + ('-source-offline-' + str(time.time_ns()) if source_only else '-offline') + '.json')
    if report.exists():
        report = report.with_name(package.name + '-offline-' + str(time.time_ns()) + '.json')
    write_json(report, record)
    print(json.dumps(dict(report=str(report), passed=record['passed'], source_only=source_only,
                         workflow=record['workflow']), ensure_ascii=False))
    return 0 if record['passed'] else 1


def main(source_only=False):
    if source_only:
        # A disposable Lua test fixture is not a release candidate. In particular,
        # do not call build/verify, create a manifest, or alter any session state.
        manifest, files = candidate.expected()
        with tempfile.TemporaryDirectory(prefix='pbz-travel-source-tests-') as directory:
            package = Path(directory)
            for name, data in files.items():
                if name.endswith('.lua'):
                    path = package / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
            return check(package, manifest, source_only=True)
    package = candidate.build(); manifest = candidate.verify(package)
    return check(package, manifest, workflow.build(package))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-only', action='store_true',
        help='Test disposable Lua sources without freezing, deploying, or touching an active research session')
    raise SystemExit(main(parser.parse_args().source_only))
