"""Select a manifest-listed role through the existing native workbench keys only."""
import argparse
import importlib
from pathlib import Path
import re
import sys

import expanded_boss_integration_workflow as workflow
import build_expanded_boss_candidate as candidate


def select(flow, identifier):
    frozen = workflow.verify(flow); manifest = candidate.verify(Path(frozen['candidate']))
    order = [row['id'] for row in manifest['bosses']]
    assert identifier in order
    sys.path.insert(0, str(flow))
    practice = importlib.import_module('ahua_practice')
    dispatch = importlib.import_module('test_player_experience_inputs').main
    wait_for = importlib.import_module('test_player_skill_batch').wait_for
    owner, state = practice.owned_session(); path = practice.log_path(state)
    text = path.read_text(encoding='utf-8', errors='replace')
    current = re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)', text)[-1]
    assert current in order
    if current == identifier:
        print('Already selected: ' + identifier); return
    def send(action, predicate, seconds=12):
        start = len(path.read_text(encoding='utf-8', errors='replace'))
        dispatch(flow, action); tail = wait_for(path, start, predicate, seconds, True)
        assert predicate(tail), 'Native workbench result missing'
    send('workbench', lambda t: 'WORKBENCH_INPUT_LOCKED=' in t)
    delta = order.index(identifier) - order.index(current)
    action = 'down' if delta > 0 else 'up'
    for _ in range(abs(delta)):
        send(action, lambda t: 'workbench_' + action + ' success=true' in t)
    send('confirm', lambda t: ('PLAYER_ENTRY_READY=' + identifier) in t
         and ('WORKBENCH_BOSS_SELECTED=' + identifier) in t and 'WORKBENCH_INPUT_RESTORED=true' in t, 80)
    print('Selected with native workbench: ' + identifier)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('workflow', type=Path)
    parser.add_argument('identifier'); args = parser.parse_args()
    select(args.workflow.resolve(), args.identifier)
