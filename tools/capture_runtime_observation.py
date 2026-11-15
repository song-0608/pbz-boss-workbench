"""用途：只读观察本次专用沙盒里的PBZ模块/线程等待，不读写游戏内存、不挂钩。"""
import ctypes
from ctypes import wintypes as w
from datetime import datetime
import json
import os
from pathlib import Path
import sys

import preflight
import test_isolation as isolation

ROOT = Path(__file__).resolve().parent.parent
TH32CS_SNAPTHREAD = 0x4
TH32CS_SNAPMODULE = 0x8
TH32CS_SNAPMODULE32 = 0x10


class Module(ctypes.Structure):
    _fields_ = [("size", w.DWORD), ("module_id", w.DWORD), ("pid", w.DWORD), ("global_use", w.DWORD),
                ("process_use", w.DWORD), ("base", ctypes.c_void_p), ("bytes", w.DWORD), ("module", w.HMODULE),
                ("name", w.WCHAR*256), ("path", w.WCHAR*260)]


class Thread(ctypes.Structure):
    _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("id", w.DWORD), ("owner", w.DWORD),
                ("base_priority", w.LONG), ("delta_priority", w.LONG), ("flags", w.DWORD)]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # 用途：显式选择研究客户端箱；原默认箱保留，不检查任何主机游戏。
    if '--steam-lab' in sys.argv[1:]:
        isolation.select_box('PBZSteamLab')
    output=None
    if '--output' in sys.argv[1:]:
        index=sys.argv.index('--output')
        output=Path(sys.argv[index+1]).resolve()
        if not output.is_relative_to((ROOT/'evidence/rendered-startup').resolve()):
            raise RuntimeError('Runtime report must stay in rendered-startup evidence')
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD,w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    for name, structure in [("Module32FirstW",Module),("Module32NextW",Module),("Thread32First",Thread),("Thread32Next",Thread)]:
        function = getattr(kernel,name); function.argtypes = [w.HANDLE,ctypes.POINTER(structure)]; function.restype = w.BOOL
    dll = isolation.api()
    query = dll.SbieApi_QueryProcess
    query.argtypes = [w.HANDLE,w.LPWSTR,w.LPWSTR,w.LPWSTR,ctypes.POINTER(w.ULONG)];query.restype = w.LONG
    rows=[]
    for process in preflight.games_running():
        pid=process["ProcessId"];box=ctypes.create_unicode_buffer(64)
        image=ctypes.create_unicode_buffer(96);sid=ctypes.create_unicode_buffer(96);session=w.ULONG()
        if query(pid,box,image,sid,ctypes.byref(session))!=0 or box.value!=isolation.BOX:
            continue # 用途：绝不检查其他箱或用户正式游戏的运行细节。
        row={**process,"box_verified":box.value,"modules":[],"threads":[]}
        snapshot=kernel.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,pid)
        if snapshot!=ctypes.c_void_p(-1).value:
            module=Module();module.size=ctypes.sizeof(module)
            more=kernel.Module32FirstW(snapshot,ctypes.byref(module))
            while more:
                row["modules"].append({"name":module.name,"path":module.path,"bytes":module.bytes})
                more=kernel.Module32NextW(snapshot,ctypes.byref(module))
            kernel.CloseHandle(snapshot)
        else:
            row["module_snapshot_error"]=ctypes.get_last_error()
        snapshot=kernel.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD,0)
        if snapshot!=ctypes.c_void_p(-1).value:
            thread=Thread();thread.size=ctypes.sizeof(thread)
            more=kernel.Thread32First(snapshot,ctypes.byref(thread))
            while more:
                if thread.owner==pid:row["threads"].append(thread.id)
                more=kernel.Thread32Next(snapshot,ctypes.byref(thread))
            kernel.CloseHandle(snapshot)
        rows.append(row)
    # 用途：只读本次箱内游戏的对话框文字，不点击窗口、不发送任何输入。
    user = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    user.GetWindowTextW.argtypes = [w.HWND,w.LPWSTR,ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes = [w.HWND,ctypes.POINTER(w.DWORD)]
    user.EnumWindows.argtypes = [callback_type,w.LPARAM]
    user.EnumChildWindows.argtypes = [w.HWND,callback_type,w.LPARAM]
    windows=[];allowed={row["ProcessId"] for row in rows}
    def text_of(handle):
        buf=ctypes.create_unicode_buffer(8192);user.GetWindowTextW(handle,buf,len(buf));return buf.value
    @callback_type
    def window_callback(handle,unused):
        pid=w.DWORD();user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
        if pid.value in allowed:
            window={"pid":pid.value,"title":text_of(handle),"children":[]}
            @callback_type
            def child_callback(child,unused):
                text=text_of(child)
                if text:window["children"].append(text)
                return True
            user.EnumChildWindows(handle,child_callback,0)
            if window["title"] or window["children"]:windows.append(window)
        return True
    user.EnumWindows(window_callback,0)
    report={"time":datetime.now().astimezone().isoformat(),"scope":"Read-only Toolhelp module/thread metadata of "+isolation.BOX+" only",
            "interpretation":"Loaded DLLs do not prove initialization or the reason for a startup wait", "processes":rows,"windows":windows}
    if output is None:
        latest=sorted((ROOT/"evidence/sandbox-baseline").glob("20*"))[-1]
        output=latest/'runtime-observation.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"report":str(output),"processes":[{"pid":r["ProcessId"],"path":r.get("ExecutablePath"),
          "modules":len(r["modules"]),"module_names":[m["name"] for m in r["modules"]],"threads":r["threads"]} for r in rows]},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
