"""只读核对本轮自建角色Owner/Instigator链上的Actor；不回收未知或场景原有对象。"""
import argparse
import json
from pathlib import Path
import re
import struct
import sys
import ahua_practice as practice
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('label')
    args = parser.parse_args()
    assert re.fullmatch(r'[a-z0-9-]{1,40}', args.label)
    owner, state = practice.owned_session()
    text = practice.log_path(state).read_text(encoding='utf-8', errors='replace')[owner['log_offset']:]
    refs = re.findall(r'OWNED_RETIRE_REFERENCE=actor\|([^|\r\n]+)\|address=(\d+)\|class=([^\r\n]+)', text)
    assert len(refs) == 3, 'three exact live assembly references required'
    addresses = {int(address): name.partition(' ')[2] for name, address, _ in refs}
    with GameRead() as game:
        actor = next(r for r in game.find_native({'Actor'}) if r['path'] == '/Script/Engine.Actor')
        base = int(actor['address'], 16)
        props = {p['name']: p for p in fields(game, base, 512)}
        selected = {key: int(props[key]['offset'], 16) for key in ('Owner', 'Instigator')}
        derived = {}
        def is_actor(cls):
            if cls in derived:
                return derived[cls]
            seen = set()
            current = cls
            while current and current not in seen and len(seen) < 32:
                if current == base:
                    derived[cls] = True
                    return True
                seen.add(current)
                current = game.u64(current + 0x40)
            derived[cls] = False
            return False
        rows = []
        for index in range(game.count):
            try:
                obj = game.object(index)
                if not obj:
                    continue
                header = game.header(obj)
                if header['flags'] & 0x10 or not is_actor(header['class']):
                    continue
                matches = []
                for key, offset in selected.items():
                    current = game.u64(obj + offset)
                    chain = []
                    for _ in range(4):
                        if not current or current in chain:
                            break
                        chain.append(current)
                        if current in addresses:
                            matches.append({'field': key, 'source': addresses[current], 'chain': [hex(p) for p in chain]})
                            break
                        if not is_actor(game.header(current)['class']):
                            break
                        current = game.u64(current + selected['Owner'])
                if matches:
                    rows.append({'path': game.path(obj), 'address': hex(obj), 'class': game.path(header['class']),
                                 'flags': hex(header['flags']), 'matches': matches})
                    assert len(rows) <= 512, 'bounded owned actor scan exceeded'
            except (OSError, ValueError, UnicodeError):
                continue
        result = {'pid': game.pid, 'state_file': state['state_file'], 'label': args.label,
                  'source_references': refs, 'properties': [props[k] for k in selected], 'actors': rows,
                  'scope': 'read only owner/instigator references; listed UObjects may already be engine-unusable; no GC claim'}
        path = Path(state['work']) / ('owned-residuals-' + args.label + '.json')
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'report': str(path), 'actors': [{'path': r['path'], 'class': r['class']} for r in rows]}, ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
