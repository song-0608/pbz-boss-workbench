"""Finalize idle player readiness with the exact frozen four-control keymap.

The legacy host keymap has only three controls. This entry validates the frozen
candidate workflow's own keymap, preserving any capture written before the old
display-only keymap reader rejected lock_target. It never reloads or sends input.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import player_travel_ui_stage as stage
from boss_adaptation_workflow import ROOT, sha, write_json


def controls(flow, deployment):
    return stage.frozen_controls(flow, deployment)


def verify_partial(captured, receipt, tail):
    assert all(captured.get(key) == value for key, value in receipt.items())
    assert captured['initialization_observed'] is True and captured['runtime_acceptance_current'] is False
    lines = captured['lines']
    assert lines and tail.splitlines()[:len(lines)] == lines, 'preserve exact original idle capture'
    assert captured['bindings'] == stage.initialization('\n'.join(lines))
    assert captured['bindings'] == stage.initialization(tail), 'assembly changed after partial capture'


def capture(flow):
    owner, state, receipt, deployment, tail = stage.snapshot(flow)
    assert owner['phase'] == 'game_launched', 'never duplicate an armed assembly'
    bindings = stage.initialization(tail)
    actual_controls = controls(flow, deployment)
    work = Path(state['work'])
    prior = work / (stage.LABEL + '-capture.json')
    record = dict(receipt, lines=tail.splitlines(), bindings=bindings,
        initialization_observed=True, runtime_acceptance_current=False)
    if prior.exists():
        verify_partial(stage.practice.read(prior), receipt, tail)
    target = work / 'player-travel-finalized-capture.json'
    assert not target.exists(), 'preserve previous finalization'
    write_json(target, dict(record, controls=actual_controls, source_sha256=sha(Path(__file__)),
        prior_capture_sha256=sha(prior) if prior.exists() else None))
    owner.update(phase='armed', log_offset=receipt['log_offset'], player_entry=True,
        scene_transition_trial=True, arena_navigation_trial=True, native_contracts_ready=True,
        actual_bindings=bindings, actual_controls=actual_controls,
        workbench=deployment.get('workbench'), boss_candidate=None, skill_lab=False, expanded=False)
    stage.practice.save_owner(owner)
    for name, args, log in (('monitor_pid', ['tools/ahua_practice.py', '--monitor'], 'ahua-practice-monitor.log'),
                            ('hud_pid', ['tools/player_overlay.py'], 'player-overlay.log')):
        with (ROOT / 'runtime' / log).open('ab') as output:
            process = subprocess.Popen([sys.executable, '-B', '-X', 'utf8', *args], cwd=ROOT,
                stdin=subprocess.DEVNULL, stdout=output, stderr=output, creationflags=subprocess.CREATE_NO_WINDOW)
        owner[name] = process.pid
    stage.practice.save_owner(owner)
    return dict(initialization_observed=True, input_sent=False, bindings=bindings,
        controls=actual_controls, runtime_acceptance_current=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workflow', type=Path)
    args = parser.parse_args()
    print(json.dumps(capture(args.workflow), ensure_ascii=False, indent=2))
