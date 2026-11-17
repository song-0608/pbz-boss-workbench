"""Read-only, focus-scoped input gate for the exact travel-repair developer payload."""
import argparse
from pathlib import Path
import re

import player_experience_trial as inherited
import player_travel_workflow as workflow
import build_player_travel_candidate as candidate

NATIVE_ACTIONS = {'native_interact': 'e', 'native_confirm': 'Return', 'native_down': 'Down',
                  'native_up': 'Up', 'native_back': 'Escape', 'native_choose': 'LEFT_MOUSE_BUTTON'}

def validate_action(action, owner, deployment, text):
    actions = dict(inherited.ACTIONS, **NATIVE_ACTIONS, primary='LEFT_MOUSE_BUTTON',
                   workbench_alias='Shift_L+F6', workbench_active='F6',
                   picker_up='F1', picker_down='F2', picker_confirm='F6', cross_map='F12')
    assert action in actions, 'Bounded trial action required'
    assert owner.get('phase') == 'armed' and owner.get('player_entry')
    assert not any(owner.get(k) for k in ('skill_lab', 'expanded', 'boss_candidate'))
    assert deployment.get('player_entry') and not deployment.get('boss_candidate')
    controls = owner.get('actual_controls', {})
    assert all(controls.get(k) == v for k, v in (
        ('enter', 'F6'), ('exit', 'F10'), ('cycle_target', 'F7'), ('lock_target', 'MIDDLE_MOUSE_BUTTON')))
    current = text[owner['log_offset']:]
    assert not any(token in current for token in ('state=FAULTED', 'ISSUE_', '[Lua::execute_file]'))
    # Opening the workbench restores ACTIVE, and selecting a role creates a new
    # OFF runtime. Both are native events, not synthetic exit attestations.
    entered = current.rfind('[PBZBossControl] enter success=true state=ACTIVE')
    off = [m.start() for m in re.finditer(
        r'\[PBZBossControl\] (?:exit|auto_exit|menu_exit|workbench_toggle|stop) success=true state=OFF', current)]
    exited = max([current.rfind('PBZ_CONTROL_LIFECYCLE:' + label + '=') for label in
                  ('PLAYER_ENTRY_READY', 'WORKBENCH_BOSS_SELECTED', 'MAP_TRAVEL_IDLE_CLEANED')] + off)
    active = entered >= 0 and entered > exited
    if action in ('lock', 'cycle_target', 'cast', 'shift_cast', 'exit', 'primary', 'workbench_active', 'cross_map'):
        assert active, 'Current successful active takeover required'
    if action in ('enter', 'down', 'up', 'confirm', 'close', 'picker_up', 'picker_down', 'picker_confirm'):
        assert not active, 'Restore the player before selecting or entering'
    if action in ('down', 'up', 'confirm', 'close', 'picker_up', 'picker_down', 'picker_confirm'):
        assert current.rfind('WORKBENCH_INPUT_LOCKED=') > current.rfind('WORKBENCH_INPUT_RESTORED=true')
    if action in NATIVE_ACTIONS:
        from research_game_menu import validate_control_menu_transition
        assert not active, 'Restore before native map menus'
        validate_control_menu_transition(owner, text)
    if action == 'workbench_alias':
        assert 'WORKBENCH_SHORTCUT_READY=SHIFT+F6' in current
    if action == 'cross_map':
        assert owner.get('scene_transition_trial') and deployment.get('scene_transition_trial')
        assert 'TRANSITION_TRIAL_KEY=F12; native travel between observed valley/forest packages once' in current
        assert 'CROSS_MAP_TRIAL_ROUTE=' not in current, 'Only one cross-map request per session'
    if action in ('cast', 'shift_cast', 'primary'):
        # Read actual bindings from the latest assembly, not the initial owner.
        begin = current.rfind('PBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT=')
        assembly = current[max(0, begin):]
        assert 'PLAYER_BINDING=slot1|skill_01|F1' in assembly
    if action == 'primary':
        assert sum(row.get('slot') == 'primary_attack' and row.get('key') == 'LEFT_MOUSE_BUTTON'
                   for row in owner.get('actual_bindings', [])) == 1, 'Current role has no primary mouse binding'
        assert re.search(r'PLAYER_BINDING=primary_attack\|[^|]+\|LEFT_MOUSE_BUTTON', assembly)
    return actions[action]


def gate(flow, action):
    # Inherit all original lease, isolation, exact deployment and foreground checks.
    saved = inherited.workflow, inherited.candidate, inherited.validate_action
    inherited.workflow, inherited.candidate, inherited.validate_action = workflow, candidate, validate_action
    try:
        return inherited.gate(flow, action)
    finally:
        inherited.workflow, inherited.candidate, inherited.validate_action = saved


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workflow', type=Path)
    parser.add_argument('action', choices=(*inherited.ACTIONS, *NATIVE_ACTIONS,
                                         'primary', 'workbench_alias', 'workbench_active',
                                         'picker_up', 'picker_down', 'picker_confirm', 'cross_map'))
    args = parser.parse_args()
    gate(args.workflow.resolve(), args.action)
