"""只读定位本轮真实GameInstance及其继承声明；不调用加载、不读取存档数据。"""
import json
from pathlib import Path
import re
import sys
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields, functions
import official_validation as v


def collect():
    with GameRead() as g:
        base = next(r for r in g.find_native({'PBZGameInstance'})
                    if r['path'] == '/Script/ProjectPBZ.PBZGameInstance')
        base_address = int(base['address'], 16)
        ancestry = {}

        def derives(address):
            if address in ancestry:
                return ancestry[address]
            chain = []
            current = address
            for _ in range(32):
                if not current or current in chain:
                    break
                chain.append(current)
                if current == base_address:
                    ancestry[address] = chain
                    return chain
                current = g.u64(current + 0x40)
            ancestry[address] = None
            return None

        instances = []
        for index in range(g.count):
            address = g.object(index)
            if not address:
                continue
            try:
                header = g.header(address)
                if header['flags'] & 0x10 or header['name'].startswith('Default__'):
                    continue
                chain = derives(header['class'])
                if chain:
                    instances.append({'path': g.path(address), 'address': hex(address),
                                      'class': g.path(header['class']), 'chain': chain})
            except (OSError, ValueError, UnicodeError):
                continue
        if len(instances) != 1:
            raise RuntimeError('Exactly one live research GameInstance required: ' + str(len(instances)))
        instance = instances[0]
        classes = []
        for address in instance.pop('chain'):
            classes.append({'path': g.path(address),
                            'properties': fields(g, address, 512),
                            'functions': functions(g, address)})
        result = {'at': v.utc8(), 'pid': g.pid, 'instance': instance, 'classes': classes,
                  'scope': 'read-only actual GameInstance class declarations; no gameplay calls or save data'}
        target = Path(g.state['work']) / 'game-flow-instance-contract.json'
        v.save(target, result)
        print(json.dumps({'report': str(target), 'instance': instance,
            'flow_functions': [{'class': c['path'], 'functions': [f for f in c['functions']
                if re.search('load|restart|return|continue|menu|checkpoint|travel', f['name'], re.I)]}
                for c in classes]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    collect()
