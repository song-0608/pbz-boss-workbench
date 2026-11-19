"""Validate bounded offline combat scripts and evaluate the exact cue faction gate.

This interpreter accepts only the small pure Begin graph seen in the native cue.
It does not execute game functions or infer runtime behavior from declarations.
"""
import argparse
import json
from pathlib import Path

import boss_disk_declarations as disk

CUE_PACKAGE = ('ProjectPBZ/Plugins/Secret/PBZCombatAsset/Content/Prototypes/'
               'Actions/GAAction_WeaponParticle_BlueRedEye.uasset')


def statements(function):
    rows = function.get('statements', [])
    if not function.get('complete') or not 1 <= len(rows) <= 4096:
        raise ValueError('Complete bounded native script required')
    offsets = [r['offset'] for r in rows]
    if (any(type(n) is not int or n < 0 for n in offsets) or offsets != sorted(set(offsets))
            or offsets[0] != 0 or rows[-1]['expression'].get('Token') != 'EX_EndOfScript'):
        raise ValueError('Invalid script offsets or missing EndOfScript')
    return {r['offset']: r['expression'] for r in rows}


def cue_begin(function, relation):
    if function.get('name') != 'Received_ActionBegin' or type(relation) is not int or relation not in (0, 1, 2):
        raise ValueError('Exact cue begin and native relation enum required')
    rows = statements(function)
    order = list(rows)
    variables, calls, spawns = {}, [], []

    def evaluate(expr):
        token = expr['Token']
        if token == 'EX_Self':
            return 'cue_action'
        if token in ('EX_IntConst', 'EX_ByteConst'):
            return expr['Value']
        if token == 'EX_LocalVariable':
            return variables[expr['Variable']['Property']['Name']]
        if token in ('EX_CallMath', 'EX_FinalFunction', 'EX_LocalVirtualFunction'):
            name = expr['Function']
            params = [evaluate(p) for p in expr['Parameters']]
            if name == dict(ObjectName="Class'GameplayStatics:GetPlayerPawn'", ObjectPath='/Script/Engine'):
                if params != ['cue_action', 0]:
                    raise ValueError('Cue local player query changed')
                calls.append('local_player');return 'local_player'
            if name == dict(ObjectName="Class'LGAAction:GetAvatarActor'", ObjectPath='/Script/LegoAbility'):
                if params:
                    raise ValueError('Cue avatar query changed')
                calls.append('avatar');return 'avatar'
            if name == dict(ObjectName="Class'FactionUtils:GetFactionRelation'", ObjectPath='/Script/SGameCombatSystem'):
                if params != ['avatar', 'local_player']:
                    raise ValueError('Cue faction argument order changed')
                calls.append('relation');return relation
            if name == dict(ObjectName="Class'KismetMathLibrary:EqualEqual_ByteByte'", ObjectPath='/Script/Engine'):
                if len(params) != 2:
                    raise ValueError('Cue comparison changed')
                return params[0] == params[1]
            if name == 'Spawn Particles' and token == 'EX_LocalVirtualFunction':
                if params != ['avatar']:
                    raise ValueError('Cue native spawn owner changed')
                spawns.append('avatar');return None
        raise ValueError('Unsupported cue expression: '+str(token))

    pc = 0
    for _ in range(32):
        expr = rows[pc];token = expr['Token']
        if token in ('EX_LetObj', 'EX_Let', 'EX_LetBool'):
            variable = expr['Variable']
            if variable['Token'] != 'EX_LocalVariable':
                raise ValueError('Unexpected cue nonlocal assignment')
            variables[variable['Variable']['Property']['Name']] = evaluate(expr['Expression'])
        elif token == 'EX_JumpIfNot':
            if not evaluate(expr['BooleanExpression']):
                pc = expr['CodeOffset']
                if pc not in rows:
                    raise ValueError('Cue branch target is not a statement boundary')
                continue
        elif token == 'EX_Return':
            if expr['Expression'] != {'Token': 'EX_Nothing'}:
                raise ValueError('Cue return changed')
            if calls.count('relation') != 1:
                raise ValueError('Exactly one native faction query required')
            return dict(relation=relation, native_spawn_calls=len(spawns), owners=spawns)
        else:
            evaluate(expr)
        position = order.index(pc)+1
        if position >= len(order):
            raise ValueError('Cue script ended without return')
        pc = order[position]
    raise ValueError('Cue Begin bounded evaluator exhausted')


def build(directory):
    directory = Path(directory)
    receipt = json.loads((directory/'result.json').read_bytes())
    if (receipt.get('kind') != 'offline_native_combat_blueprint_scripts' or not receipt.get('passed')
            or receipt.get('game_started') is not False or receipt.get('runtime_behavior_verified') is not False):
        raise ValueError('Successful offline script receipt required')
    functions, sources, total = None, {}, 0
    if not 1 <= len(receipt['packages']) <= 8:
        raise ValueError('Bounded combat scripts required')
    for row in receipt['packages']:
        name = row['script_file']
        if Path(name).name != name or '/' in name or '\\' in name:
            raise ValueError('Local script filename required')
        path = directory/name
        if disk.digest(path) != row['sha256'] or not row['passed']:
            raise ValueError('Script digest or completion mismatch')
        records = json.loads(path.read_bytes())
        if len(records) != row['functions'] or len(records) != row['complete_functions']:
            raise ValueError('Function coverage mismatch')
        for record in records:
            statements(record)
        total += len(records);sources[name] = row['sha256']
        if row['package'] == CUE_PACKAGE:
            if functions is not None:
                raise ValueError('Duplicate cue package')
            functions = {f['name']: f for f in records}
            if len(functions) != len(records):
                raise ValueError('Duplicate cue function')
    if not functions:
        raise ValueError('Exact native cue package required')
    results = [cue_begin(functions['Received_ActionBegin'], relation) for relation in (0, 1, 2)]
    if [r['native_spawn_calls'] for r in results] != [0, 0, 1]:
        raise ValueError('Native cue faction gate changed; no fallback can be signed')
    return dict(schema=1, kind='native_combat_script_audit', packages=len(receipt['packages']),
        complete_functions=total, cue_faction_branches=results,
        cue_spawn_requires_hostile_relation=True,
        sources=dict(receipt_sha256=disk.digest(directory/'result.json'), script_sha256=sources,
                     exporter_sha256=receipt['tool_sha256'], mapping_sha256=receipt['mapping_sha256'],
                     audit_sha256=disk.digest(__file__)),
        pure_script_simulation=True, runtime_behavior_verified=False, cue_render_verified=False,
        defense_runtime_verified=False, game_started=False, installed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path);parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args();result = build(args.directory);disk.write_new(args.output, result)
    print(json.dumps({k:v for k,v in result.items() if k != 'sources'}, ensure_ascii=False))
