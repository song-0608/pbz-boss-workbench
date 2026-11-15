"""用途：有效授权租期内，仅点击PBZ服务器错误框的“重试”一次，记录连接元数据。"""
import ctypes,json,subprocess,sys,time
from ctypes import wintypes as w
from pathlib import Path
import official_validation as v
from test_game_with_offline_client import game_capture


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    c.isolation.check_policy(dll,allow_official_validation=True)
    if c.host_steam_pids(dll):raise RuntimeError('Preserve host Steam')
    state=json.loads(v.state_path().read_text(encoding='utf-8'));work=Path(state['work'])
    record=work/'one-official-retry.json'
    if record.exists():raise RuntimeError('One retry already used in this lease')
    allowed={p['ProcessId'] for p in c.box_processes(dll) if p['Name'].lower()=='pbz.exe'}
    u=ctypes.WinDLL('user32',use_last_error=True);cb=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    u.EnumWindows.argtypes=[cb,w.LPARAM];u.EnumChildWindows.argtypes=[w.HWND,cb,w.LPARAM]
    u.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
    u.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int];u.IsWindowVisible.argtypes=[w.HWND]
    u.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
    candidates=[]
    def text(handle):
        b=ctypes.create_unicode_buffer(1024);u.GetWindowTextW(handle,b,len(b));return b.value
    @cb
    def visit(handle,unused):
        pid=w.DWORD();u.GetWindowThreadProcessId(handle,ctypes.byref(pid))
        if pid.value in allowed and u.IsWindowVisible(handle) and 'Phantom Blade Zero' in text(handle):
            rows=[]
            @cb
            def child(h,l):
                rows.append((h,text(h)));return True
            u.EnumChildWindows(handle,child,0)
            buttons=[h for h,t in rows if t in ('重试','重試')]
            if len(buttons)==1 and any('无法访问服务器' in t for h,t in rows):
                candidates.append((buttons[0],pid.value))
        return True
    u.EnumWindows(visit,0)
    if len(candidates)!=1:raise RuntimeError('Exact server error/retry button not confirmed')
    report={'requested_at':v.utc8(),'pid':candidates[0][1],'retry_count':1,'connections':[],
            'support_browser_opened':False,'menu_verified':False}
    v.save(record,report) # 用途：先落盘占用一次尝试，脚本异常也不能无限重试。
    if not u.PostMessageW(candidates[0][0],0x00F5,0,0):raise ctypes.WinError(ctypes.get_last_error())
    seen=set();end=time.monotonic()+15
    while time.monotonic()<end:
        current=json.loads(v.state_path().read_text(encoding='utf-8'))
        if current['restored'] or time.time()>=current['deadline_unix']:break
        r=subprocess.run(['netstat.exe','-ano','-p','TCP'],capture_output=True,timeout=3)
        for line in r.stdout.decode(errors='replace').splitlines():
            fields=line.split()
            if len(fields)==5 and fields[0]=='TCP' and fields[-1].isdigit() and int(fields[-1]) in allowed:
                row=tuple(fields[1:])
                if row not in seen:
                    seen.add(row);report['connections'].append({'at':v.utc8(),'local':row[0],
                      'remote':row[1],'state':row[2],'pid':int(row[3])})
        time.sleep(.3)
    report['observed_at']=v.utc8();report['capture']=game_capture(dll,work/'after-one-official-retry.png')
    report['windows']=c.windows_for(allowed);v.save(record,report)
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
