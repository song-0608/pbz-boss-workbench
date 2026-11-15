"""One bounded read-only FName batch; does not load assets, navigate or send input."""
from __future__ import annotations

from datetime import datetime
import json
import re
import struct
import time

PREFIX = '/PBZCombatAsset/ActorData/Mobs/'
PACKAGE = re.compile(r'^/PBZCombatAsset/ActorData/Mobs/[A-Za-z0-9_]+/[A-Za-z0-9_/]+(?:\.[A-Za-z0-9_]+)*$')


def parse_block(data):
    """Stop at invalid/trailing entries, following the build-verified 2-byte stride."""
    if len(data) > 65536:
        raise ValueError('FName block exceeds 64 KiB')
    offset = 0
    while offset + 2 <= len(data):
        header = struct.unpack_from('<H', data, offset)[0]
        length, wide = header >> 6, header & 1
        if not length:
            return
        size = 2 + length * (2 if wide else 1)
        if offset + size > len(data):
            return
        try:
            text = data[offset+2:offset+size].decode('utf-16le' if wide else 'utf-8')
        except UnicodeError:
            return
        yield offset, text
        offset += (size + 1) & ~1


def scan(reader, max_seconds=90, max_hits=50000, clock=time.monotonic):
    pool = reader.base + 0xdd86ac0
    last = reader.u32(pool + 8)
    if not 0 <= last <= 2048:
        raise ValueError('Unexpected bounded FName block count')
    deadline = clock() + max_seconds
    hits, parsed, errors = [], 0, []
    completed = 0
    for block in range(last+1):
        if clock() >= deadline:
            raise RuntimeError('Read-only discovery batch exceeded its time budget')
        address = reader.u64(pool + 0x10 + block * 8)
        try:
            data = reader.read(address, 65536)
            for offset, value in parse_block(data):
                parsed += 1
                if not value.startswith(PREFIX) or not PACKAGE.fullmatch(value):
                    continue
                if len(hits) >= max_hits:
                    raise RuntimeError('Resource hit bound reached; do not publish a truncated catalog')
                comparison = (block << 16) | (offset // 2)
                if reader.name(comparison) != value:
                    raise RuntimeError('FName crosscheck failed; metadata changed during batch')
                hits.append({'name': value, 'comparison_index': comparison,
                             'runtime_identity_verified': False})
            completed += 1
        except OSError as error:
            errors.append({'block': block, 'type': type(error).__name__})
            if len(errors) >= 8:
                raise RuntimeError('Too many unreadable name blocks; stop the batch') from error
    return {'fname_blocks': last+1, 'completed_blocks': completed, 'fname_entries_parsed': parsed,
            'resource_name_clues': hits, 'errors': errors, 'complete': not errors}


def collect():
    # Imports stay inside the live entry point: pure parser/tests work without a game or Win32.
    import official_validation as v
    from pbz_readonly import GameRead
    from pathlib import Path
    from boss_adaptation_workflow import BUILD
    with GameRead() as reader:
        start = time.monotonic()
        report = scan(reader)
        report.update(at=datetime.now().astimezone().isoformat(), pid=reader.pid,
            target_build_sha256=BUILD, elapsed_seconds=time.monotonic()-start,
            scope='Read-only bounded FName paths; no function calls, asset loading, map navigation or input.',
            boss_identity_verified=False, boss_control_verified=False)
        target = Path(reader.state['work'])/'boss-resource-names.json'
        v.save(target, report)
        if report['complete']:
            v.save(v.ROOT/'evidence/adaptation/boss-resource-names.json', report)
        return {'report': str(target), 'names': len(report['resource_name_clues']),
                'complete': report['complete'], 'seconds': report['elapsed_seconds'], 'game_calls': 0}


if __name__ == '__main__':
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
