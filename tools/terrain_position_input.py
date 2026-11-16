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
    source = data.decode('utf-8')
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('direction', choices=('left', 'right'))
    args = parser.parse_args()
    print(json.dumps(move(args.direction), ensure_ascii=False))
