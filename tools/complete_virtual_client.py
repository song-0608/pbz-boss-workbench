"""用途：按本机Steam已安装客户端清单补齐复制遗漏，避免把缺客户端文件误判为需要联网授权。"""
from pathlib import Path, PureWindowsPath
import hashlib
import shutil
import json
import sys
from datetime import datetime, timezone, timedelta
import test_isolation as isolation
import run_sandbox_baseline as baseline

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(r'D:\steam')


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    dry = '--inspect' in sys.argv[1:]
    isolation.select_box('PBZSteamLab')
    dll = isolation.api()
    isolation.check_policy(dll)
    if not dry and baseline.box_pids(dll):
        raise RuntimeError('Box occupied; cannot change a running client')
    target = isolation.virtual_file(isolation.get_root(dll), Path(r'E:\PBZSteamLabClient'))
    manifest = SOURCE / 'package/steam_client_win64.installed'
    jobs = []
    absent_source = []
    count = 0
    for line in manifest.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():
            continue
        if line.startswith(('OSVER=', 'VERSION=', 'SHA1=')):
            continue
        name, metadata = line.rsplit(',', 1)
        size = int(metadata.split(';')[0])
        relative = PureWindowsPath(name)
        if relative.is_absolute() or relative.drive or '..' in relative.parts or relative.parts[0].casefold() in ('userdata', 'steamapps', 'config', 'logs', 'dumps', 'private-local-cache'):
            raise RuntimeError('Unexpected client manifest path; no copying: ' + name)
        if size < 0:
            continue
        count += 1
        original, destination = SOURCE / relative, target / relative
        if not original.is_file() or original.stat().st_size != size:
            absent_source.append(name)
            continue
        if not destination.is_file() or destination.stat().st_size != size:
            jobs.append((original, destination))
    report = {'time': datetime.now(timezone(timedelta(hours=8))).isoformat(), 'installed_manifest_files': count,
              'copy_jobs': len(jobs), 'copy_bytes': sum(s.stat().st_size for s, d in jobs),
              'host_client_missing_or_wrong_size': absent_source, 'inspect_only': dry, 'files': [],
              'host_client_modified': False, 'game_or_userdata_copied': False}
    if absent_source:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise RuntimeError('Host installed manifest does not match source; no writes')
    if not dry:
        for original, destination in jobs:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, destination)
            with original.open('rb') as f:
                first = hashlib.file_digest(f, 'sha256').hexdigest()
            with destination.open('rb') as f:
                second = hashlib.file_digest(f, 'sha256').hexdigest()
            if first != second:
                raise RuntimeError('Client component copy verification failed')
            report['files'].append({'name': str(original.relative_to(SOURCE)), 'bytes': original.stat().st_size, 'sha256': first})
        # 用途：复制合法更新源文件，不修改安装器的认证/校验逻辑或禁用更新器。
        cache = SOURCE / 'update_hosts_cached.vdf'
        if cache.is_file():
            shutil.copy2(cache, target / cache.name)
        (ROOT / 'evidence/offline-steam/complete-client-copy.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'files'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
