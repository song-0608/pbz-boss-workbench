"""用途：当前云关闭画面复核后启动一轮定向离线战斗研究；不运行地图观测器。"""
import json
from pathlib import Path
import shutil
import sys
import official_validation as v
import research_window_input as ui
from pbz_ue4ss_baseline import deploy_and_launch


def main():
    if sys.argv[1:]!=['--cloud-off-reviewed']:raise RuntimeError('Review current cloud/overlay OFF screenshot first')
    state=json.loads(v.state_path().read_text(encoding='utf-8'));work=Path(state['work'])
    shutil.copy2(v.ROOT/'runtime/steam-menu-private.png',work/'cloud-off-reviewed.png')
    v.save(work/'cloud-gate.json',{'at':v.utc8(),'ui_off_verified':True,'screenshot':'cloud-off-reviewed.png'})
    ui.click('影之刃零',1238,24,1263,902)
    state.update({'test_purpose':'Faction and target contracts, player-aligned temporary Ahua, owned camera cleanup; no map exploration',
        'restart_reason':'Previous bounded session ended; one new process for new combat identity and lifecycle integration',
        'save_isolation_acceptance_repeated':False})
    v.save(v.state_path(),state)
    carrier=v.ROOT/'adaptation/pbz-26367565/Mods/PBZObserveAI/Scripts/main.lua'
    original=carrier.read_bytes();(work/'observer-source-before-combat.lua').write_bytes(original)
    try:
        carrier.write_bytes(b'print("PBZ_COMBAT_CONTRACT:READY=offline declaration probe only; no actor loops\\n")\n')
        deploy_and_launch(with_signature=True,readonly_ai=True,readonly_hot_reload=True)
    finally:carrier.write_bytes(original)


if __name__=='__main__':main()
