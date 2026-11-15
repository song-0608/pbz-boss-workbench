"""用途：原版授权验证期间，只读记录窗口及真实进程退出码；不调试、不注入、不操作游戏。"""
import ctypes,json,sys,time
from ctypes import wintypes as w
from pathlib import Path
import official_validation as v
from test_game_with_offline_client import game_capture


def observe(seconds=120,stop_on_render=True):
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    state=json.loads(v.state_path().read_text(encoding='utf-8'));work=Path(state['work'])
    offline=bool(state.get('offline_validation'))
    c.isolation.check_policy(dll,allow_official_validation=not offline,allow_offline_validation=offline)
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
    k.GetExitCodeProcess.argtypes=[w.HANDLE,ctypes.POINTER(w.DWORD)]
    k.CloseHandle.argtypes=[w.HANDLE]
    u=ctypes.WinDLL('user32',use_last_error=True);cb=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    u.EnumWindows.argtypes=[cb,w.LPARAM];u.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
    u.GetClassNameW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int];u.IsWindowVisible.argtypes=[w.HWND]
    report={'started_at':v.utc8(),'no_debugger':True,'no_injection':True,'menu_verified':False,
            'observations':[],'process_exit_codes':{},'reason':None}
    handles={};metadata={};seen=False;empty=0;start=time.monotonic();last_progress=-20;render_captured=False;last_capture=-20
    try:
        while time.monotonic()-start<seconds:
            current=json.loads(v.state_path().read_text(encoding='utf-8'))
            if current['restored'] or time.time()>=current['deadline_unix']:
                report['reason']='lease_ended';break
            if c.host_steam_pids(dll):
                report['reason']='outside_steam_detected';break
            ps=[p for p in c.box_processes(dll) if p['Name'].lower()=='pbz.exe'];ids={p['ProcessId'] for p in ps}
            if ids:seen=True;empty=0
            elif seen:empty+=1
            for p in ps:
                pid=p['ProcessId'];metadata[pid]=p
                if pid not in handles:
                    # 用途：仅请求查询退出码的权限；不申请读写内存或创建线程权限。
                    handle=k.OpenProcess(0x1000,False,pid)
                    if handle:handles[pid]=handle
            for pid,h in handles.items():
                code=w.DWORD()
                if k.GetExitCodeProcess(h,ctypes.byref(code)) and code.value!=259:
                    report['process_exit_codes'][str(pid)]={'code':code.value,'hex':f'0x{code.value:08X}'}
            classes=[]
            @cb
            def visit(h,l):
                pid=w.DWORD();u.GetWindowThreadProcessId(h,ctypes.byref(pid))
                if pid.value in ids and u.IsWindowVisible(h):
                    name=ctypes.create_unicode_buffer(128);u.GetClassNameW(h,name,len(name))
                    classes.append({'pid':pid.value,'class':name.value})
                return True
            u.EnumWindows(visit,0)
            windows=[row for row in c.windows_for(ids) if row['visible']]
            row={'at':v.utc8(),'pids':sorted(ids),'window_classes':classes,'windows':windows}
            report['observations'].append(row)
            messages=' '.join(t for win in windows for t in win['children'])
            if any(t in messages for t in ['无法访问服务器','无法连接服务器']):
                report['reason']='server_unreachable';time.sleep(.5)
                report['capture']=game_capture(dll,work/'observed-server-error.png');break
            if any(q['class']=='UnrealWindow' or q['class'].endswith(':UnrealWindow') for q in classes):
                if not render_captured:
                    report['capture']=game_capture(dll,work/'render-window.png')
                    render_captured=report['capture'].get('captured',False)
                    print(json.dumps({'render_window_observed':True,'capture':report['capture']},ensure_ascii=False),flush=True)
                if stop_on_render:
                    report['reason']='render_window_requires_visual_review';break
                if time.monotonic()-start-last_capture>=20:
                    pic=game_capture(dll,work/('render-check-'+str(round(time.monotonic()-start))+'.png'))
                    if pic.get('captured'):
                        report.setdefault('periodic_captures',[]).append(pic)
                        print(json.dumps({'periodic_capture':pic},ensure_ascii=False),flush=True)
                    last_capture=time.monotonic()-start
            if seen and empty>=2:
                report['reason']='all_pbz_processes_exited';break
            elapsed=time.monotonic()-start
            if elapsed-last_progress>=20:
                print(json.dumps({'elapsed_seconds':round(elapsed),'pbz_pids':sorted(ids),
                                  'window_classes':classes},ensure_ascii=False),flush=True)
                last_progress=elapsed
            time.sleep(.6)
        if report['reason'] is None:report['reason']='bounded_observation_timeout'
        report['ended_at']=v.utc8();report['processes']=list(metadata.values())
        v.save(work/'startup-observation.json',report)
        print(json.dumps({key:value for key,value in report.items() if key!='observations'},ensure_ascii=False),flush=True)
        return report
    finally:
        for handle in handles.values():k.CloseHandle(handle)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');observe()
