"""Finite lateral positioning through the unchanged research input gates."""
import argparse
import hashlib
import json
import re
import types
from pathlib import Path
from boss_adaptation_workflow import ROOT
from native_menu_input import FROZEN


def variant(direction):
    assert direction in ('left', 'right')
    path = ROOT / 'tools/research_game_menu.py'
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == FROZEN
    source = data.decode('utf-8').replace('\r\n', '\n')
    needle = "'control_forward':83 if backward else 87"
    assert source.count(needle) == 1
    source = source.replace(needle, "'control_forward':" + str(65 if direction == 'left' else 68))
    module = types.ModuleType('bounded_terrain_position_variant')
    module.__file__ = str(path)
    exec(compile(source, str(path), 'exec'), module.__dict__)
    return module


def move(direction):
    import ahua_practice as practice
    import official_validation as validation
    owner, state = practice.owned_session()
    assert owner['phase'] == 'armed' and owner.get('player_entry')
    log = practice.log_path(state)
    before = log.read_text(encoding='utf-8', errors='replace')
    states = re.findall(r'\[PBZBossControl\] [^\r\n]* state=(\w+)', before)
    assert states and states[-1] == 'OFF', 'Restored original player required'
    assert before.rfind('WORKBENCH_INPUT_RESTORED=true') > before.rfind('WORKBENCH_INPUT_LOCKED='), 'Close workbench first'
    result = variant(direction).click(0, 0, 2560, 1600, 'control_forward')
    receipt = Path(state['work']) / 'terrain-position-actions.json'
    actions = json.loads(receipt.read_text(encoding='utf-8')) if receipt.exists() else []
    actions.append({'at': validation.utc8(), 'state_file': state['state_file'],
                    'direction': direction, 'key': 'A' if direction == 'left' else 'D',
                    'seconds': .35, 'log_offset': len(before),
                    'original_source_sha256': FROZEN, 'result': result})
    validation.save(receipt, actions)
    return result


def render_startup_camera(direction):
    """Render only a fixed gesture; retain every original isolation and lease gate."""
    assert direction in ('left', 'right', 'fine-left', 'fine-right', 'down')
    path = ROOT / 'tools/research_game_menu.py'
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == FROZEN
    source = data.decode('utf-8').replace('\r\n', '\n')
    start = source.index('    if positioning_key is not None:\n        u.keybd_event(positioning_key,0,0,0)')
    end = source.index("    if purpose in ('control_lab_next'", start)
    replacement = "    if positioning_key is not None:\n"
    replacement += "        for _ in range(6):\n"
    replacement += "            if u.GetForegroundWindow()!=h:raise RuntimeError('Research window lost focus')\n"
    dx,dy={'left':(-100,0),'right':(100,0),'fine-left':(-20,0),'fine-right':(20,0),'down':(0,40)}[direction]
    replacement += "            u.mouse_event(1," + str(dx) + "," + str(dy) + ",0,0);time.sleep(.04)\n"
    replacement += "        return {'relative_mouse_x':" + str(dx*6) + ",'relative_mouse_y':"+str(dy*6)+",'only_research_game_targeted':True}\n"
    return source[:start] + replacement + source[end:],dx,dy


def startup_look(direction):
    """One finite camera gesture before any actors are assembled."""
    source,dx,dy=render_startup_camera(direction)
    path=ROOT/'tools/research_game_menu.py'
    module = types.ModuleType('bounded_startup_camera_variant');module.__file__ = str(path)
    exec(compile(source, str(path), 'exec'), module.__dict__)
    result = module.click(0, 0, 2560, 1600, 'practice_position_left')
    import ahua_practice as practice
    import official_validation as validation
    _, state = practice.owned_session()
    receipt = Path(state['work']) / 'startup-camera-actions.json'
    actions = json.loads(receipt.read_text(encoding='utf-8')) if receipt.exists() else []
    actions.append({'at': validation.utc8(), 'state_file': state['state_file'],
                    'direction': direction, 'relative_mouse_x': dx*6, 'relative_mouse_y':dy*6,
                    'original_source_sha256': FROZEN, 'result': result})
    validation.save(receipt, actions)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('direction', choices=('left', 'right', 'look-left', 'look-right','look-fine-left','look-fine-right','look-down'))
    args = parser.parse_args()
    result = startup_look(args.direction[5:]) if args.direction.startswith('look-') else move(args.direction)
    print(json.dumps(result, ensure_ascii=False))
