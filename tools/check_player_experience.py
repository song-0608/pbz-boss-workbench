"""Run candidate-scoped offline regressions; never launch or install the game."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import build_player_experience_candidate as candidate
import player_experience_workflow as workflow
from boss_adaptation_workflow import ROOT, sha, write_json
from build_boss_profile_candidate import lua
from mod_installation import MANIFEST

NEW_LUA = ('player_action_input', 'player_target_lock', 'player_boss_picker',
           'player_experience_runtime', 'player_experience_bridge', 'player_experience_catalog')
BASELINE_LUA = ('runtime', 'session', 'input_driver', 'ue_host', 'target_selector',
                'target_transition', 'remote_control', 'world_boundary', 'ue_calls',
                'ue_input_cache', 'input_barrier', 'object_lifecycle', 'combat_identity',
                'ue_combat', 'boss_workbench', 'workbench_input', 'player_hud',
                'player_entry', 'keymap', 'player_protection',
                'owned_initialization', 'idle_world_watch')
PYTHON_TESTS = ('player_experience_candidate', 'player_experience_workflow',
                'player_experience_trial', 'player_experience_input_release',
                'player_roster_expansion', 'player_keymap', 'player_overlay',
                'player_status_stream', 'performance_comparison', 'practice_lease',
                'research_scene_checkpoint', 'research_scene_reload')


def remap_test(source, directory, root=ROOT):
    """Keep assertions intact and redirect only historical module path literals."""
    old = '/mod/PBZBossControl/'
    assert old in source, 'Historical test has no explicit module anchor'
    relative = directory.relative_to(root).as_posix()
    return source.replace(old, '/' + relative + '/PBZBossControl/')


def run(name, command, root=ROOT):
    result = subprocess.run([str(x) for x in command], cwd=root, capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=120)
    return dict(name=name, passed=result.returncode == 0, exit_code=result.returncode,
                output=(result.stdout + result.stderr).strip())


def check(directory=None, root=ROOT):
    directory = (directory or candidate.build(root)).resolve()
    manifest = candidate.verify(directory, root)
    trial = workflow.build(directory, root)
    workflow.verify(trial, root)
    tests = [root/'tests'/('test_'+name+'.lua') for name in (*NEW_LUA, *BASELINE_LUA)]
    tests += [root/'tests'/('test_'+name+'.py') for name in PYTHON_TESTS]
    tests += [root/'tools'/name for name in ('player_experience_trial.py',
              'test_player_experience_inputs.py','player_experience_metadata.py')]
    sources = {p.relative_to(root).as_posix(): sha(p) for p in tests}
    sources['tools/check_player_experience.py'] = sha(Path(__file__))
    identity = dict(candidate=manifest['release_id'], tests=sources)
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    work = root/'runtime/player-experience-checks'/key
    work.mkdir(parents=True, exist_ok=True)
    executable = root.parent/'build/lua-harness/Release/lua-lab.exe'
    modules = sorted((directory/'PBZBossControl/Scripts').rglob('*.lua'))
    syntax = work/'syntax.lua'
    syntax.write_text('local files='+lua([p.relative_to(root).as_posix() for p in modules])+
                      '\nfor _,path in ipairs(files)do assert(loadfile(path))end\n'
                      "print('PASS syntax: '..#files..' candidate modules')\n", encoding='utf-8')
    checks = [run('candidate_lua_syntax', [executable, syntax], root)]
    for name in NEW_LUA:
        checks.append(run(name, [executable, root/'tests'/('test_'+name+'.lua'), root, directory], root))
    for name in BASELINE_LUA:
        original = root/'tests'/('test_'+name+'.lua')
        source = remap_test(original.read_text(encoding='utf-8'), directory, root)
        runner = work/('test_'+name+'.lua')
        runner.write_text(source, encoding='utf-8')
        checks.append(run('candidate_baseline_'+name, [executable, runner, root], root))
    checks.append(run('python_regressions', [sys.executable, '-B', '-X', 'utf8', '-m', 'unittest',
        *('tests.test_'+name for name in PYTHON_TESTS)], root))
    candidate.verify(directory, root)
    workflow.verify(trial, root)
    assert all(sha(root/name)==digest for name,digest in sources.items()), 'Sources changed during check'
    report = dict(schema=1, at=datetime.now().astimezone().isoformat(),
        passed=all(c['passed'] for c in checks), candidate=str(directory),
        candidate_manifest_sha256=sha(directory/MANIFEST), workflow=str(trial),
        workflow_manifest_sha256=sha(trial/'manifest.json'), source_files=sources,
        candidate_lua_modules=len(modules), checks=checks, game_started=False,
        installed=False, runtime_acceptance_current=False,
        new_playable_bosses=0, more_boss_resource_previews=6)
    target=root/'evidence/adaptation'/('player-experience-offline-'+key+'.json')
    write_json(target, report)
    print(json.dumps(dict(report=str(target),passed=report['passed'],groups=len(checks),
        failed=[c['name'] for c in checks if not c['passed']],candidate=str(directory),
        workflow=str(trial),game_started=False),ensure_ascii=False))
    for row in checks:
        if not row['passed']: print(row['name']+':\n'+row['output'])
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path)
    args=parser.parse_args()
    sys.exit(0 if check(args.candidate)['passed'] else 1)
