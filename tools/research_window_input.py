"""用途：向已核实的研究箱指定窗口发送一次坐标点击，不接受登录窗或主机窗口。"""
import ctypes
from ctypes import wintypes as w
import time
import test_offline_client as client


def click(title,x,y,width,height):
    client.isolation.select_box('PBZSteamLab');dll=client.isolation.api()
    if client.host_steam_pids(dll):
        raise RuntimeError('Host Steam active; preserve it')
    allowed={p['ProcessId'] for p in client.box_processes(dll)
             if p['Name'].casefold() in ('steam.exe','steamwebhelper.exe')}
    if title not in ('影之刃零','Phantom Blade Zero','Steam','Steam 对话','Steam Dialog','Menu'):
        raise RuntimeError('Unsupported research window')
    user=ctypes.WinDLL('user32',use_last_error=True);user.SetProcessDPIAware()
    cb=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    user.EnumWindows.argtypes=[cb,w.LPARAM]
    user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
    user.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
    user.GetClientRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)]
    user.IsWindowVisible.argtypes=[w.HWND]
    user.GetForegroundWindow.restype=w.HWND
    user.SetForegroundWindow.argtypes=[w.HWND]
    user.ClientToScreen.argtypes=[w.HWND,ctypes.POINTER(w.POINT)]
    user.WindowFromPoint.argtypes=[w.POINT];user.WindowFromPoint.restype=w.HWND
    user.AttachThreadInput.argtypes=[w.DWORD,w.DWORD,w.BOOL]
    kernel=ctypes.WinDLL('kernel32');kernel.GetCurrentThreadId.restype=w.DWORD
    found=[]
    @cb
    def visit(handle,unused):
        pid=w.DWORD();user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
        if pid.value in allowed and user.IsWindowVisible(handle):
            text=ctypes.create_unicode_buffer(256);user.GetWindowTextW(handle,text,256)
            rect=w.RECT();user.GetClientRect(handle,ctypes.byref(rect))
            if text.value==title and rect.right==width and rect.bottom==height:
                found.append(handle)
        return True
    user.EnumWindows(visit,0)
    if len(found)!=1 or not (0<=x<width and 0<=y<height):
        raise RuntimeError('Exact research window/size not confirmed')
    handle=found[0];front=user.GetForegroundWindow()
    thread=user.GetWindowThreadProcessId(front,None) if front else 0
    own=kernel.GetCurrentThreadId();attached=False
    try:
        if thread and thread!=own:attached=bool(user.AttachThreadInput(own,thread,True))
        user.SetForegroundWindow(handle)
    finally:
        if attached:user.AttachThreadInput(own,thread,False)
    time.sleep(.25)
    if user.GetForegroundWindow()!=handle:
        # 用途：Windows可能拒绝后台激活；只恢复已核实的研究窗口后重试，绝不向其他程序点击。
        user.ShowWindow.argtypes=[w.HWND,ctypes.c_int]
        user.ShowWindow(handle,9)
        user.keybd_event(18,0,0,0);user.keybd_event(18,0,2,0)
        user.SetForegroundWindow(handle);time.sleep(.3)
    if user.GetForegroundWindow()!=handle:raise RuntimeError('Target not foreground; no input sent')
    point=w.POINT(x,y);user.ClientToScreen(handle,ctypes.byref(point))
    hit=w.DWORD();user.GetWindowThreadProcessId(user.WindowFromPoint(point),ctypes.byref(hit))
    if hit.value not in allowed:
        raise RuntimeError('Point belongs to another application')
    old=w.POINT();user.GetCursorPos(ctypes.byref(old))
    user.SetCursorPos(point.x,point.y);user.mouse_event(2,0,0,0,0);user.mouse_event(4,0,0,0,0)
    user.SetCursorPos(old.x,old.y)
    return {'research_window':title,'clicked':[x,y],'login_input_sent':False}
