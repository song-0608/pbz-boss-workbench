"""Separate current 3C candidate deployment, window reload and live readiness.

No UI input, automatic game launch, live ability activation or accepted release
installation occurs here. The ordinary lease and independent watchdog remain
unchanged. Use stage only after the separately observed read-only contracts.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time

import ahua_practice as practice
import official_validation as validation
import native_grant_ui_stage as controls
import player_travel_workflow as workflow
import build_player_travel_candidate as candidate
from boss_adaptation_workflow import ROOT, sha, write_json
from four_boss_integration_workflow import modules
from mod_installation import unlinked_path


LABEL = 'player-travel-ui-stage'
OPTIONS = ('--interactive', '--camera', '--combat', '--remote', '--barrier',
           '--protect-player', '--batch-skills', '--practice', '--update-modules',
           '--target-cycle', '--arena-navigation-trial', '--performance-profile',
           '--player-entry', '--scene-transition-trial')


def deployment_guard(deployment, manifest, package, state, now):
    assert deployment['player_entry'] is True and deployment['boss_candidate'] is None
    assert deployment['module_source_sha256'] == modules(manifest), 'exact current candidate modules required'
    assert unlinked_path(Path(deployment['mod_source_directory'])) == package / 'PBZBossControl'
    assert deployment['formal_install_modified'] is False
    for name in ('scene_transition_trial', 'arena_navigation_trial', 'performance_profile'):
        assert deployment[name] is True
    for name in ('skill_lab', 'expanded', 'player_key_trial', 'combo_scheduler_trial', 'death_trial',
                 'native_death_trial', 'active_skill_death_trial', 'active_skill_disposal_trial', 'incoming_combat_trial'):
        assert deployment[name] is False
    grant = deployment['grant']
    assert grant['isolated'] is True and grant['offline'] is True
    assert grant['session_id'] == Path(state['state_file']).parent.name
    assert now < grant['expires_at'] == state['control_probe_expires_at'] <= state['deadline_unix']


def stage(flow):
    record = workflow.verify(flow)
    package = unlinked_path(Path(record['candidate']))
    manifest = candidate.verify(package)
    owner, state = practice.owned_session()
    controls.idle_guard(owner, state, time.time())
    from research_storage import container_path
    carrier = controls.mirror_guard(state, container_path())
    pid = controls.research_pid(validation)
    validation.verify_build(state['ue4ss_loader_manifest'])
    assert validation.c.baseline.formal_files() == state['formal_before']
    work = Path(state['work'])
    assert not list(work.glob(LABEL + '*')), 'preserve prior attempt'
    # Require this process's completed contracts. These inspectors read engine
    # declarations only; they do not focus windows, send keys or call gameplay.
    import stage_readonly_contracts as readonly
    _, _, _, receipt, tail = readonly.snapshot()
    assert receipt['research_pid'] == pid
    readonly.analyze(tail)
    practice.validate_map_travel_loader(state, practice.log_path(state).read_text(encoding='utf-8', errors='replace'))
    for name in ('inspect_camera_contract.py', 'inspect_combat_contract.py', 'inspect_combat_types.py',
                 'inspect_remote_contract.py', 'inspect_input_barrier_contract.py',
                 'inspect_player_protection_contract.py', 'inspect_player_ui_contract.py', 'inspect_arena_contract.py',
                 'inspect_player_controller_contract.py'):
        result = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'tools' / name)],
            cwd=ROOT, capture_output=True, encoding='utf-8', errors='replace', timeout=100)
        (work / (LABEL + '-' + name + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
        assert result.returncode == 0, 'read-only contract failed: ' + name
    # Inspectors consume time but cannot extend the session.
    controls.idle_guard(*practice.owned_session(), time.time())
    raw = practice.log_path(state).read_bytes()
    context = dict(workflow=str(unlinked_path(flow)), workflow_sha256=sha(Path(flow) / 'manifest.json'),
        source_sha256=sha(Path(__file__)), state_file=state['state_file'], research_pid=pid,
        deadline_unix=state['deadline_unix'], carrier=str(carrier), log_byte_offset=len(raw),
        log_offset=len(raw.decode('utf-8', errors='replace')),
        log_prefix_sha256=hashlib.sha256(raw).hexdigest(), input_sent=False)
    write_json(work / (LABEL + '-intent.json'), context)
    result = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(Path(flow) / 'run_control_lifecycle_probe.py'),
        *OPTIONS], cwd=ROOT, capture_output=True, encoding='utf-8', errors='replace', timeout=120)
    (work / (LABEL + '-deployment.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
    assert result.returncode == 0, 'candidate staging failed; preserve intent and close research session'
    owner, state = practice.owned_session()
    assert owner['phase'] == 'game_launched' and state['state_file'] == context['state_file']
    assert state['deadline_unix'] == context['deadline_unix'] and controls.research_pid(validation) == pid
    validation.verify_build(state['ue4ss_loader_manifest'])
    deployment = practice.read(work / 'control-lifecycle-deployment.json')
    deployment_guard(deployment, manifest, package, state, time.time())
    staged = dict(context, grant_expires_at=deployment['grant']['expires_at'],
        carrier_sha256=sha(carrier), deployment_sha256=sha(work / 'control-lifecycle-deployment.json'))
    write_json(work / (LABEL + '-staged.json'), staged)
    return dict(staged=True, input_sent=False, research_pid=pid, runtime_verified=False)


def snapshot(flow):
    record = workflow.verify(flow)
    package = unlinked_path(Path(record['candidate']))
    manifest = candidate.verify(package)
    owner, state = practice.owned_session()
    assert not state['restored'] and state['boss_lifecycle_experiment'] and state['offline_validation']
    assert not state['network_active'] and owner['phase'] in ('game_launched', 'armed')
    work = Path(state['work'])
    receipt = practice.read(work / (LABEL + '-staged.json'))
    assert all(receipt[k] == v for k, v in practice.read(work / (LABEL + '-intent.json')).items())
    assert receipt['state_file'] == state['state_file'] and receipt['deadline_unix'] == state['deadline_unix']
    assert receipt['workflow'] == str(unlinked_path(flow)) and receipt['workflow_sha256'] == sha(Path(flow) / 'manifest.json')
    assert receipt['source_sha256'] == sha(Path(__file__))
    assert controls.research_pid(validation) == receipt['research_pid']
    validation.verify_build(state['ue4ss_loader_manifest'])
    assert sha(Path(receipt['carrier'])) == receipt['carrier_sha256']
    assert sha(work / 'control-lifecycle-deployment.json') == receipt['deployment_sha256']
    assert validation.c.baseline.formal_files() == state['formal_before']
    deployment = practice.read(work / 'control-lifecycle-deployment.json')
    deployment_guard(deployment, manifest, package, state, time.time())
    raw = practice.log_path(state).read_bytes()
    offset = receipt['log_byte_offset']
    assert hashlib.sha256(raw[:offset]).hexdigest() == receipt['log_prefix_sha256']
    return owner, state, receipt, deployment, raw[offset:].decode('utf-8', errors='strict')


def reload_gate(flow):
    owner, state, receipt, _, tail = snapshot(flow)
    assert owner['phase'] == 'game_launched' and 'PBZ_CONTROL_LIFECYCLE:' not in tail, 'never reload a started assembly'
    assert time.time() + 120 < min(receipt['grant_expires_at'], state['deadline_unix'] - 120)
    hwnd = controls.foreground_window(validation, receipt['research_pid'])
    result = dict(window_id=hwnd, research_pid=receipt['research_pid'], key='Control_L+r',
                  gate_expires_at=time.time() + 10, state_file=state['state_file'], input_sent=False)
    write_json(Path(state['work']) / (LABEL + '-gate-' + str(time.time_ns()) + '.json'), result)
    return result


def initialization_status(tail):
    required = ('PBZ_CONTROL_LIFECYCLE:INTERACTIVE_READY=',
                'PBZ_CONTROL_LIFECYCLE:MAP_TRAVEL_GUARD_READY=true',
                'PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=')
    counts = {token: tail.count(token) for token in required}
    failures = [line for line in tail.splitlines() if any(token in line for token in
        ('state=FAULTED', 'PBZ_CONTROL_RESTORE:FAILED=', 'PBZ_CONTROL_LIFECYCLE:ISSUE_', '[Lua::execute_file]'))]
    stages = [line for line in tail.splitlines() if 'PBZ_CONTROL_LIFECYCLE:' in line]
    return dict(complete=all(count == 1 for count in counts.values()) and not failures,
        missing=[token for token, count in counts.items() if count == 0],
        duplicate=[token for token, count in counts.items() if count > 1],
        failures=failures, last_stage=stages[-1] if stages else None,
        runtime_acceptance_current=False, input_sent=False)


def initialization(tail):
    assert not any(token in tail for token in ('state=FAULTED', 'PBZ_CONTROL_RESTORE:FAILED=',
        'PBZ_CONTROL_LIFECYCLE:ISSUE_', '[Lua::execute_file]'))
    readiness = initialization_status(tail)
    assert readiness['complete'], 'one complete current player assembly required: ' + json.dumps(readiness)
    assert '[PBZBossControl] enter success=true state=ACTIVE' not in tail, 'capture idle initialization first'
    bindings = [dict(slot=a, skill=b, key=c) for a, b, c in re.findall(r'PLAYER_BINDING=(\w+)\|(\w+)\|([\w_]+)', tail)]
    assert bindings and len({b['slot'] for b in bindings}) == len(bindings)
    return bindings


def status(flow):
    _, _, _, _, tail = snapshot(flow)
    return initialization_status(tail)


def frozen_controls(flow, deployment):
    """Read the deployed schema from this verified workflow, before recording readiness."""
    frozen = workflow.verify(flow)
    source = Path(flow) / 'player_keymap.py'
    assert sha(source) == frozen['files']['player_keymap.py']
    spec = importlib.util.spec_from_file_location('pbz_frozen_travel_keymap', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    actual = dict(module.validate(deployment['player_keymap'])['controls'])
    assert actual == dict(enter='F6', exit='F10', cycle_target='F7', lock_target='MIDDLE_MOUSE_BUTTON')
    return actual


def capture(flow):
    owner, state, receipt, deployment, tail = snapshot(flow)
    assert owner['phase'] == 'game_launched'
    bindings = initialization(tail)
    actual_controls = frozen_controls(flow, deployment)
    work = Path(state['work']); path = work / (LABEL + '-capture.json')
    assert not path.exists()
    write_json(path, dict(receipt, lines=tail.splitlines(), bindings=bindings,
        controls=actual_controls, initialization_observed=True, runtime_acceptance_current=False))
    owner.update(phase='armed', log_offset=receipt['log_offset'], player_entry=True,
        scene_transition_trial=True, arena_navigation_trial=True, native_contracts_ready=True,
        actual_bindings=bindings, actual_controls=actual_controls,
        workbench=deployment.get('workbench'), boss_candidate=None, skill_lab=False, expanded=False)
    practice.save_owner(owner)
    for name, args, log in (('monitor_pid', ['tools/ahua_practice.py', '--monitor'], 'ahua-practice-monitor.log'),
                            ('hud_pid', ['tools/player_overlay.py'], 'player-overlay.log')):
        with (ROOT / 'runtime' / log).open('ab') as output:
            process = subprocess.Popen([sys.executable, '-B', '-X', 'utf8', *args], cwd=ROOT,
                stdin=subprocess.DEVNULL, stdout=output, stderr=output, creationflags=subprocess.CREATE_NO_WINDOW)
        owner[name] = process.pid
    practice.save_owner(owner)
    return dict(initialization_observed=True, input_sent=False, bindings=bindings,
        controls=actual_controls, runtime_acceptance_current=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('stage', 'reload-gate', 'status', 'capture'))
    parser.add_argument('workflow', type=Path)
    args = parser.parse_args()
    result = {'stage': stage, 'reload-gate': reload_gate, 'status': status, 'capture': capture}[args.action](args.workflow)
    print(json.dumps(result, ensure_ascii=False, indent=2))
