"""用途：在现有隔离离线进程一次查询阵营/镜头枚举，登记文件哈希后热重载。"""
import hashlib
import json
from pathlib import Path
import time
import official_validation as v
import research_game_menu as menu

def main():
    s=json.loads(v.state_path().read_text(encoding='utf-8'))
    if s.get('restored')or s.get('network_active')or not s.get('readonly_ai_experiment')or time.time()>s['deadline_unix']-120:
        raise RuntimeError('Active read-only offline session required')
    v.verify_build(s['ue4ss_loader_manifest'])
    row=next(r for r in s['ue4ss_loader_manifest']if r['physical_path'].replace('\\','/').endswith('/PBZObserveAI/Scripts/main.lua'))
    target=Path(row['physical_path']);work=Path(s['work'])
    data=b'\n'.join((v.ROOT/'mod/PBZBossControl/Experiments'/name).read_bytes()for name in ('camera_contract.lua','combat_contract.lua'))
    (work/'readonly-combat-before.lua').write_bytes(target.read_bytes())
    row['sha256']=hashlib.sha256(data).hexdigest()
    v.save(v.state_path(),s)
    target.write_bytes(data)
    v.verify_build(s['ue4ss_loader_manifest'])
    print(menu.click(0,0,2560,1600,'observe_reload'))

if __name__=='__main__':main()
