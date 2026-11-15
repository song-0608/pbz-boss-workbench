"""用途：仅向专用沙盒镜像安装已校验的官方客户端文件；不执行包内程序，不碰正式Steam。"""
from pathlib import Path, PureWindowsPath
import hashlib
import json
import shutil
import stat
import sys
import zipfile
from datetime import datetime, timezone, timedelta
import test_isolation as isolation
import run_sandbox_baseline as baseline
from fetch_client_update import CACHE

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    isolation.select_box('PBZSteamLab')
    dll = isolation.api()
    policy = isolation.check_policy(dll)
    if baseline.box_pids(dll):
        raise RuntimeError('Box occupied; refuse to replace running client files')
    if not any(rule.casefold().endswith(r'\steamapps\common\pbz\*') for rule in policy['ClosedFilePath']):
        raise RuntimeError('PBZ preparation-time launch block is missing')
    target = isolation.virtual_file(isolation.get_root(dll), Path(r'E:\PBZSteamLabClient'))
    verified = json.loads((ROOT / 'evidence/offline-steam/official-packages-verified.json').read_text(encoding='utf-8'))
    archives = []
    # 用途：所有压缩包和路径先验证完毕，再开始安装，避免边读未知清单边覆盖文件。
    for row in verified['packages']:
        archive = CACHE / row['file']
        if not archive.is_file() or digest(archive) != row['sha256']:
            raise RuntimeError('Verified archive changed')
        with zipfile.ZipFile(archive) as package:
            for info in package.infolist():
                name = PureWindowsPath(info.filename)
                if name.is_absolute() or name.root or name.drive or '..' in name.parts or stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError('Unsafe archive path')
                if not name.parts:
                    continue
                lower = str(name).casefold()
                if name.parts[0].casefold() in ('userdata', 'steamapps', 'private-local-cache') or lower in (r'config\loginusers.vdf', r'config\config.vdf', r'config\registry.vdf'):
                    raise ValueError('Unexpected account/game-data entry in official client archive')
                if info.file_size > 1024 * 1024 * 1024:
                    raise ValueError('Unexpectedly large client file')
        archives.append((row, archive))
    rows = []
    for row, archive in archives:
        with zipfile.ZipFile(archive) as package:
            for info in package.infolist():
                destination = target / PureWindowsPath(info.filename)
                if info.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_name(destination.name + '.pbz-prepared')
                with package.open(info) as source, temporary.open('wb') as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                if temporary.stat().st_size != info.file_size:
                    raise ValueError('Client extraction length mismatch')
                temporary.replace(destination)
                rows.append({'name': str(destination.relative_to(target)), 'bytes': info.file_size, 'sha256': digest(destination)})
        print('Installed verified official client package: ' + row['name'], flush=True)
    # 用途：使用真实官方清单，不伪造installed标记；最后仍由官方客户端完成启动校验。
    for name in ('steam_client_win64', 'steam_client_win64.manifest'):
        shutil.copy2(CACHE / 'steam_client_win64', target / 'package' / name)
    report = {'time': datetime.now(timezone(timedelta(hours=8))).isoformat(), 'version': verified['version'],
              'file_count': len(rows), 'bytes': sum(row['bytes'] for row in rows), 'files': rows,
              'game_launched': False, 'client_launched': False, 'official_client_validation_pending': True,
              'host_steam_modified': False, 'account_or_drm_validation_bypassed': False,
              'steam_exe_sha256': digest(target / 'steam.exe')}
    (ROOT / 'evidence/offline-steam/official-client-install.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'files'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
