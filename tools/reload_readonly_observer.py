"""用途：同一离线研究会话更新唯一只读观察脚本的哈希清单并触发UE4SS热重载。"""
import ctypes
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import official_validation as v
import research_game_menu as menu


def reload():
    s=json.loads(v.state_path().read_text(encoding='utf-8'));work=Path(s['work'])
    if s.get('restored') or time.time()>=s['deadline_unix']-30 or s.get('network_active'):
        raise RuntimeError('Active offline lease with cleanup margin required')
    if not s.get('readonly_ai_experiment') or not s.get('readonly_hot_reload_enabled'):
        raise RuntimeError('Read-only hot reload was not enabled at startup')
    if v.c.baseline.formal_files()!=s['formal_before']:raise RuntimeError('Formal baseline changed')
    v.verify_build(s['ue4ss_loader_manifest'])
    source=v.ROOT/'adaptation/pbz-26367565/Mods/PBZObserveAI/Scripts/main.lua'
    suffix='/ue4ss/Mods/PBZObserveAI/Scripts/main.lua'
    rows=[r for r in s['ue4ss_loader_manifest'] if Path(r['physical_path']).as_posix().endswith(suffix)]
    if len(rows)!=1:raise RuntimeError('Exact observer manifest entry required')
    row=rows[0];target=Path(row['physical_path'])
    from research_storage import container_path
    if not target.is_relative_to(container_path()):raise RuntimeError('Research mirror only')
    old=target.read_bytes();new=source.read_bytes()
    history=work/'readonly-reloads';history.mkdir(exist_ok=True)
    serial=len(list(history.glob('*.json')))+1
    (history/f'{serial:02d}-before.lua').write_bytes(old)
    (history/f'{serial:02d}-after.lua').write_bytes(new)
    # 用途：看门狗不扫描manifest但收尾会检查它；先替换唯一声明文件，再立即原子更新state。
    temporary=target.with_suffix('.lua.pending');temporary.write_bytes(new);temporary.replace(target)
    row['sha256']=hashlib.sha256(new).hexdigest();v.save(v.state_path(),s)
    v.verify_build(s['ue4ss_loader_manifest'])
    v.save(history/f'{serial:02d}.json',{'at':v.utc8(),'before_sha256':hashlib.sha256(old).hexdigest(),
        'after_sha256':row['sha256'],'scope':'Declared read-only observer only; no gameplay control scripts',
        'hot_reload_requested':False})
    # 用途：复用精确研究窗口焦点/离线/正式文件检查，然后仅发送源码已核对的Ctrl+R。
    menu.click(0,0,2560,1600,'observe_reload')
    receipt=history/f'{serial:02d}.json';result=json.loads(receipt.read_text(encoding='utf-8'))
    result['hot_reload_requested']=True;v.save(receipt,result)
    print('Read-only observer updated, manifest verified, Ctrl+R sent to research game only.')

if __name__=='__main__':reload()
