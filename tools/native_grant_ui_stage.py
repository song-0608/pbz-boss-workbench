"""Prepare exact Boss experiments without sending UI input or launching games.

Build offline, stage once on an owned idle research carrier with fresh native
contracts, issue a short reload gate, then use the window API for Ctrl+R.
Gate issuance is not evidence that input was sent or that a Boss is playable.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from boss_adaptation_workflow import ROOT, sha, write_json
from build_player_experience_candidate import replace
from mod_installation import unlinked_path
import native_grant_developer_bundle as bundle
import native_grant_developer_workflow as previous

SOURCES = ('tools/native_grant_ui_stage.py', 'tests/test_native_grant_ui_stage.py')
LABEL = 'native-grant-ui-stage'
OPTIONS = ('--interactive', '--camera', '--combat', '--remote', '--barrier',
           '--protect-player', '--batch-skills', '--practice', '--update-modules',
           '--target-cycle', '--arena-navigation-trial', '--performance-profile')


def render(root=ROOT):
    original = previous.render(root)
    runner = original['run_control_lifecycle_probe.py'].decode('utf-8')
    runner = replace(runner, 'import research_game_menu as menu\n', '')
    runner = replace(runner, 'from mod_installation import active_mod_root\n',
                     'from mod_installation import active_mod_root, unlinked_path\n')
    runner = replace(runner, '        target=directory/source.relative_to(scripts)\n',
        '        target=directory/source.relative_to(scripts)\n'
        "        assert unlinked_path(target).is_relative_to(unlinked_path(directory)), 'preserve linked module path'\n")
    runner = replace(runner,
        "    menu.click(0,0,2560,1600,'control_reload')\n"
        "    print('Bounded lifecycle experiment hot reload requested in existing isolated game; no restart.')",
        "    print('Candidate staged; no input sent. Use a fresh reload gate and the window API.')")
    runner = replace(runner, "if __name__=='__main__':main()", '''if __name__=='__main__':
    import native_grant_ui_stage as controller
    context = controller.begin_stage(Path(__file__).parent)
    sys.argv = [__file__, *controller.OPTIONS, '--boss-candidate', context['id'],
                '--boss-candidate-bundle', context['bundle']]
    main()
    controller.finish_stage(Path(__file__).parent, context)
''')
    ast.parse(runner)
    assert 'research_game_menu' not in runner and 'menu.click' not in runner
    return {'stage_candidate.py': runner.encode('utf-8'),
            'boss_candidate_gate.py': original['boss_candidate_gate.py']}


def expected(target, root=ROOT):
    parent, _, _ = previous.expected(target, root)
    files = render(root)
    manifest = dict(schema=1, kind='native_grant_ui_stage', id=parent['id'],
        bundle=str(target), bundle_manifest_sha256=sha(target / 'manifest.json'),
        parent_workflow_manifest=parent,
        source_files={n: sha(root / n) for n in SOURCES},
        files={n: hashlib.sha256(data).hexdigest() for n, data in files.items()},
        developer_only=True, playable=False, game_started=False, ui_input_sent=False)
    key = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:16]
    return manifest, files, 'native-grant-ui-' + parent['id'] + '-' + key


def build(target, root=ROOT):
    target = unlinked_path(target)
    manifest, files, name = expected(target, root)
    output = root / 'runtime/developer-workflows' / name
    if not output.exists():
        output.mkdir(parents=True)
        for filename, data in files.items(): (output / filename).write_bytes(data)
        write_json(output / 'manifest.json', manifest)
    verify(output, root)
    return output


def verify(flow, root=ROOT):
    flow = unlinked_path(flow)
    assert flow.parent == (root / 'runtime/developer-workflows').resolve()
    recorded = bundle.read(unlinked_path(flow / 'manifest.json'))
    target = unlinked_path(Path(recorded['bundle']))
    manifest, files, name = expected(target, root)
    assert flow.name == name and recorded == manifest, 'workflow or source drift'
    assert {p.name for p in flow.iterdir()} == set(files) | {'manifest.json'}
    assert all(unlinked_path(flow / n).read_bytes() == data for n, data in files.items())
    return manifest


def idle_guard(owner, state, now):
    assert owner.get('state_file') == state.get('state_file'), 'current owned session required'
    assert owner.get('phase') == 'game_launched', 'idle unarmed carrier required'
    assert not state.get('boss_lifecycle_experiment'), 'preserve existing experiment'
    assert state.get('readonly_ai_experiment') and state.get('readonly_hot_reload_enabled')
    assert state.get('ue4ss_deployed') and not state.get('restored')
    assert state.get('offline_validation') and not state.get('network_active')
    assert now < state['deadline_unix'] - 180, 'preserve initialization and cleanup time'


def mirror_guard(state, mirror):
    mirror = unlinked_path(mirror)
    paths = [unlinked_path(Path(row['physical_path'])) for row in state['ue4ss_loader_manifest']]
    assert paths and all(p.is_relative_to(mirror) for p in paths), 'research mirror files only'
    assert len(paths) == len(set(paths)), 'unique loader declarations required'
    carriers = [p for p in paths if p.as_posix().endswith('/Mods/PBZObserveAI/Scripts/main.lua')]
    assert len(carriers) == 1, 'unique idle carrier required'
    return carriers[0]


def begin_stage(flow):
    import ahua_practice as practice
    import official_validation as validation
    from research_storage import container_path
    manifest = verify(flow)
    owner, state = practice.owned_session()
    idle_guard(owner, state, time.time())
    carrier = mirror_guard(state, container_path())
    pid = research_pid(validation)
    validation.verify_build(state['ue4ss_loader_manifest'])
    assert validation.c.baseline.formal_files() == state['formal_before']
    work = unlinked_path(Path(state['work']))
    assert work == unlinked_path(ROOT / 'evidence/official-validation' / work.name)
    assert not list(work.glob(LABEL + '*')), 'preserve prior attempt, including failed staging'
    raw = practice.log_path(state).read_bytes()
    context = dict(schema=1, id=manifest['id'], bundle=manifest['bundle'],
        workflow=str(unlinked_path(flow)), workflow_manifest_sha256=sha(flow / 'manifest.json'),
        state_file=state['state_file'], log_byte_offset=len(raw), log_prefix_sha256=hashlib.sha256(raw).hexdigest(),
        carrier=str(carrier), carrier_before_sha256=sha(carrier),
        deadline_unix=state['deadline_unix'], research_pid=pid, ui_input_sent=False, staged=False)
    # Save intent before the inherited deployment can mutate the carrier. A
    # failure must leave evidence and must not be blindly retried.
    write_json(work / (LABEL + '-intent.json'), context)
    return context


def deployment_guard(deployment, manifest, state, now):
    grant = deployment['grant']
    expected_grant = manifest['parent_workflow_manifest']['candidate_grant']
    assert deployment['boss_candidate'] == manifest['id'] and not deployment['player_entry']
    assert unlinked_path(Path(deployment['developer_bundle'])) == unlinked_path(Path(manifest['bundle']))
    assert deployment['candidate_identity_grant'] == expected_grant
    assert all(grant.get(k) == v for k, v in expected_grant.items())
    assert grant['isolated'] is True and grant['offline'] is True
    assert grant['exe_sha256'] == bundle.BUILD
    assert grant['session_id'] == Path(state['state_file']).parent.name
    assert now < grant['expires_at'] <= state['deadline_unix'], 'never refresh a staged grant'
    assert state['control_probe_expires_at'] == grant['expires_at']
    recorded = bundle.read(Path(manifest['bundle']) / 'manifest.json')
    expected_modules = {p.removeprefix('Scripts/'): h for p, h in recorded['base_mod_files'].items()
                        if p.startswith('Scripts/') and p != 'Scripts/main.lua'}
    expected_modules['boss_candidate.lua'] = recorded['overrides']['Scripts/boss_candidate.lua']
    assert deployment['module_source_sha256'] == expected_modules, 'exact candidate and base modules required'
    for key in ('arena_navigation_trial', 'performance_profile'):
        assert deployment[key] is True
    for key in ('skill_lab', 'expanded', 'player_key_trial', 'combo_scheduler_trial',
                'death_trial', 'native_death_trial', 'active_skill_death_trial',
                'active_skill_disposal_trial', 'incoming_combat_trial', 'scene_transition_trial'):
        assert deployment[key] is False


def finish_stage(flow, context):
    import ahua_practice as practice
    import official_validation as validation
    from research_storage import container_path
    manifest = verify(flow)
    owner, state = practice.owned_session()
    assert state['state_file'] == context['state_file'] and owner['phase'] == 'game_launched'
    assert state['deadline_unix'] == context['deadline_unix']
    assert research_pid(validation) == context['research_pid'], 'preserve the process checked at staging'
    work = Path(state['work'])
    assert bundle.read(work / (LABEL + '-intent.json')) == context
    carrier = mirror_guard(state, container_path())
    assert str(carrier) == context['carrier']
    validation.verify_build(state['ue4ss_loader_manifest'])
    assert validation.c.baseline.formal_files() == state['formal_before']
    deployment = bundle.read(work / 'control-lifecycle-deployment.json')
    deployment_guard(deployment, manifest, state, time.time())
    archives = [p for p in work.glob('control-lifecycle-deployment-*.json') if bundle.read(p) == deployment]
    assert len(archives) == 1, 'one exact deployment archive required'
    raw = practice.log_path(state).read_bytes()
    assert hashlib.sha256(raw[:context['log_byte_offset']]).hexdigest() == context['log_prefix_sha256']
    tail = raw[context['log_byte_offset']:].decode('utf-8', errors='strict')
    assert 'PBZ_CONTROL_LIFECYCLE:' not in tail, 'unexpected reload before separate UI gate'
    receipt = dict(context, staged=True, carrier_sha256=sha(carrier),
        deployment_archive=archives[0].name, deployment_sha256=sha(archives[0]),
        grant_expires_at=deployment['grant']['expires_at'])
    target = work / (LABEL + '-staged.json')
    assert not target.exists()
    write_json(target, receipt)
    print(json.dumps(dict(staged=True, id=manifest['id'], ui_input_sent=False,
                          reload_required=True, playable=False), ensure_ascii=False))


def staged_guard(flow):
    import ahua_practice as practice
    import official_validation as validation
    from research_storage import container_path
    manifest = verify(flow)
    owner, state = practice.owned_session()
    assert owner['phase'] == 'game_launched' and state.get('boss_lifecycle_experiment')
    assert state.get('offline_validation') and not state.get('network_active') and not state.get('restored')
    assert time.time() < state['deadline_unix'] - 120
    work = Path(state['work'])
    receipt = bundle.read(work / (LABEL + '-staged.json'))
    assert receipt['staged'] is True and receipt['ui_input_sent'] is False
    assert receipt['state_file'] == state['state_file'] and receipt['workflow'] == str(unlinked_path(flow))
    assert receipt['workflow_manifest_sha256'] == sha(flow / 'manifest.json')
    assert receipt['deadline_unix'] == state['deadline_unix']
    assert research_pid(validation) == receipt['research_pid'], 'staged process changed'
    intent = bundle.read(work / (LABEL + '-intent.json'))
    assert all(receipt.get(k) == v for k, v in intent.items() if k != 'staged')
    assert intent['staged'] is False
    carrier = mirror_guard(state, container_path())
    assert str(carrier) == receipt['carrier'] and sha(carrier) == receipt['carrier_sha256']
    validation.verify_build(state['ue4ss_loader_manifest'])
    assert validation.c.baseline.formal_files() == state['formal_before']
    assert Path(receipt['deployment_archive']).name == receipt['deployment_archive']
    archive = work / receipt['deployment_archive']
    assert sha(archive) == receipt['deployment_sha256']
    deployment = bundle.read(archive)
    assert bundle.read(work / 'control-lifecycle-deployment.json') == deployment
    deployment_guard(deployment, manifest, state, time.time())
    assert deployment['grant']['expires_at'] == receipt['grant_expires_at']
    raw = practice.log_path(state).read_bytes()
    offset = receipt['log_byte_offset']
    assert type(offset) is int and 0 <= offset <= len(raw)
    assert hashlib.sha256(raw[:offset]).hexdigest() == receipt['log_prefix_sha256']
    return manifest, state, receipt, raw[offset:].decode('utf-8', errors='strict')


def select_research_pid(processes, game):
    """Accept one exact engine image, optionally with its own Steam launcher.

    Both PBZ images share a filename. A filename-only count must neither reject
    the legitimate parent/child pair nor pick an arbitrary process from it.
    """
    rows = [row for row in processes if row['Name'].lower() == 'pbz.exe']
    engine = (Path(game) / 'platform/steam/PBZ.exe').resolve()
    launcher = (Path(game) / 'steam/PBZ.exe').resolve()
    def image(row):
        value = row.get('ExecutablePath')
        assert isinstance(value, str) and value, 'research image path unreadable'
        return Path(value).resolve()
    engines = [row for row in rows if image(row) == engine]
    assert len(engines) == 1, 'one exact owned research engine required'
    selected = engines[0]
    for row in rows:
        assert row is selected or (image(row) == launcher
            and row['ProcessId'] == selected.get('ParentProcessId')), 'unexpected additional research game'
    return selected['ProcessId']


def research_pid(validation):
    c = validation.c
    c.isolation.select_box('PBZSteamLab'); dll = c.isolation.api()
    c.isolation.check_policy(dll, allow_offline_validation=True)
    assert not c.host_steam_pids(dll), 'preserve host Steam'
    return select_research_pid(c.box_processes(dll), c.baseline.GAME)


def foreground_window(validation, expected_pid):
    import ctypes
    from ctypes import wintypes as w
    assert research_pid(validation) == expected_pid, 'staged process changed'
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetForegroundWindow.restype = w.HWND
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    user.IsWindowVisible.argtypes = [w.HWND]
    callback = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes = [callback, w.LPARAM]
    windows = []
    @callback
    def inspect(handle, _):
        pid = w.DWORD(); user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        if pid.value == expected_pid and user.IsWindowVisible(handle):
            name = ctypes.create_unicode_buffer(256); user.GetClassNameW(handle, name, len(name))
            if name.value == 'Sandbox:PBZSteamLab:UnrealWindow': windows.append(int(handle))
        return True
    assert user.EnumWindows(inspect, 0)
    foreground = int(user.GetForegroundWindow() or 0)
    assert len(windows) == 1 and windows[0] == foreground, 'exact foreground research window required'
    return foreground


def reload_gate(flow):
    import official_validation as validation
    manifest, state, receipt, tail = staged_guard(flow)
    assert 'PBZ_CONTROL_LIFECYCLE:' not in tail, 'do not repeat a started reload'
    window = foreground_window(validation, receipt['research_pid'])
    now = time.time()
    assert now + 10 < min(receipt['grant_expires_at'], state['deadline_unix'] - 120)
    record = dict(id=manifest['id'], state_file=state['state_file'], window_id=window,
        research_pid=receipt['research_pid'],
        workflow_manifest_sha256=receipt['workflow_manifest_sha256'],
        staged_receipt_sha256=sha(Path(state['work']) / (LABEL + '-staged.json')),
        key='Control_L+r', gate_expires_at=now + 10, input_sent=False, playable=False)
    write_json(Path(state['work']) / (LABEL + '-gate-' + str(time.time_ns()) + '.json'), record)
    return record


def capture(flow):
    manifest, state, receipt, tail = staged_guard(flow)
    identity = 'PBZ_CONTROL_LIFECYCLE:CANDIDATE_IDENTITY_READY=' + manifest['id'] + '|'
    assert tail.count(identity) == 1 and tail.count('PBZ_CONTROL_LIFECYCLE:INTERACTIVE_READY=') == 1
    assert not any(s in tail for s in ('PBZ_CONTROL_LIFECYCLE:ISSUE_', 'state=FAULTED', 'RESTORE:FAILED='))
    rows = []
    import re
    for role, skill, path in re.findall(r'CANDIDATE_LIVE_BINDING=([^|\r\n]+)\|([^|\r\n]+)\|([^\r\n]+)', tail):
        assert role == manifest['id']
        rows.append(dict(skill=skill, class_path=path))
    allowed = bundle.read(Path(manifest['bundle']) / 'manifest.json')['definition']['ability_pool']
    assert rows and len({r['skill'] for r in rows}) == len(rows)
    assert len({r['class_path'] for r in rows}) == len(rows)
    assert all(r['class_path'] in allowed for r in rows)
    result = dict(id=manifest['id'], state_file=state['state_file'],
        workflow_manifest_sha256=receipt['workflow_manifest_sha256'], bindings=rows,
        missing_native_grants=[p for p in allowed if p not in {r['class_path'] for r in rows}],
        initialization_observed=True, playable=False, activation_verified=False,
        damage_verified=False, restoration_verified=False, lines=tail.splitlines())
    target = Path(state['work']) / (LABEL + '-capture.json')
    assert not target.exists(), 'preserve previous capture'
    write_json(target, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('build').add_argument('bundle', type=Path)
    for name in ('verify', 'stage', 'reload-gate', 'capture'):
        sub.add_parser(name).add_argument('workflow', type=Path)
    args = parser.parse_args()
    if args.action == 'build': result = dict(workflow=str(build(args.bundle)), game_started=False)
    elif args.action == 'verify': result = dict(verified=True, id=verify(args.workflow)['id'])
    elif args.action == 'stage':
        verify(args.workflow)
        raise SystemExit(subprocess.run([sys.executable, '-B', '-X', 'utf8',
            str(args.workflow / 'stage_candidate.py')], cwd=ROOT).returncode)
    elif args.action == 'reload-gate': result = reload_gate(args.workflow)
    else: result = capture(args.workflow)
    print(json.dumps(result, ensure_ascii=False, indent=2))
