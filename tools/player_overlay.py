"""研究游戏专属只读状态层：不夺焦点、不接收鼠标、不发送输入、不读取游戏内存。"""
import argparse
import ctypes
from ctypes import wintypes as w
import json
from pathlib import Path
import re
import time
import tkinter as tk
import ahua_practice as practice
from player_status_stream import StatusStream,valid_status


def latest_status(data, session, now):
    rows=re.findall(r'PBZ_PLAYER_UI:STATUS=(\{[^\r\n]+\})',data)
    if not rows:
        return None
    try:
        value=json.loads(rows[-1])
        if not valid_status(value,session,now):
            return None
        return value
    except (ValueError,KeyError,TypeError):
        return None


def overlay_layout(text,client_width):
    """工作台使用更大字号；普通状态层保留紧凑显示。"""
    menu=text.startswith('Boss 工作台  |  Insert 开关')
    return {'menu':menu,'font_size':(18 if client_width>=1600 else 14) if menu else 11,
            'wraplength':min(1040,max(240,client_width-96)) if menu else min(760,max(240,client_width-60)),
            'padx':24 if menu else 12,'pady':18 if menu else 8}


def main(smoke=False):
    root=tk.Tk();root.withdraw();root.overrideredirect(True)
    root.configure(background='#142027');root.attributes('-topmost',True);root.attributes('-alpha',0.92)
    label=tk.Label(root,text='',justify='left',anchor='nw',fg='#C7F9D4',bg='#142027',
                   font=('Microsoft YaHei UI',11),padx=12,pady=8)
    label.pack()
    if smoke:
        root.update_idletasks();root.destroy();print('read-only overlay widget smoke passed');return
    import official_validation as v
    owner,state=practice.owned_session()
    if owner.get('phase')!='armed':raise RuntimeError('Current armed player assembly required')
    expected=owner['state_file'];offset=owner['log_offset'];session=Path(expected).parent.name
    path=practice.log_path(state)
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    c.isolation.check_policy(dll,allow_offline_validation=True)
    user=ctypes.WinDLL('user32',use_last_error=True);user.SetProcessDPIAware()
    user.GetForegroundWindow.restype=w.HWND
    user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
    user.GetClassNameW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
    user.GetClientRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)]
    user.ClientToScreen.argtypes=[w.HWND,ctypes.POINTER(w.POINT)]
    user.GetAncestor.argtypes=[w.HWND,w.UINT];user.GetAncestor.restype=w.HWND
    user.GetWindowLongPtrW.argtypes=[w.HWND,ctypes.c_int];user.GetWindowLongPtrW.restype=ctypes.c_ssize_t
    user.SetWindowLongPtrW.argtypes=[w.HWND,ctypes.c_int,ctypes.c_ssize_t]
    user.SetWindowLongPtrW.restype=ctypes.c_ssize_t
    user.SetWindowPos.argtypes=[w.HWND,w.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.UINT]
    root.update_idletasks();handle=user.GetAncestor(root.winfo_id(),2)
    style=user.GetWindowLongPtrW(handle,-20)|0x08000000|0x20|0x80|0x80000
    user.SetWindowLongPtrW(handle,-20,style)
    if user.GetWindowLongPtrW(handle,-20)&(0x08000000|0x20|0x80000)!=(0x08000000|0x20|0x80000):
        raise RuntimeError('Nonactivating click-through window styles did not verify')
    pids=set();last_pid_check=0;shown=False
    status_stream=StatusStream(path,session,tail_existing=False)
    last_text,last_geometry=None,None
    visible=False

    def tick():
        nonlocal pids,last_pid_check,shown,last_text,last_geometry,visible
        try:
            now=time.time();current=practice.read(practice.OWNER)
            if (current.get('phase')!='armed' or current.get('state_file')!=expected
                    or current.get('log_offset')!=offset or now>=state['deadline_unix']
                    or practice.read(Path(expected)).get('restored')):
                root.destroy();return
            if now-last_pid_check>3:
                pids={p['ProcessId']for p in c.box_processes(dll)if p['Name'].lower()=='pbz.exe'}
                last_pid_check=now
            status=status_stream.read(now)
            front=user.GetForegroundWindow();pid=w.DWORD();user.GetWindowThreadProcessId(front,ctypes.byref(pid))
            cls=ctypes.create_unicode_buffer(256);user.GetClassNameW(front,cls,256)
            if pid.value not in pids or not cls.value.endswith(':UnrealWindow') or not status:
                if visible:root.withdraw();visible=False
            else:
                rect=w.RECT();user.GetClientRect(front,ctypes.byref(rect))
                layout=overlay_layout(status['text'],rect.right)
                point=w.POINT(0,0);user.ClientToScreen(front,ctypes.byref(point))
                content=(status['text'],tuple(layout.items()))
                if content!=last_text:
                    label.configure(text=content[0],wraplength=layout['wraplength'],
                        font=('Microsoft YaHei UI',layout['font_size']),padx=layout['padx'],pady=layout['pady'])
                    root.update_idletasks();last_text=content
                if not visible:root.deiconify();visible=True
                panel_width,panel_height=root.winfo_reqwidth(),root.winfo_reqheight()
                x=point.x+max(12,(rect.right-panel_width)//2) if layout['menu'] else point.x+24
                y=point.y+max(12,(rect.bottom-panel_height)//3) if layout['menu'] else point.y+24
                geometry=(x,y,panel_width,panel_height)
                if geometry!=last_geometry:
                    user.SetWindowPos(handle,w.HWND(-1),*geometry,0x10|0x40);last_geometry=geometry
                if user.GetForegroundWindow()!=front:
                    root.withdraw();raise RuntimeError('Status layer changed foreground unexpectedly')
                if not shown:
                    v.save(Path(state['work'])/'player-overlay-visible.json',{'at':v.utc8(),
                        'game_pid':pid.value,'nonactivating':True,'click_through':True,
                        'session':session,'status_source':'live Lua readback','engine_canvas_hook':False})
                    shown=True
            root.after(250,tick)
        except Exception as error:
            v.save(Path(state['work'])/'player-overlay-error.json',{'at':v.utc8(),'error':str(error)})
            root.destroy()
    root.after(50,tick);root.mainloop()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--smoke',action='store_true')
    main(parser.parse_args().smoke)
