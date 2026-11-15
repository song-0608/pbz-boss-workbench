"""用途：在尚未装配Boss的研究进程诊断自建镜头销毁，不启动额外游戏。"""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import ahua_practice as practice
import inspect_camera_contract
import official_validation as v
import research_game_menu as menu

def main():
    owner,state=practice.owned_session()
    if owner['phase']!='game_launched' or state.get('boss_lifecycle_experiment'):
        raise RuntimeError('Idle carrier required; preserve active controls')
    v.verify_build(state['ue4ss_loader_manifest'])
    with contextlib.redirect_stdout(io.StringIO()):passed=inspect_camera_contract.collect()==0
    contract=json.loads((Path(state['work'])/'camera-native-contract.json').read_text(encoding='utf-8'))
    declaration=next(f for f in contract['functions'] if f['path']=='/Script/Engine.KismetSystemLibrary.IsValid')
    if not passed or declaration['parameter_bytes']!=9 or [p['name']for p in declaration['parameters']]!=['Object','ReturnValue']:
        raise RuntimeError('Engine validity query contract not verified')
    source=v.ROOT/'mod/PBZBossControl/Experiments/camera_cleanup_probe.lua'
    deadline=min(int(time.time())+60,int(state['deadline_unix'])-30)
    if deadline<time.time()+30:raise RuntimeError('Insufficient diagnostic margin')
    data=('local camera_probe_deadline='+str(deadline)+'\n').encode()+source.read_bytes()
    row=next(r for r in state['ue4ss_loader_manifest'] if r['physical_path'].replace('\\','/').endswith('/PBZObserveAI/Scripts/main.lua'))
    carrier=Path(row['physical_path']);row['sha256']=hashlib.sha256(data).hexdigest()
    v.save(v.state_path(),state);carrier.write_bytes(data)
    work=Path(state['work']);(work/'camera-cleanup-probe.lua').write_bytes(data)
    menu.click(0,0,2560,1600,'observe_reload')
    print(json.dumps({'probe_deployed':True,'deadline':deadline,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()},ensure_ascii=False))

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
