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
import creative_workspace


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
    # These two contracts deliberately exercise canonical numeric defaults.
    # Test authored payload values separately rather than rejecting valid tuning.
    fixed_loader=work/'fixed-tuning-contracts.lua'
    fixed_modules=dict(modules,player_3c_tuning='tools/player_3c_tuning.lua')
    fixed_loader.write_text('local modules='+lua(fixed_modules)+'\n'
        'for name,path in pairs(modules)do package.preload[name]=assert(loadfile(path))end\n'
        'dofile(assert(arg[3]))\n',encoding='utf-8')
    identity=manifest['travel_repair_identity']['creative_integration']
    profiles={}
    if identity:
        directory,creative=creative_workspace.checked_snapshot('integration',identity['integration'])
        assert creative_workspace.digest(creative_workspace.canonical(creative))==identity['manifest_sha256']
        profiles=creative_workspace.read(directory/'files'/creative_workspace.CONFIGS[0])['profiles']
    authored=work/'creative-tuning-payload.lua'
    authored.write_text('local actual=assert(loadfile('+lua(test_path(package/(candidate.PREFIX+'player_3c_tuning.lua')))+'))()\n'
        "local reference=assert(loadfile('tools/player_3c_tuning.lua'))()\n"
        "package.loaded['player_3c_tuning']=actual\n"
        'local Input=assert(loadfile('+lua(test_path(package/(candidate.PREFIX+'ue_input.lua')))+'))()\n'
        'local profiles='+lua(profiles)+'\nlocal roles='+lua(sorted(creative_workspace.ROLES-{'*'}))+'\n'
        'for _,id in ipairs(roles)do\n'
        ' local expected=reference.resolve(id)\n'
        " for key,value in pairs(profiles['*']or{})do expected[key]=value end\n"
        ' for key,value in pairs(profiles[id]or{})do expected[key]=value end\n'
        ' local resolved=actual.resolve(id)\n'
        " for key,value in pairs(expected)do assert(resolved[key]==value,'authored tuning mismatch: '..id..'/'..key)end\n"
        ' assert(actual.resolve(id,{mouse_scale=.37}).mouse_scale==.37)\n'
        ' local pc={IsMoveInputIgnored=function()return false end,IsLookInputIgnored=function()return false end,\n'
        '  IsInputKeyDown=function()return false end,GetControlRotation=function()return{Yaw=0}end,\n'
        '  GetInputMouseDelta=function(_,x,y)x.DeltaX=1000000;y.DeltaY=0 end}\n'
        ' local bridge={profile={id=id},api={locomotion={settings=resolved}},check=function()return pc end}\n'
        ' local input=Input.new(bridge,{make_name=function(v)return v end,game_paused=function()return false end},\n'
        '  {input_verified=true,mouse_scale=.22}):read({})\n'
        " assert(input.look_yaw==actual.look_limit(bridge.api.locomotion),'input and native look bounds differ: '..id)\n"
        'end\n'
        "print('PASS pinned creative tuning for six roles and explicit call overrides')\n",encoding='utf-8')
    syntax = work / 'syntax.lua'
    syntax.write_text('local files=' + lua([test_path(package / n)
        for n in manifest['files'] if n.endswith('.lua')]) + '\n'
        'for _,path in ipairs(files)do assert(loadfile(path))end\n'
        "print('PASS candidate Lua syntax: '..#files)\n", encoding='utf-8')
    executable = ROOT.parent / 'build/lua-harness/Release/lua-lab.exe'
    jobs = [('syntax', [str(executable), str(syntax)]),('creative_tuning_payload',[str(executable),str(authored)])]
    for name in ('player_travel_repair', 'player_controller_query', 'player_controller_owner', 'player_reassembly', 'player_native_travel_trial',
                 'player_assembly_tasks', 'player_action_queue', 'player_retirement_budget', 'player_map_lifecycle', 'player_map_initialization',
                 'player_target_diagnostics', 'runtime', 'ue_calls', 'ue_combat', 'world_boundary', 'idle_world_watch',
                 'player_spawn_assets',
                 'player_activity_probe',
                 'boss_defense_input', 'boss_defense_bridge', 'boss_native_cues', 'boss_cue_bridge', 'boss_combat_controls', 'boss_native_input',
                 'map_travel_guard', 'workbench_input', 'player_experience_runtime',
                 'player_action_input', 'player_primary_routes', 'remote_control', 'player_remote_performance', 'target_transition', 'ue_host',
                 'input_driver', 'player_3c', 'player_skill_buffer', 'player_locomotion', 'player_3c_target_lock'):
        selected_loader=fixed_loader if name in ('player_3c','player_locomotion') else loader
        jobs.append((name, [str(executable), str(selected_loader), '.', test_path(package),
                           'tests/test_' + name + '.lua']))
    for name in ('boss_combat_contract', 'boss_combat_support', 'boss_defense_cue_audit', 'boss_combat_script_audit',
                 'player_travel_candidate', 'player_travel_trial', 'player_travel_progress', 'player_overlay', 'player_status_stream',
                 'workbench_roster', 'workbench_session_status', 'workbench_cmd_entry', 'player_source_checks', 'player_3c_contract',
                 'player_travel_ui_stage', 'player_travel_capture', 'creative_workspace', 'creative_workbench','creative_starter_workspace'):
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
    record['creative_integration']=identity
    record['sources_unchanged_after_checks']=all(sha(ROOT/name)==expected
        for name,expected in record['source_sha256'].items())
    record['passed']=record['passed'] and record['sources_unchanged_after_checks']
    record['canonical_tuning_contracts']=['player_3c','player_locomotion']
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
