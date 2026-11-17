"""Read only engine ownership declarations for replacing repeated global census."""
import json
from pathlib import Path

from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields
import official_validation as validation


def collect():
    names = {'Engine', 'GameEngine', 'GameViewportClient', 'GameInstance', 'LocalPlayer', 'Player',
             'PlayerController'}
    wanted = {'GameViewport', 'GameInstance', 'LocalPlayers', 'ViewportClient', 'PlayerController', 'Player'}
    with GameRead() as game:
        rows = []
        for row in game.find_native(names, ('/Script/Engine.',)):
            address = int(row['address'], 16)
            if game.header(game.header(address)['class'])['name'] != 'Class':
                continue
            rows.append(dict(path=row['path'], properties=[p for p in fields(game, address, 512)
                                                         if p['name'] in wanted]))
        result = dict(schema=1, at=validation.utc8(), pid=game.pid, classes=rows,
                      metadata_only=True, gameplay_called=False, process_writes=False)
        path = Path(game.state['work'])/'player-controller-owner-contract.json'
        validation.save(path, result)
    print(json.dumps(dict(report=str(path), classes=rows), ensure_ascii=False))
    return result


if __name__ == '__main__':
    collect()
