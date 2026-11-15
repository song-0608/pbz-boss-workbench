"""用途：在断网专用箱中启动独立Steam，确认能否使用既有合法离线会话；不启动PBZ。"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from ctypes import wintypes as w
import ctypes
import json
import subprocess
import sys
import time
import winreg

import test_isolation as isolation
import run_sandbox_baseline as baseline
import preflight

ROOT=Path(__file__).resolve().parent.parent


def registry_host():
    result={}
    for subkey,names in [(r'Software\Valve\Steam',('SteamPath','SteamExe')),
                          (r'Software\Valve\Steam\ActiveProcess',('pid',))]:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,subkey) as key:
                for name in names:
                    try:result[subkey+'\\'+name]=winreg.QueryValueEx(key,name)[0]
                    except FileNotFoundError:pass
        except FileNotFoundError:pass
    return result


def windows_for(pids):
    """用途：只读取指定箱进程的窗口文本，不激活、不发送键鼠输入。"""
    user=ctypes.WinDLL('user32',use_last_error=True)
    callback_type=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    user.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
    user.IsWindowVisible.argtypes=[w.HWND]
    user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
    user.EnumWindows.argtypes=[callback_type,w.LPARAM];user.EnumChildWindows.argtypes=[w.HWND,callback_type,w.LPARAM]
    rows=[]
    def text(h):
        b=ctypes.create_unicode_buffer(8192);user.GetWindowTextW(h,b,len(b));return b.value
    @callback_type
    def cb(h,unused):
        pid=w.DWORD();user.GetWindowThreadProcessId(h,ctypes.byref(pid))
        if pid.value in pids:
            row={'pid':pid.value,'title':text(h),'visible':bool(user.IsWindowVisible(h)),'children':[]}
            @callback_type
            def child(c,unused):
                value=text(c)
                if value:row['children'].append(value)
                return True
            user.EnumChildWindows(h,child,0)
            if row['title'] or row['children']:rows.append(row)
        return True
    user.EnumWindows(cb,0);return rows


def bootstrap(mode,work,container):
    logical=work/(mode+'-'+str(time.time_ns())+'.json')
    command=[str(isolation.SBIE/'Start.exe'),'/box:'+isolation.BOX,'/silent','/hide_window','/wait',
             str(ROOT/'build/steam-lab-bootstrap/steam-lab-bootstrap.exe'),mode,str(logical)]
    r=subprocess.run(command,capture_output=True,timeout=20)
    physical=isolation.virtual_file(container,logical)
    if r.returncode or not physical.is_file():raise RuntimeError('Sandbox bootstrap failed: '+mode)
    return json.loads(physical.read_text(encoding='utf-8'))


def box_processes(dll):
    ids=baseline.box_pids(dll)
    if not ids:return []
    command='Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -in @('+','.join(map(str,ids))+')} | Select-Object ProcessId,ParentProcessId,Name,ExecutablePath | ConvertTo-Json -Compress'
    r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,timeout=15)
    if r.returncode:raise RuntimeError('Cannot verify box process images')
    if not r.stdout.strip():return []
    value=json.loads(r.stdout);return value if isinstance(value,list) else [value]


def cleanup(dll):
    # 用途：先通过官方退出命令让研究Steam落盘会话；断网由调用者先执行，超时仍回收本箱。
    # 强制结束可能丢失离线所需信息，因此正常退出成功后只清理剩余辅助服务。
    if isolation.BOX=='PBZSteamLab':
        try:
            if any(p['Name'].lower()=='steam.exe' for p in box_processes(dll)) and not host_steam_pids(dll):
                subprocess.run([str(isolation.SBIE/'Start.exe'),'/box:PBZSteamLab','/silent',
                   r'E:\PBZSteamLabClient\steam.exe','-shutdown'],capture_output=True,timeout=4)
                until=time.monotonic()+10
                while time.monotonic()<until:
                    if not any(p['Name'].lower()=='steam.exe' for p in box_processes(dll)):break
                    time.sleep(.4)
        except Exception:
            pass # 用途：正常退出失败不能阻止研究箱强制回收；不会尝试终止主机Steam。
    subprocess.run([str(isolation.SBIE/'Start.exe'),'/box:'+isolation.BOX,'/terminate'],capture_output=True,timeout=15)
    for _ in range(30):
        if not baseline.box_pids(dll):return []
        time.sleep(.2)
    return baseline.box_pids(dll)


def host_steam_pids(dll):
    """用途：本机TCP不是独立网络空间；主机Steam若重启，停止本次研究箱实验并保留主机会话。"""
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
        '@(Get-Process steam,steamwebhelper -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id) | ConvertTo-Json -Compress'],capture_output=True,timeout=10)
    if result.returncode:raise RuntimeError('Cannot inspect host Steam')
    value=json.loads(result.stdout) if result.stdout.strip() else []
    ids=value if isinstance(value,list) else [value]
    outside=set(ids)-set(baseline.box_pids(dll))
    if not outside:
        return []
    # 用途：PS枚举和沙盒枚举不是原子快照；已退出的网页子进程不能误判成主机Steam。
    # 只保留第二次采样仍存在、且仍不属于研究箱的进程，随后仍按原规则保护主机会话。
    time.sleep(.25)
    confirmation=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
        '@(Get-Process steam,steamwebhelper -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id) | ConvertTo-Json -Compress'],capture_output=True,timeout=10)
    if confirmation.returncode:
        raise RuntimeError('Cannot confirm host Steam candidates')
    current=json.loads(confirmation.stdout) if confirmation.stdout.strip() else []
    survivors=current if isinstance(current,list) else [current]
    return sorted(outside.intersection(survivors)-set(baseline.box_pids(dll)))


def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    if 'windowsapps' in sys.executable.casefold():raise RuntimeError('Use non-Store Python')
    isolation.select_box('PBZSteamLab');dll=isolation.api();policy=isolation.check_policy(dll)
    if baseline.box_pids(dll) or preflight.games_running():raise RuntimeError('Research box or PBZ already running; preserve session')
    if host_steam_pids(dll):raise RuntimeError('Host Steam is running; preserve session')
    container=isolation.get_root(dll)
    now=datetime.now(timezone(timedelta(hours=8)));work=ROOT/'evidence/offline-steam'/now.strftime('%Y%m%d-%H%M%S');work.mkdir()
    host_before=registry_host();formal_before=baseline.formal_files()
    report={'time':now.isoformat(),'box':isolation.BOX,'work':str(work),'policy':policy,'game_launch_requested':False,
            'host_steam_registry_before':host_before,'host_steam_session_used':False,'internet_allowed':False,'lan_allowed':False,
            'client_loopback_tcp_allowed':policy['AllowNetworkAccess']==['y']}
    starter=None
    try:
        if '--native-start' in sys.argv[1:]:
            # 用途：用Sandboxie官方直接入口做对照，排除自写CreateProcess包装器的影响。
            # Start.exe本身的返回码不算客户端成功；下面仍读取箱内进程和真实活动用户。
            starter=subprocess.Popen([str(isolation.SBIE/'Start.exe'),'/box:'+isolation.BOX,
                '/silent','/wait',r'E:\PBZSteamLabClient\steam.exe','-offline','-silent'],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            time.sleep(1)
            report['client_start']={'method':'Sandboxie native Start.exe','start_exit_after_one_second':starter.poll(),
                                    'initial_box_processes':box_processes(dll)}
        else:
            report['client_start']=bootstrap('client-visible' if '--visible' in sys.argv[1:] else 'client',work,container)
        print('Independent sandboxed Steam started; observing offline initialization for up to 180 seconds.',flush=True)
        observations=[]
        for delay in range(36):
            time.sleep(5)
            outside=host_steam_pids(dll)
            if outside:
                report['stopped_for_new_host_steam_pids']=outside
                break
            inspect=bootstrap('inspect',work,container)
            processes=box_processes(dll);windows=windows_for({p['ProcessId'] for p in processes})
            observations.append({'elapsed_seconds':(delay+1)*5,'client':inspect,'processes':processes,'windows':windows})
            if inspect.get('official_existing_global_user_available') and inspect.get('active_client_in_same_box'):break
            if report['client_start'].get('child_exit_after_one_second') not in (None,259):
                if not any(p.get('Name','').casefold()=='steam.exe' for p in processes):break
            if starter and starter.poll() is not None and not any(p.get('Name','').casefold()=='steam.exe' for p in processes):break
            titles=' '.join(row['title']+' '+' '.join(row['children']) for row in windows).casefold()
            if any(token in titles for token in ('fatal error','致命错误','steam needs to be online','必须联网','无法连接')):break
        report['observations']=observations
        last=observations[-1]['client'] if observations else {}
        report['independent_client_has_active_user']=bool(last.get('official_existing_global_user_available') and last.get('active_client_in_same_box'))
        report['note']='Official ConnectToGlobalUser is existing client-session evidence; registry ActiveUser alone may be zero offline. Neither proves app ownership or game startup.'
    finally:
        report['remaining_box_pids']=cleanup(dll)
        if starter:
            try:report['native_start_final_exit']=starter.wait(timeout=3)
            except subprocess.TimeoutExpired:report['native_start_final_exit']=None
        after=baseline.formal_files();report['formal_files_changed']=[name for name in sorted(set(formal_before)|set(after)) if formal_before.get(name)!=after.get(name)]
        report['host_steam_registry_after']=registry_host();report['host_steam_registry_unchanged']=report['host_steam_registry_after']==host_before
        report['original_backup_compare']=preflight.compare(ROOT/'evidence/latest-preflight.json')
        (work/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        (ROOT/'evidence/offline-steam/latest-client-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    compact={k:v for k,v in report.items() if k not in ('policy','observations')}
    compact['window_messages']=[{'title':win['title'],'children':win['children']} for observation in report.get('observations',[])[-1:] for win in observation['windows']]
    print(json.dumps(compact,ensure_ascii=False,indent=2))
    return 0 if report.get('independent_client_has_active_user') and not report['formal_files_changed'] and not report['remaining_box_pids'] else 2


if __name__=='__main__':raise SystemExit(main())
