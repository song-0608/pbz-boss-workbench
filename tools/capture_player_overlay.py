"""仅截取已聚焦研究游戏的客户区，验证配套状态层实际可见。"""
import ctypes
from ctypes import wintypes as w
from pathlib import Path
import re
import sys
import time
from PIL import ImageGrab
import ahua_practice as practice
import official_validation as v
import research_game_menu as menu


def capture(label):
    if not re.fullmatch('[a-z0-9-]{1,64}',label):raise ValueError('Bounded evidence label required')
    owner,state=practice.owned_session()
    if owner.get('phase')!='armed':raise RuntimeError('Current armed session required')
    menu.click(0,0,2560,1600,'control_focus')
    time.sleep(.6)
    user=ctypes.WinDLL('user32',use_last_error=True);user.SetProcessDPIAware()
    user.GetForegroundWindow.restype=w.HWND
    user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
    user.GetClientRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)]
    user.ClientToScreen.argtypes=[w.HWND,ctypes.POINTER(w.POINT)]
    handle=user.GetForegroundWindow();pid=w.DWORD();user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    if pid.value not in {p['ProcessId']for p in c.box_processes(dll)if p['Name'].lower()=='pbz.exe'}:
        raise RuntimeError('Research game no longer foreground; no desktop capture')
    rect=w.RECT();user.GetClientRect(handle,ctypes.byref(rect))
    if not 320<=rect.right<=7680 or not 200<=rect.bottom<=4320:raise RuntimeError('Bounded client area required')
    origin=w.POINT(0,0);user.ClientToScreen(handle,ctypes.byref(origin))
    if user.GetForegroundWindow()!=handle:raise RuntimeError('Research foreground changed before capture')
    picture=ImageGrab.grab(bbox=(origin.x,origin.y,origin.x+rect.right,origin.y+rect.bottom),all_screens=True)
    target=Path(state['work'])/(label+'.png');picture.save(target)
    preview=target.with_name(label+'-preview.png');picture.resize((1280,round(picture.height*1280/picture.width))).save(preview)
    result={'at':v.utc8(),'game_pid':pid.value,'file':str(target),'preview':str(preview),'only_game_client_captured':True}
    v.save(target.with_suffix('.json'),result);return result


if __name__=='__main__':
    import json
    print(json.dumps(capture(sys.argv[1]),ensure_ascii=False))
