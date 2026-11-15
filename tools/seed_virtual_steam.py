"""用途：为Steam准备纯英文的箱内安装路径，实际文件仍全部保存在D盘研究容器。"""
from pathlib import Path
import os
import shutil
import hashlib
import json
import sys
from datetime import datetime, timezone, timedelta
import test_isolation as isolation
import run_sandbox_baseline as baseline

ROOT = Path(__file__).resolve().parent.parent


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    isolation.select_box('PBZSteamLab')
    dll = isolation.api()
    isolation.check_policy(dll)
    if baseline.box_pids(dll):
        raise RuntimeError('Box occupied')
    source = ROOT / 'runtime/SteamOffline'
    alias = Path(r'E:\PBZSteamLabClient')
    container = isolation.get_root(dll)
    target = isolation.virtual_file(container, alias)
    if not source.is_dir() or target.exists():
        raise RuntimeError('Inspect source or existing virtual client before copying')
    if not alias.is_junction() or alias.resolve() != source.resolve():
        raise RuntimeError('Expected project-owned junction not found; refuse directory change')
    # 用途：先在D盘虚拟镜像内完整复制并验哈希，再替换我们自己的入口联接，绝不移动正式Steam。
    rows = []
    for base, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = [name for name in dirs if name != 'private-local-cache' and not (Path(base) / name).is_junction() and not (Path(base) / name).is_symlink()]
        for name in files:
            original = Path(base) / name
            if original.is_symlink():
                continue
            destination = target / original.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, destination)
            with original.open('rb') as f:
                first = hashlib.file_digest(f, 'sha256').hexdigest()
            with destination.open('rb') as f:
                second = hashlib.file_digest(f, 'sha256').hexdigest()
            if first != second:
                raise RuntimeError('Virtual client copy mismatch')
            rows.append({'name': str(original.relative_to(source)), 'bytes': original.stat().st_size, 'sha256': first})
    # os.rmdir只删除已核实的目录联接本身；被联接的D盘资料保留。
    os.rmdir(alias)
    alias.mkdir()
    report = {'time': datetime.now(timezone(timedelta(hours=8))).isoformat(), 'logical_install': str(alias),
              'physical_install': str(target), 'host_entry_is_empty_directory': not any(alias.iterdir()),
              'host_formal_steam_modified': False, 'source_copy_preserved': source.is_dir(),
              'file_count': len(rows), 'bytes': sum(row['bytes'] for row in rows), 'files': rows,
              'private_runtime_not_for_sharing': True}
    (ROOT / 'evidence/offline-steam/virtual-client-copy.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'files'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
