"""用途：一次合并验证F6、镜头画面、W、F1和出招后F10；仅使用既有研究输入闸门。"""
import json
from pathlib import Path
import time
import sys
import official_validation as v
import research_game_menu as menu
import capture_research_game as capture
import run_control_lifecycle_probe as deploy


def main():
    state=json.loads(v.state_path().read_text(encoding='utf-8'))
    log_path=next(Path(r['physical_path']).parent/'UE4SS.log' for r in state['ue4ss_loader_manifest'] if r['physical_path'].endswith('UE4SS.dll'))
    start=log_path.stat().st_size
    deploy.main()
    deadline=time.monotonic()+23
    while time.monotonic()<deadline:
        with log_path.open('rb')as handle:
            handle.seek(start);tail=handle.read().decode('utf-8',errors='replace')
        if 'PBZ_CONTROL_LIFECYCLE:ISSUE_' in tail:
            raise RuntimeError(tail[-3000:])
        if 'PBZ_CONTROL_LIFECYCLE:INTERACTIVE_READY=' in tail:break
        time.sleep(.2)
    else:raise RuntimeError('No current bounded interactive ready; no keys sent')
    events=[]
    def key(purpose):events.append({'at':v.utc8(),**menu.click(0,0,2560,1600,purpose)})
    try:
        key('control_enter')
        time.sleep(.9)
        look_only='--look-only' in sys.argv
        if look_only:
            key('control_look')
            key('control_forward')
            time.sleep(.7)
            events.append(capture.capture('camera-after-look-move'))
        else:
            events.append(capture.capture('camera-active'))
            key('control_forward')
            key('control_skill')
            time.sleep(.1)
        key('control_exit')
        time.sleep(.7)
        events.append(capture.capture('camera-after-look-exit' if look_only else 'camera-after-exit'))
    finally:
        v.save(Path(state['work'])/('camera-look-inputs.json' if '--look-only' in sys.argv else 'camera-control-inputs.json'),events)
    with log_path.open('rb')as handle:
        handle.seek(start);tail=handle.read().decode('utf-8',errors='replace')
    (Path(state['work'])/('camera-look-batch.log' if look_only else 'camera-control-batch.log')).write_text(tail,encoding='utf-8')
    print(tail[-12000:])


if __name__=='__main__':main()
