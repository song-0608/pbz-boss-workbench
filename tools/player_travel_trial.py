"""Read-only, focus-scoped input gate for the exact travel-repair developer payload."""
import argparse
from pathlib import Path
import re

import player_experience_trial as inherited
import player_travel_workflow as workflow
import build_player_travel_candidate as candidate

NATIVE_ACTIONS = {'native_interact': 'e', 'native_confirm': 'Return', 'native_down': 'Down',
                  'native_up': 'Up', 'native_back': 'Escape', 'native_choose': 'LEFT_MOUSE_BUTTON',
                  'native_map': 'Tab'}
MOVEMENT_ACTIONS = {'forward': 'w', 'backward': 's', 'strafe_left': 'a', 'strafe_right': 'd'}
WANJUN_ACTIONS = {'native_light': ('skill_07', 'F9'), 'native_blue_cue': ('heavy_01', 'F2'),
                  'native_retreat': ('teleport_left', 'Q')}

def validate_action(action, owner, deployment, text):
    actions = dict(inherited.ACTIONS, **NATIVE_ACTIONS, primary='LEFT_MOUSE_BUTTON', defense='RIGHT_MOUSE_BUTTON',
                   workbench_alias='Shift_L+F6', workbench_active='F6',
                   picker_up='F1', picker_down='F2', picker_confirm='F6', prepare_native_travel='F12')
    actions.update(MOVEMENT_ACTIONS)
    actions.update({name: key for name, (_, key) in WANJUN_ACTIONS.items()})
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
    if action in MOVEMENT_ACTIONS or action in WANJUN_ACTIONS or action in (
            'lock', 'cycle_target', 'cast', 'shift_cast', 'exit', 'primary', 'defense', 'workbench_active', 'prepare_native_travel'):
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
    if action == 'prepare_native_travel':
        assert owner.get('scene_transition_trial') and deployment.get('scene_transition_trial')
        assert 'TRANSITION_TRIAL_KEY=F12; restore once for native map menu travel' in current
        assert 'NATIVE_TRAVEL_MENU_READY=' not in current, 'Only one native travel preparation per session'
    if action in ('cast', 'shift_cast', 'primary') or action in WANJUN_ACTIONS:
        # Read actual bindings from the latest assembly, not the initial owner.
        begin = current.rfind('PBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT=')
        assembly = current[max(0, begin):]
        assert 'PLAYER_BINDING=slot1|skill_01|F1' in assembly
    if action == 'primary':
        bindings = re.findall(r'PLAYER_BINDING=primary_attack\|([^|\r\n]+)\|LEFT_MOUSE_BUTTON(?:\r?\n|$)', assembly)
        assert len(bindings) == 1, 'Current assembly requires exactly one primary mouse binding'
    if action == 'defense':
        assert deployment.get('native_combat_controls', {}).get('developer_only') is True
        roles = re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)', current[:entered])
        assert roles and roles[-1] == '056_youlong'
        assert re.search(r'NATIVE_DEFENSE_READY=RIGHT_MOUSE_BUTTON\r?\n', current[exited:entered]), \
            'Current takeover requires a verified native stance binding'
    if action in WANJUN_ACTIONS:
        assert 'PLAYER_ENTRY_READY=057_wanjun' in assembly, 'Current WanJun assembly required'
        slot, key = WANJUN_ACTIONS[action]
        binding = re.escape(f'PLAYER_BINDING={slot}|{slot}|{key}')
        bindings = re.findall(binding + r'(?:\r?\n|$)', assembly)
        assert len(bindings) == 1, 'Current assembly requires exactly one native ' + slot + ' binding'
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
    parser.add_argument('action', choices=(*inherited.ACTIONS, *NATIVE_ACTIONS, *MOVEMENT_ACTIONS,
                                         'primary', 'defense', 'workbench_alias', 'workbench_active',
                                         'picker_up', 'picker_down', 'picker_confirm', 'prepare_native_travel',
                                         *WANJUN_ACTIONS))
    args = parser.parse_args()
    gate(args.workflow.resolve(), args.action)
