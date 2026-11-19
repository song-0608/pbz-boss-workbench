"""Read-only action gate for separately dispatched research-window key presses."""
import argparse
import json
from pathlib import Path
import re
import time
from uuid import uuid4

from boss_adaptation_workflow import sha
from control_action_evidence import control_identity, restoration_result
from player_target_readiness import latest_target_status
import native_grant_ui_stage as flow


def remaining_budget(receipt, state, purpose, now):
    # Keep the existing exit reserve. New work also needs the ten-second key
    # window, the developer module's 30-second skill timeout and another fresh
    # validation before restoration. A late cast must not consume that reserve.
    reserve = {'enter': 120, 'cast': 90, 'exit': 30}[purpose]
    remaining = min(receipt['grant_expires_at'], state['deadline_unix'] - 120) - now
    assert remaining > reserve, 'reserve time for action and restoration'
    return reserve, remaining


def choose_action(tail, manifest, capture, definition, state, purpose, skill, now):
    assert purpose in ('enter', 'cast', 'exit')
    assert capture['id'] == manifest['id'] and capture['state_file'] == state['state_file']
    assert not any(token in tail for token in ('state=FAULTED', 'PBZ_CONTROL_RESTORE:FAILED=',
                                              'PBZ_CONTROL_LIFECYCLE:ISSUE_'))
    enter = tail.rfind('[PBZBossControl] enter success=true state=ACTIVE')
    exits = [tail.rfind('[PBZBossControl] ' + event + ' success=true state=OFF')
             for event in ('exit', 'menu_exit', 'auto_exit', 'stop')]
    active = enter >= 0 and enter > max(exits)
    if purpose == 'enter':
        assert not active and skill is None, 'do not repeat an active takeover'
        if enter >= 0:
            assert restoration_result(tail[enter:])['passed'], 'complete previous recovery required'
        return dict(key='F6', purpose=purpose)
    assert active, 'verified active takeover required'
    live = tail[enter:]
    identity = control_identity(live)
    assert identity and identity['participants']['boss']['class'].split(' ', 1)[-1] == definition['class_path']
    if purpose == 'exit':
        assert skill is None
        return dict(key='F10', purpose=purpose, identity=identity)
    assert skill is not None and not any(token in live for token in ('success=false', 'SKILL_NATIVE_REJECTED=')), \
        'do not automatically retry native rejection'
    begins = list(re.finditer(r'KEY_SKILL_BEGIN=([^|\r\n]+)\|', live))
    assert all(row[1] == skill for row in begins), 'keep one skill per consecutive-release trial'
    if begins:
        last = begins[-1]
        assert len(re.findall(r'KEY_SKILL_END=' + re.escape(last[1]) +
            r'\|peak=[1-9]\d*\|active=0\|natural=true\|', live[last.end():])) == 1, 'previous skill still active or unconfirmed'
    bound = [r for r in capture['bindings'] if r['skill'] == skill]
    assert len(bound) == 1 and bound[0]['class_path'] in definition['ability_pool']
    registrations = re.findall(r'PLAYER_BINDING=([^|\r\n]+)\|([^|\r\n]+)\|([^\r\n]+)', tail[:enter])
    rows = [r for r in registrations if r[1] == skill]
    assert len(rows) == 1 and rows[0][2] in ('F1', 'F2', 'F3', 'F4'), 'exact developer key registration required'
    status = latest_target_status(live, Path(state['state_file']).parent.name, now, definition['display_name'])
    assert status and status['visibility'] == 'visible', 'fresh ACTIVE visible target required'
    return dict(key=rows[0][2], purpose=purpose, skill=skill,
                class_path=bound[0]['class_path'], identity=identity, target=status['target'])


def choose_cancel_trial(tail, manifest, capture, definition, state, skill, now):
    """Prepare one explicit cast and its recovery from the same fresh proof.

    These are two bounded permissions, not an input sender or an observation
    that cancellation happened. Native logs must still prove activity at F10.
    """
    assert manifest.get('kind') == 'native_combo_ui_stage', 'reviewed native combo workflow required'
    assert manifest.get('developer_only') is True and manifest.get('playable') is False
    assert skill == 'skill_01' and definition['ability_pool'] == [definition['parent_class']], \
        'one exact reviewed native parent required'
    cast = choose_action(tail, manifest, capture, definition, state, 'cast', skill, now)
    restore = choose_action(tail, manifest, capture, definition, state, 'exit', None, now)
    assert cast['identity'] == restore['identity'], 'one exact active takeover required'
    return [cast, restore]


def gate(workflow, purpose, skill=None):
    import official_validation as validation
    manifest, state, receipt, tail = flow.staged_guard(workflow)
    work = Path(state['work']); capture_path = work / (flow.LABEL + '-capture.json')
    capture = json.loads(capture_path.read_bytes())
    assert capture['workflow_manifest_sha256'] == receipt['workflow_manifest_sha256']
    assert capture['initialization_observed'] is True
    assert tail.splitlines()[:len(capture['lines'])] == capture['lines'], 'retain exact captured initialization prefix'
    capture = dict(capture, workflow=str(workflow.resolve()))
    definition = flow.bundle.read(Path(manifest['bundle']) / 'manifest.json')['definition']
    now = time.time()
    paired = purpose == 'cast-cancel'
    budget_purpose = 'cast' if paired else purpose
    remaining_budget(receipt, state, budget_purpose, now)
    if paired:
        action = dict(purpose=purpose, actions=choose_cancel_trial(
            tail, manifest, capture, definition, state, skill, now),
            max_action_count=2, active_cancellation_observed=False)
    else:
        action = choose_action(tail, manifest, capture, definition, state, purpose, skill, now)
    hwnd = flow.foreground_window(validation, receipt['research_pid'])
    issued = time.time()
    reserve, remaining = remaining_budget(receipt, state, budget_purpose, issued)
    result = dict(action, window_id=hwnd, research_pid=receipt['research_pid'],
        state_file=state['state_file'], gate_expires_at=issued + 10, input_sent=False,
        workflow_manifest_sha256=receipt['workflow_manifest_sha256'], capture_sha256=sha(capture_path),
        action_and_restore_reserve_seconds=reserve, remaining_seconds_at_issue=remaining,
        observed_log_tail_sha256=__import__('hashlib').sha256(tail.encode()).hexdigest())
    # Simultaneous validators can share a clock tick, including for the same
    # purpose. Never let their JSON writes overlap or overwrite prior evidence.
    path = work / ('native-grant-skill-gate-' + purpose + '-' + str(time.time_ns()) + '-' + uuid4().hex + '.json')
    with path.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workflow', type=Path); parser.add_argument('purpose', choices=('enter', 'cast', 'exit', 'cast-cancel'))
    parser.add_argument('--skill'); args = parser.parse_args()
    print(json.dumps(gate(args.workflow, args.purpose, args.skill), ensure_ascii=False, indent=2))
