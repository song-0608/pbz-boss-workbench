"""用途：复制本机Steam客户端及本机已有离线缓存到研究目录，不修改源客户端、不上传缓存。"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(r"D:\steam")
DEST = ROOT / "runtime/SteamOffline"


def copy_verified(source, target):
    """用途：复制后校验字节相同；报告只存文件名和哈希，绝不打印配置或登录缓存内容。"""
    before = source.stat()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    with source.open('rb') as f: original_hash = hashlib.file_digest(f,'sha256').hexdigest()
    with target.open('rb') as f: copied_hash = hashlib.file_digest(f,'sha256').hexdigest()
    after = source.stat()
    if original_hash != copied_hash or before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise RuntimeError('Source changed or copy mismatch; no launch: '+source.name)
    return {'relative_file': str(target.relative_to(DEST)), 'bytes': after.st_size, 'sha256': copied_hash}


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if 'windowsapps' in sys.executable.casefold():
        raise RuntimeError('Use non-Store Python for correct AppData paths')
    if DEST.exists():
        raise RuntimeError('Offline client already exists; inspect it instead of overwriting')
    DEST.mkdir(parents=True)
    files=[]
    # 用途：复制已安装的客户端组件，不复制任何其他游戏或用户进度。
    for path in SOURCE.iterdir():
        if path.is_file() and path.suffix.casefold() in ('.exe','.dll','.json','.signatures'):
            files.append((path, DEST/path.name))
    for name in ('bin','clientui','public','resource','steamui','tenfoot','package','config'):
        base=SOURCE/name
        if not base.is_dir():continue
        for directory, dirs, names in os.walk(base,followlinks=False):
            dirs[:]=[name for name in dirs if not (Path(directory)/name).is_symlink() and not (Path(directory)/name).is_junction()]
            for name in names:
                path=Path(directory)/name
                if path.is_file() and not path.is_symlink():files.append((path,DEST/path.relative_to(SOURCE)))
    # 用途：离线授权仍交给官方客户端验证；不解密、不生成、不伪造登录凭据。
    # 该文件只作为私有本机缓存保存，不能放入对外分享的项目包。
    local_cache=Path(os.environ['LOCALAPPDATA'])/'Steam/local.vdf'
    if local_cache.is_file():files.append((local_cache,DEST/'private-local-cache/local.vdf'))
    rows=[]
    for index,(source,target) in enumerate(files):
        rows.append(copy_verified(source,target))
        if index and index%300==0:print('Copied and verified client files:',index,flush=True)
    report={'time':datetime.now(timezone(timedelta(hours=8))).isoformat(),'client_source':str(SOURCE),'client_copy':str(DEST),
            'file_count':len(rows),'bytes':sum(row['bytes'] for row in rows),'source_files_modified':False,
            'source_userdata_copied':False,'existing_offline_config_copied':True,'no_credentials_decrypted':True,
            'private_local_cache_present':local_cache.is_file(),'files':rows}
    (ROOT/'evidence/offline-steam-copy.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (DEST/'本机缓存请勿分享.txt').write_text('本目录包括本机Steam配置和加密离线登录缓存。只供本人本机离线实验，不放入简历或分享包，不上传。源Steam未修改。\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='files'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
