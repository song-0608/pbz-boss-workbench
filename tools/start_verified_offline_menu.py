"""用途：当前云关闭截图复核后启动原版离线菜单；保留看门狗，供设置写入核对。"""
import json
from pathlib import Path
import shutil
import sys
import official_validation as v
import research_window_input as ui


def main():
    if sys.argv[1:]!=['--cloud-off-reviewed']:raise RuntimeError('Current properties screenshot review required')
    state=json.loads(v.state_path().read_text(encoding='utf-8'));work=Path(state['work'])
    if not state.get('offline_validation') or not state.get('compatibility_probe_passed'):raise RuntimeError('Offline preparation not verified')
    proof=json.loads((work/'actual-save-path-proof.json').read_text(encoding='utf-8'))
    if not proof.get('passed'):raise RuntimeError('Actual save paths not verified')
    shutil.copy2(v.ROOT/'runtime/steam-menu-private.png',work/'cloud-off-reviewed.png')
    v.save(work/'cloud-gate.json',{'at':v.utc8(),'ui_off_verified':True,'screenshot':'cloud-off-reviewed.png'})
    ui.click('影之刃零',1238,24,1263,902)
    v.save(work/'test-purpose.json',{'purpose':'Second offline cold start and actual settings write isolation',
        'gameplay_allowed':False,'new_game_allowed':False,'save_load_allowed':False})
    v.launch(offline=True)


if __name__=='__main__':main()
