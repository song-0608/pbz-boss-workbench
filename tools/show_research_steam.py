"""用途：只显示PBZSteamLab内的Steam主窗口，恢复到屏幕中央；不截图、不读取登录输入。"""
import ctypes
from ctypes import wintypes as w
import json
import sys
import time
import test_offline_client as client


class RECT(ctypes.Structure):
    _fields_ = [('left', w.LONG), ('top', w.LONG), ('right', w.LONG), ('bottom', w.LONG)]


def show(timeout=30):
    client.isolation.select_box('PBZSteamLab')
    dll = client.isolation.api()
    user = ctypes.WinDLL('user32', use_last_error=True)
    # 用途：使用真实屏幕像素，避免高DPI缩放使窗口截图只截到部分协议。
    user.SetProcessDPIAware()
    callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes = [callback_type, w.LPARAM]
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    user.IsWindowVisible.argtypes = [w.HWND]
    user.IsWindowVisible.restype = w.BOOL
    user.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(RECT)]
    user.ShowWindowAsync.argtypes = [w.HWND, ctypes.c_int]
    user.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.UINT]
    user.SetForegroundWindow.argtypes = [w.HWND]
    user.SetForegroundWindow.restype = w.BOOL
    user.GetForegroundWindow.restype = w.HWND
    user.SystemParametersInfoW.argtypes = [w.UINT, w.UINT, w.LPVOID, w.UINT]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        processes = client.box_processes(dll)
        allowed = {p['ProcessId'] for p in processes if p['Name'].casefold() in ('steam.exe', 'steamwebhelper.exe')}
        windows = []

        @callback_type
        def visit(handle, unused):
            pid = w.DWORD()
            user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
            if pid.value not in allowed:
                return True
            title = ctypes.create_unicode_buffer(512)
            user.GetWindowTextW(handle, title, len(title))
            # 用途：按登录/主窗口名称选择，排除后台IME与空白浏览器服务窗。
            if 'steam' in title.value.casefold() and 'ime' not in title.value.casefold():
                rect = RECT()
                user.GetWindowRect(handle, ctypes.byref(rect))
                if rect.right - rect.left >= 100 and rect.bottom - rect.top >= 100:
                    windows.append((handle, pid.value, '登录' in title.value or 'sign in' in title.value.casefold()))
            return True

        user.EnumWindows(visit, 0)
        if windows:
            handle, pid, login = sorted(windows, key=lambda item: item[2], reverse=True)[0]
            work = RECT()
            if not user.SystemParametersInfoW(0x0030, 0, ctypes.byref(work), 0):
                raise ctypes.WinError(ctypes.get_last_error())
            # 用途：主窗口给协议正文保留足够空间，避免窄窗口裁掉“重试”和本人操作按钮。
            target_width,target_height=(760,640) if login else (1600,1000)
            width, height = min(target_width, work.right - work.left), min(target_height, work.bottom - work.top)
            x, y = work.left + (work.right - work.left - width) // 2, work.top + (work.bottom - work.top - height) // 2
            user.ShowWindowAsync(handle, 9)  # SW_RESTORE：恢复最小化状态。
            positioned = bool(user.SetWindowPos(handle, 0, x, y, width, height, 0x0040))
            foreground_requested = bool(user.SetForegroundWindow(handle))
            time.sleep(.3)
            actual = RECT()
            user.GetWindowRect(handle, ctypes.byref(actual))
            foreground = user.GetForegroundWindow()
            foreground_pid = w.DWORD()
            if foreground:
                user.GetWindowThreadProcessId(foreground, ctypes.byref(foreground_pid))
            return {'found_research_window': True, 'login_window': login, 'pid': pid,
                    'visible': bool(user.IsWindowVisible(handle)), 'positioned': positioned,
                    'window_rectangle': [actual.left, actual.top, actual.right, actual.bottom],
                    'foreground_request_accepted': foreground_requested,
                    'research_window_is_foreground': foreground_pid.value in allowed,
                    'window_contents_or_credentials_read': False}
        time.sleep(1)
    return {'found_research_window': False, 'window_contents_or_credentials_read': False}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print(json.dumps(show(), ensure_ascii=False, indent=2))
