"""只读核对当前研究进程的视线、屏幕提示和显式切图接口。"""
import json
import struct
from pathlib import Path
import official_validation as v
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields

FUNCTIONS = {
    '/Script/Engine.Controller.LineOfSightTo',
    '/Script/Engine.KismetSystemLibrary.PrintString',
    '/Script/Engine.GameplayStatics.OpenLevel',
    '/Script/Engine.HUD.DrawText',
    '/Script/Engine.HUD.ReceiveDrawHUD',
    '/Script/Engine.HUD.GetOwningPlayerController',
}


def collect():
    declarations = []
    with GameRead() as g:
        for row in g.find_native({p.rsplit('.', 1)[1] for p in FUNCTIONS}):
            if row['path'] not in FUNCTIONS:
                continue
            address = int(row['address'], 16)
            declarations.append({
                'path': row['path'],
                'parameter_bytes': struct.unpack('<H', g.read(address + 0x106, 2))[0],
                'parameters': [p for p in fields(g, address, 32) if int(p['property_flags'], 16) & 0x80],
            })
        missing = sorted(FUNCTIONS - {f['path'] for f in declarations})
        result = {'at': v.utc8(), 'pid': g.pid, 'passed': not missing,
                  'missing': missing, 'functions': declarations,
                  'scope': 'read-only reflected declarations; no native calls'}
        target = Path(g.state['work']) / 'player-ui-native-contract.json'
        v.save(target, result)
    print(json.dumps({'report': str(target), 'missing': missing, 'functions': declarations}, ensure_ascii=False))


if __name__ == '__main__':
    collect()
