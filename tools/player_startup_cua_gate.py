"""Read-only CUA authorization for the unarmed, isolated saved-scene startup.

Never injects input. Use one fresh receipt per observed native menu action.
"""
import argparse
import ctypes
from ctypes import wintypes as w
from pathlib import Path
import time

import ahua_practice as practice
import official_validation as validation
from research_game_menu import validate_startup_positioning


def gate(action):
    key = {'continue': 'Return', 'interact': 'e', 'back': 'Escape'}[action]
    owner, state = practice.owned_session()
    text = practice.log_path(state).read_text(encoding='utf-8', errors='replace')
    validate_startup_positioning(owner, state, text)
    assert state['deadline_unix'] - time.time() > 30
    c = validation.c
    assert c.baseline.formal_files() == state['formal_before']
    validation.verify_build(state['ue4ss_loader_manifest'])
    c.isolation.select_box('PBZSteamLab')
    dll = c.isolation.api()
    c.isolation.check_policy(dll, allow_offline_validation=True)
    assert not c.host_steam_pids(dll)
    pids = {p['ProcessId'] for p in c.box_processes(dll) if p['Name'].lower() == 'pbz.exe'}
    assert pids
    u = ctypes.WinDLL('user32', use_last_error=True)
    u.GetForegroundWindow.restype = w.HWND
    u.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    u.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    u.IsWindowVisible.argtypes = [w.HWND]
    callback = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    u.EnumWindows.argtypes = [callback, w.LPARAM]
    windows = []

    @callback
    def inspect(handle, _):
        pid = w.DWORD()
        u.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        if pid.value in pids and u.IsWindowVisible(handle):
            name = ctypes.create_unicode_buffer(256)
            u.GetClassNameW(handle, name, len(name))
            if name.value == 'Sandbox:PBZSteamLab:UnrealWindow':
                windows.append(int(handle))
        return True

    assert u.EnumWindows(inspect, 0)
    foreground = int(u.GetForegroundWindow() or 0)
    assert len(windows) == 1 and windows[0] == foreground, 'Unique foreground research render window required'
    record = dict(schema=1, action=action, key=key, window_id=foreground,
                  state_file=state['state_file'], gate_expires_at=time.time()+10,
                  input_sent=False, gameplay_verified=False)
    validation.save(Path(state['work'])/('startup-cua-gate-'+str(time.time_ns())+'.json'), record)
    return record


if __name__ == '__main__':
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('continue', 'interact', 'back'))
    print(json.dumps(gate(parser.parse_args().action), ensure_ascii=False))
