"""用途：只读查找原有资源索引中的明文阿花线索；不解密、不修改包、不启动游戏。"""
import hashlib
import json
import mmap
from pathlib import Path
import re
from datetime import datetime
from pbz_candidate_rules import bride_name_match

ROOT = Path(__file__).resolve().parents[1]
PAKS = Path(r'E:\SteamLibrary\steamapps\common\PBZ\ProjectPBZ\Content\Paks')
EXE = PAKS.parents[2] / 'platform/steam/PBZ.exe'
EXPECTED = '4415933ce33476f14c837abb61a1b60af8b78cd81783896501913a7aac69e423'


def collect():
    with EXE.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest() != EXPECTED:
            raise RuntimeError('Registered game build required')
    reports = []
    for filename in ('ProjectPBZ-Windows.utoc', 'ProjectPBZ-Windows.pak'):
        path = PAKS / filename
        if not 0 < path.stat().st_size <= 512 * 1024 * 1024:
            raise RuntimeError('Unexpected bounded metadata container size')
        matches, count = [], 0
        with path.open('rb') as stream, mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ) as data:
            # 用途：只收集已经明文可见的资源名；没有命中就记为没有线索，不尝试解密。
            for pattern, encoding in ((rb'[\x20-\x7e]{4,768}', 'ascii'),
                                      (rb'(?:[\x20-\x7e]\x00){4,768}', 'utf-16le')):
                for token in re.finditer(pattern, data):
                    value = token[0].decode(encoding)
                    if not bride_name_match(value): continue
                    count += 1
                    if len(matches) < 128:
                        matches.append({'offset':hex(token.start()),'encoding':encoding,'text':value,
                                        'runtime_identity_verified':False})
        reports.append({'file':str(path),'bytes':path.stat().st_size,'plaintext_match_count':count,
                        'matches':matches,'truncated':count>len(matches)})
    result = {'at':datetime.now().astimezone().isoformat(),'exe_sha256':EXPECTED,
              'containers':reports,'boss_identity_verified':False,'boss_control_verified':False,
              'scope':'Read-only existing plaintext container bytes; no decompression, decryption, game process, account or save access'}
    target=ROOT/'evidence/adaptation/bride-disk-clues.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'report':str(target),'counts':{Path(r['file']).name:r['plaintext_match_count'] for r in reports},
            'examples':[m['text'] for r in reports for m in r['matches'][:6]]}


if __name__=='__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(collect(),ensure_ascii=False,indent=2))
