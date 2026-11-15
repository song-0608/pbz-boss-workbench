"""用途：只读本轮明确生成的三个训练角色位置，判断初始化失效是否伴随离开平台；不探图。"""
import json
from pathlib import Path
import re
import struct
import sys
import ahua_practice as practice
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields


def main():
    owner, state = practice.owned_session()
    text = practice.log_path(state).read_text(encoding='utf-8', errors='replace')
    text = text[text.rfind('PBZ_CONTROL_LIFECYCLE:DEFERRED_ACTOR='):]
    paths = re.findall(r'PBZ_CONTROL_LIFECYCLE:(?:SPAWNED|TRAINING_TARGET_[12])=[^ ]+ ([^\r\n]+)', text)
    names = {p.rsplit('.', 1)[1] for p in paths}
    with GameRead() as g:
        contract = json.loads((Path(state['work']) / 'camera-native-contract.json').read_text(encoding='utf-8'))
        root_offset = int(next(p['offset'] for p in contract['properties'] if p['owner'] == '/Script/Engine.Actor' and p['name'] == 'RootComponent'), 16)
        scene = next(r for r in g.find_native({'SceneComponent'}) if r['path'] == '/Script/Engine.SceneComponent')
        props = {p['name']: p for p in fields(g, int(scene['address'], 16))}
        selected = [props[k] for k in ('RelativeLocation', 'ComponentVelocity', 'AttachParent')]
        rows = []
        for index in range(g.count):
            try:
                address = g.object(index)
                if not address:
                    continue
                raw = g.read(address, 40)
                if g.name(*struct.unpack_from('<II', raw, 24)) not in names:
                    continue
                root = g.u64(address + root_offset)
                row = {'name': g.header(address)['name'], 'actor_address': hex(address), 'root_address': hex(root)}
                for prop in selected:
                    offset = int(prop['offset'], 16)
                    row[prop['name']] = struct.unpack('<ddd', g.read(root + offset, 24)) if prop['element_size'] == 24 else hex(g.u64(root + offset))
                rows.append(row)
                if len(rows) >= len(names):
                    break
            except (OSError, ValueError, UnicodeError):
                continue
        result = {'pid': g.pid, 'rows': rows, 'properties': selected, 'scope': 'read-only owned training actors; no game function calls or map scan'}
        (Path(state['work']) / 'owned-training-positions.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
