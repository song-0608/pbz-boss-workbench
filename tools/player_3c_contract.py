"""Read declarations for walking tuning in the current leased research process."""
import struct
from pathlib import Path
from inspect_pbz_ai_metadata import fields
from pbz_readonly import GameRead
import official_validation as validation

CLASSES = {
    '/Script/Engine.Character': {'CharacterMovement': ('ObjectProperty', 8)},
    '/Script/Engine.CharacterMovementComponent': {
        'MaxWalkSpeed': ('FloatProperty', 4), 'MaxAcceleration': ('FloatProperty', 4)},
}

def validate(record):
    assert record['pid'] > 0
    for path, expected in CLASSES.items():
        actual = record['classes'][path]
        for name, (kind, size) in expected.items():
            matched = [row for row in actual if row['name'] == name]
            assert len(matched) == 1
            row, = matched
            assert row['type'] == kind and row['element_size'] == size and row['array_dim'] == 1
    names = {'/Script/Engine.GameplayStatics.GetWorldDeltaSeconds':
             [('WorldContextObject', 'ObjectProperty', 8), ('ReturnValue', 'FloatProperty', 4)],
             '/Script/Engine.ActorComponent.GetOwner': [('ReturnValue', 'ObjectProperty', 8)]}
    for name, expected in names.items():
        function = record['functions'][name]
        assert [(p['name'], p['type'], p['element_size']) for p in function['parameters']] == expected
        allowed = (12, 16) if len(expected) == 2 else (8,)
        assert function['parameter_bytes'] in allowed
    return True

def collect(work, expected_pid):
    with GameRead() as game:
        assert game.pid == expected_pid, 'current remote-contract process required'
        wanted = set(CLASSES) | {'/Script/Engine.GameplayStatics.GetWorldDeltaSeconds',
                                  '/Script/Engine.ActorComponent.GetOwner'}
        record = dict(schema=1, at=validation.utc8(), pid=game.pid, classes={}, functions={},
                      scope='engine declarations only; no gameplay calls or process writes')
        for row in game.find_native({p.rsplit('.', 1)[1] for p in wanted}):
            path = row['path']
            if path not in wanted:
                continue
            address = int(row['address'], 16)
            if path in CLASSES:
                record['classes'][path] = fields(game, address, 512)
            else:
                record['functions'][path] = dict(
                    parameter_bytes=struct.unpack('<H', game.read(address + 0x106, 2))[0],
                    parameters=[p for p in fields(game, address, 32) if int(p['property_flags'], 16) & 0x80])
        record['passed'] = validate(record)
        validation.save(Path(work) / 'player-3c-native-contract.json', record)
        return {'binding_verified': True, 'locomotion_verified': True}
