"""用途：只查看研究用Steam菜单，判断是否真正切到离线；拒绝登录窗，不采集账号和密码。"""
import ctypes
from ctypes import wintypes as w
import json
import sys
import time
from pathlib import Path
from PIL import Image
import test_offline_client as client
from show_research_steam import show

ROOT = Path(__file__).resolve().parent.parent


def capture_menu(path, click_menu=False, focus=True, attempt=0):
    client.isolation.select_box('PBZSteamLab'); dll=client.isolation.api()
    client.isolation.check_policy(dll, allow_eula_web='--eula-preparation' in sys.argv,
                                  allow_official_validation='--official-validation-review' in sys.argv,
                                  allow_auth_preparation='--authentication-preparation' in sys.argv,
                                  allow_official_client_preparation='--official-client-preparation' in sys.argv,
                                  allow_offline_validation='--offline-validation-review' in sys.argv)
    if client.host_steam_pids(dll):raise RuntimeError('Host Steam appeared; preserve it')
    if focus:
        shown=show(10)
        if not shown.get('found_research_window') or shown.get('login_window'):
            raise RuntimeError('No research main window; do not capture login contents')
    pids={p['ProcessId'] for p in client.box_processes(dll) if p['Name'].casefold()=='steamwebhelper.exe'}
    u=ctypes.WinDLL('user32',use_last_error=True);g=ctypes.WinDLL('gdi32',use_last_error=True)
    CB=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    u.EnumWindows.argtypes=[CB,w.LPARAM];u.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
    u.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int];u.IsWindowVisible.argtypes=[w.HWND]
    u.GetClientRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)];u.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
    rows=[]
    @CB
    def visit(h,l):
        pid=w.DWORD();u.GetWindowThreadProcessId(h,ctypes.byref(pid))
        if pid.value in pids and u.IsWindowVisible(h):
            title=ctypes.create_unicode_buffer(256);u.GetWindowTextW(h,title,256);r=w.RECT();u.GetClientRect(h,ctypes.byref(r))
            properties='--properties' in sys.argv and ('phantom blade zero' in title.value.casefold() or '影之刃零' in title.value)
            eligible=properties if '--properties' in sys.argv else title.value in ('Steam','Menu','Steam 对话','Steam Dialog')
            if eligible and r.right>=100 and r.bottom>=80:rows.append((h,title.value,r.right,r.bottom))
        return True
    u.EnumWindows(visit,0)
    if not rows:
        if attempt<20:
            time.sleep(.5);return capture_menu(path,click_menu,False,attempt+1)
        raise RuntimeError('No verified requested Steam window; main window cannot substitute for game properties')
    h,title,width,height=min(rows,key=lambda row:-1 if '--properties' in sys.argv and ('phantom blade zero' in row[1].casefold() or '影之刃零' in row[1]) else 0 if row[1] in ('Steam 对话','Steam Dialog') else 1 if row[1]=='Menu' else 2)
    if click_menu:
        if title!='Steam':raise RuntimeError('Menu already open; do not click arbitrary window')
        # 用途：仅向已核实的研究客户端窗口发送左上角Steam菜单点击，不发送键盘或登录输入。
        u.GetForegroundWindow.restype=w.HWND;u.SetForegroundWindow.argtypes=[w.HWND]
        u.AttachThreadInput.argtypes=[w.DWORD,w.DWORD,w.BOOL]
        kernel=ctypes.WinDLL('kernel32');kernel.GetCurrentThreadId.restype=w.DWORD
        foreground=u.GetForegroundWindow();thread=u.GetWindowThreadProcessId(foreground,None) if foreground else 0
        current=kernel.GetCurrentThreadId();attached=False
        try:
            if thread and thread!=current:attached=bool(u.AttachThreadInput(current,thread,True))
            u.SetForegroundWindow(h)
        finally:
            if attached:u.AttachThreadInput(current,thread,False)
        time.sleep(.2)
        actual=w.DWORD();u.GetWindowThreadProcessId(u.GetForegroundWindow(),ctypes.byref(actual))
        if actual.value not in pids:raise RuntimeError('Research window is not foreground; no mouse input sent')
        u.ClientToScreen.argtypes=[w.HWND,ctypes.POINTER(w.POINT)];u.GetCursorPos.argtypes=[ctypes.POINTER(w.POINT)]
        u.SetCursorPos.argtypes=[ctypes.c_int,ctypes.c_int];u.WindowFromPoint.argtypes=[w.POINT];u.WindowFromPoint.restype=w.HWND
        position=w.POINT(75,27);u.ClientToScreen(h,ctypes.byref(position))
        hit=w.DWORD();u.GetWindowThreadProcessId(u.WindowFromPoint(position),ctypes.byref(hit))
        if hit.value not in pids:raise RuntimeError('Menu point belongs to another app; no click')
        old_cursor=w.POINT();u.GetCursorPos(ctypes.byref(old_cursor))
        u.SetCursorPos(position.x,position.y);u.mouse_event(2,0,0,0,0);u.mouse_event(4,0,0,0,0)
        u.SetCursorPos(old_cursor.x,old_cursor.y);time.sleep(.7)
        return capture_menu(path,False,False)
    u.GetDC.argtypes=[w.HWND];u.GetDC.restype=w.HDC;u.ReleaseDC.argtypes=[w.HWND,w.HDC];u.PrintWindow.argtypes=[w.HWND,w.HDC,w.UINT]
    g.CreateCompatibleDC.argtypes=[w.HDC];g.CreateCompatibleDC.restype=w.HDC
    g.CreateCompatibleBitmap.argtypes=[w.HDC,ctypes.c_int,ctypes.c_int];g.CreateCompatibleBitmap.restype=w.HBITMAP
    g.SelectObject.argtypes=[w.HDC,w.HGDIOBJ];g.SelectObject.restype=w.HGDIOBJ
    g.DeleteObject.argtypes=[w.HGDIOBJ];g.DeleteDC.argtypes=[w.HDC]
    dc=u.GetDC(h);m=g.CreateCompatibleDC(dc);bmp=g.CreateCompatibleBitmap(dc,width,height);old=g.SelectObject(m,bmp)
    class Header(ctypes.Structure):
        _fields_=[('size',w.DWORD),('width',w.LONG),('height',w.LONG),('planes',w.WORD),('bits',w.WORD),('compression',w.DWORD),('bytes',w.DWORD),('x',w.LONG),('y',w.LONG),('used',w.DWORD),('important',w.DWORD)]
    class Info(ctypes.Structure):_fields_=[('header',Header),('colors',w.DWORD*3)]
    g.GetDIBits.argtypes=[w.HDC,w.HBITMAP,w.UINT,w.UINT,w.LPVOID,ctypes.POINTER(Info),w.UINT]
    try:
        if not u.PrintWindow(h,m,3):raise RuntimeError('Menu capture failed')
        info=Info();info.header=Header(ctypes.sizeof(Header),width,-height,1,32,0,0,0,0,0,0)
        buf=ctypes.create_string_buffer(width*height*4)
        if g.GetDIBits(m,bmp,0,height,buf,ctypes.byref(info),0)!=height:raise RuntimeError('Menu pixels unavailable')
        pic=Image.frombytes('RGB',(width,height),buf.raw,'raw','BGRX')
        # 主窗口只保留左上菜单栏，账号区、登录区和游戏列表均不输出。
        if title=='Steam':
            if '--review-dialog' in sys.argv:
                # 只保留中央内容以核对许可提示，去掉顶部账号区和底部个人状态区。
                pic=pic.crop((0,min(90,height),width,max(90,height-50)))
            else:
                pic=pic.crop((0,0,min(380,width),min(480,height)))
        pic.save(path)
    finally:
        g.SelectObject(m,old);g.DeleteObject(bmp);g.DeleteDC(m);u.ReleaseDC(h,dc)
    return {'window':title,'file':str(path),'only_menu_captured':True}


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    target=ROOT/'runtime/steam-menu-private.png'
    print(json.dumps(capture_menu(target,'--open-menu' in sys.argv),ensure_ascii=False,indent=2))
