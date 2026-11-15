"""用途：仅向当前离线研究窗口发送固定操控测试序列，保留真实输入时间；不重启游戏。"""
import json
from pathlib import Path
import time
import official_validation as v
import research_game_menu as menu


def main():
    s=json.loads(v.state_path().read_text(encoding='utf-8'));work=Path(s['work'])
    p=next(Path(x['physical_path']).parent/'UE4SS.log'for x in s['ue4ss_loader_manifest']if x['physical_path'].endswith('UE4SS.dll'))
    until=time.monotonic()+25
    while time.monotonic()<until:
        log=p.read_text(encoding='utf-8',errors='replace');segment=log[log.rfind('Re-installing all mods'):]
        if 'INTERACTIVE_READY='in segment:break
        if 'ISSUE_'in segment and 'END='in segment:raise RuntimeError(segment[-1800:])
        time.sleep(.3)
    else:raise RuntimeError('Interactive init not ready')
    events=[]
    for action,delay in [('control_enter',1),('control_forward',0),('control_look',0),('control_attack',1),
        ('control_skill',7),('control_skill2',7),('control_skill3',7),('control_skill4',2),('control_exit',0)]:
        result=menu.click(0,0,2560,1600,action)
        events.append({'at':v.utc8(),'action':action,'result':result})
        v.save(work/'interactive-input-events.json',events);print(result,flush=True);time.sleep(delay)


if __name__=='__main__':main()
