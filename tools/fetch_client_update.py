"""用途：只从Valve官方HTTPS更新站下载公开客户端更新包，不连接账号、不启动游戏。"""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent.parent
ORIGIN = 'https://client-update.steamstatic.com/'
CACHE = ROOT / 'dependencies/SteamClientOfficialUpdate'


def keyvalues(text):
    """用途：读取官方客户端文本清单的键、值和嵌套块；不执行清单内容。"""
    tokens = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"|([{}])', text)
    tokens = [value if symbol == '' else symbol for value, symbol in tokens]
    pos = 0

    def block(nested=False):
        nonlocal pos
        result = {}
        while pos < len(tokens):
            key = tokens[pos]; pos += 1
            if key == '}':
                if not nested:
                    raise ValueError('Unexpected closing brace')
                return result
            if pos >= len(tokens):
                raise ValueError('Missing manifest value')
            value = tokens[pos]; pos += 1
            result[key] = block(True) if value == '{' else value
        if nested:
            raise ValueError('Unclosed manifest block')
        return result
    return block()


def get(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'PBZ-local-client-preparation/1.0'})
    return urllib.request.urlopen(request, timeout=35)


def fetch(package):
    name, expected, size = package['file'], package['sha2'], int(package['size'])
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or not re.fullmatch(r'[a-fA-F0-9]{64}', expected):
        raise ValueError('Unsafe package metadata')
    path = CACHE / name
    if path.is_file():
        with path.open('rb') as f:
            if path.stat().st_size == size and hashlib.file_digest(f, 'sha256').hexdigest() == expected.lower():
                return {'name': name, 'bytes': size, 'sha256': expected.lower(), 'cache_verified': True}
    temporary = path.with_name(path.name + '.partial')
    received = 0
    checksum = hashlib.sha256()
    with get(ORIGIN + name) as response, temporary.open('wb') as output:
        # 用途：拒绝重定向到未确认的第三方来源；不发送任何Steam配置、Cookie或登录资料。
        if not response.url.startswith(ORIGIN):
            raise ValueError('Unexpected download origin')
        while chunk := response.read(1024 * 1024):
            received += len(chunk)
            if received > size:
                raise ValueError('Package exceeds advertised size')
            output.write(chunk); checksum.update(chunk)
    if received != size or checksum.hexdigest() != expected.lower():
        raise ValueError('Official package checksum mismatch: ' + name)
    temporary.replace(path)
    return {'name': name, 'bytes': received, 'sha256': checksum.hexdigest(), 'cache_verified': False}


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    CACHE.mkdir(parents=True, exist_ok=True)
    with get(ORIGIN + 'steam_client_win64') as response:
        manifest = response.read(1024 * 1024)
    (CACHE / 'steam_client_win64').write_bytes(manifest)
    parsed = keyvalues(manifest.decode('utf-8-sig'))
    entries = parsed.get('win64')
    if not isinstance(entries, dict):
        raise ValueError('Unexpected manifest platform')
    packages = [value for value in entries.values() if isinstance(value, dict) and all(k in value for k in ('file', 'sha2', 'size'))]
    wanted = next((arg.split('=', 1)[1] for arg in sys.argv[1:] if arg.startswith('--package=')), None)
    if wanted is not None:
        package = entries.get(wanted)
        if package not in packages:
            raise ValueError('Unknown official package')
        packages = [package]
    report = {'time': datetime.now(timezone(timedelta(hours=8))).isoformat(), 'origin': ORIGIN,
              'manifest_sha256': hashlib.sha256(manifest).hexdigest(), 'version': entries.get('version'),
              'package_count': len(packages), 'package_bytes': sum(int(p['size']) for p in packages),
              'game_launched': False, 'steam_client_launched': False, 'account_credentials_sent': False, 'packages': []}
    if '--inspect' not in sys.argv[1:]:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(fetch, package) for package in packages]
            for future in concurrent.futures.as_completed(futures):
                result = future.result(); report['packages'].append(result)
                print('Verified official update package: ' + result['name'], flush=True)
        (ROOT / 'evidence/offline-steam/official-client-update-download.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'packages'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
