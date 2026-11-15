"""用途：只读比较阿花普攻与技能06的继承、生命周期声明和蓝图调用线索；不激活普攻。"""
import configparser
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import official_validation as v
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields, functions

ROOT = Path(__file__).resolve().parents[1]
NAMES = {'GA_AHua_Attack_01_C', 'GA_AHua_Skill_06_C'}
KIND = {'Class', 'BlueprintGeneratedClass', 'LegoAbilityBlueprintGeneratedClass'}
POINTER_CALLS = {0x1C: 'EX_FinalFunction', 0x46: 'EX_LocalFinalFunction', 0x68: 'EX_CallMath'}
NAME_CALLS = {0x1B: 'EX_VirtualFunction', 0x45: 'EX_LocalVirtualFunction'}


def call_candidates(data, resolve_pointer, resolve_name):
    """用途：寻找调用操作码邻接的已验证引用；这是静态线索，不是完整反编译或执行轨迹。"""
    result = []
    for offset in range(max(0, len(data) - 8)):
        token = data[offset]
        try:
            if token in POINTER_CALLS:
                pointer = struct.unpack_from('<Q', data, offset + 1)[0]
                if pointer < 0x10000 or pointer >= 0x7FFFFFFFFFFF or pointer % 8:
                    continue
                value = resolve_pointer(pointer)
                if value:
                    result.append({'offset': offset, 'token': POINTER_CALLS[token], 'function': value})
            elif token in NAME_CALLS:
                comparison, number = struct.unpack_from('<II', data, offset + 1)
                if comparison >> 16 > 8191 or number > 10000:
                    continue
                value = resolve_name(comparison, number)
                if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', value):
                    result.append({'offset': offset, 'token': NAME_CALLS[token], 'virtual_name': value})
        except (OSError, ValueError, UnicodeError):
            continue
        if len(result) >= 256:
            break
    return result


def main():
    selected_names = NAMES
    all_ahua = '--all-ahua' in sys.argv[1:]
    if all_ahua:
        import csv
        with (ROOT / '35-阿花技能验收矩阵-非发布键位.csv').open(encoding='utf-8-sig', newline='') as stream:
            selected_names = {r['真实资源类'].rsplit('.', 1)[-1] for r in csv.DictReader(stream)
                if r['真实资源类'].startswith('/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/')}
    layout = configparser.ConfigParser()
    layout.read(ROOT / 'adaptation/pbz-26367565/MemberVariableLayout.ini', encoding='utf-8-sig')
    script_offset = int(layout['UStruct']['Script'], 0)
    selected, issues = [], []
    with GameRead() as g:
        found = []
        for index in range(g.count):
            try:
                obj = g.object(index)
                if not obj:
                    continue
                raw = g.read(obj, 40)
                name = g.name(*struct.unpack_from('<II', raw, 24))
                if name in selected_names and g.header(g.u64(obj + 0x10))['name'] in KIND:
                    path = g.path(obj)
                    if path.startswith('/PBZCombatAsset/ActorData/Mobs/042_AHua/'):
                        found.append((obj, path))
            except (OSError, ValueError, UnicodeError):
                continue
        def resolve(pointer):
            h = g.header(pointer)
            if g.header(h['class'])['name'] != 'Function':
                return None
            return g.path(pointer)
        for obj, path in found:
            chain, seen = [], set()
            owner = obj
            while owner and owner not in seen and len(chain) < 12:
                seen.add(owner)
                owner_path = g.path(owner)
                row = {'path': owner_path, 'properties': fields(g, owner, 256), 'functions': functions(g, owner)}
                pointer = g.u64(owner + 0x48)
                function_seen = set()
                bytecode = []
                while pointer and pointer not in function_seen and len(function_seen) < 256:
                    function_seen.add(pointer)
                    try:
                        h = g.header(pointer)
                        if g.header(h['class'])['name'] == 'Function':
                            data_pointer, count, capacity = struct.unpack('<Qii', g.read(pointer + script_offset, 16))
                            if not 0 <= count <= capacity <= 1_048_576 or count > 65536:
                                raise ValueError('script array bound/layout not accepted')
                            if count:
                                data = g.read(data_pointer, count)
                                bytecode.append({'function': g.path(pointer), 'bytes': count,
                                    'sha256': hashlib.sha256(data).hexdigest(),
                                    'call_candidates': call_candidates(data, resolve, g.name),
                                    'interpretation': 'opcode-neighbor reference candidates; not a complete disassembly'})
                    except (OSError, ValueError, UnicodeError) as error:
                        issues.append({'owner': owner_path, 'function_pointer': hex(pointer), 'type': type(error).__name__, 'reason': str(error)[:120]})
                    pointer = g.u64(pointer + 0x28)
                row['blueprint_call_candidates'] = bytecode
                chain.append(row)
                owner = g.u64(owner + 0x40)
            selected.append({'class': path, 'inheritance': chain})
        report = {'at': v.utc8(), 'pid': g.pid, 'objects': selected, 'issues': issues,
            'found_class_count': len(found), 'scope': 'read-only loaded Ahua lifecycle metadata; no activation, function calls or save parsing',
            'script_layout_source': 'adaptation/pbz-26367565/MemberVariableLayout.ini',
            'token_source': 'upstream/RE-UE4SS/deps/first/Unreal/include/Unreal/Script.hpp'}
        output = Path(g.state['work']) / ('ahua-all-ability-lifecycle-contract.json' if all_ahua else 'ahua-attack-lifecycle-contract.json')
        v.save(output, report)
        if not all_ahua:
            v.save(ROOT / 'evidence/adaptation/latest-ahua-attack-lifecycle-contract.json', report)
        print(json.dumps({'report': str(output), 'found': [r['class'] for r in selected], 'issues': len(issues)}, ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
