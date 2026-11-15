"""用途：官方Steam入口的限时原版测试；网络默认拒绝、写入虚拟化，不注入Mod或绕过认证。"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import ctypes
from ctypes import wintypes as w
import hashlib
import json
import shutil
import subprocess
import sys
import time
import test_offline_client as client
from test_wfp_isolation import change
from test_rendered_startup import EXPECTED

ROOT = Path(__file__).resolve().parent.parent
GAME = client.baseline.GAME
LIBRARY_RULE = r'E:\SteamLibrary\*'
GAME_RULE = str(GAME) + r'\*'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def game_capture(dll, target):
    """用途：只截图本研究箱PBZ的可见窗口，不截图Steam登录或桌面其他程序。"""
    from PIL import Image
    processes = client.box_processes(dll)
    allowed = {p['ProcessId'] for p in processes if p['Name'].casefold() == 'pbz.exe'}
    if not allowed:
        return {'captured': False}
    user = ctypes.WinDLL('user32', use_last_error=True)
    # 用途：窗口尺寸和像素使用同一DPI坐标，避免游戏画面被截断。
    user.SetProcessDPIAware()
    gdi = ctypes.WinDLL('gdi32', use_last_error=True)
    callback = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes = [callback, w.LPARAM]
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.IsWindowVisible.argtypes = [w.HWND]
    user.GetClassNameW.argtypes = [w.HWND,w.LPWSTR,ctypes.c_int]
    user.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
    user.GetDC.argtypes = [w.HWND]; user.GetDC.restype = w.HDC
    user.ReleaseDC.argtypes = [w.HWND, w.HDC]
    user.PrintWindow.argtypes = [w.HWND, w.HDC, w.UINT]
    gdi.CreateCompatibleDC.argtypes = [w.HDC]; gdi.CreateCompatibleDC.restype = w.HDC
    gdi.CreateCompatibleBitmap.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int]; gdi.CreateCompatibleBitmap.restype = w.HBITMAP
    gdi.SelectObject.argtypes = [w.HDC, w.HGDIOBJ]; gdi.SelectObject.restype = w.HGDIOBJ
    gdi.DeleteObject.argtypes = [w.HGDIOBJ]; gdi.DeleteDC.argtypes = [w.HDC]
    found = []
    @callback
    def visit(handle, unused):
        pid = w.DWORD(); user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        if pid.value in allowed and user.IsWindowVisible(handle):
            kind=ctypes.create_unicode_buffer(256);user.GetClassNameW(handle,kind,len(kind))
            # 用途：控制台可能比真正游戏窗口大，且可能含账号标识，不把它当菜单截图。
            if kind.value in ('ConsoleWindowClass','CASCADIA_HOSTING_WINDOW_CLASS','PseudoConsoleWindow'):
                return True
            rect = w.RECT(); user.GetWindowRect(handle, ctypes.byref(rect))
            width, height = rect.right - rect.left, rect.bottom - rect.top
            if 250 <= width <= 7680 and 100 <= height <= 4320:
                found.append((handle, width, height,kind.value))
        return True
    user.EnumWindows(visit, 0)
    if not found:
        return {'captured': False}
    handle, width, height,kind = max(found, key=lambda row: (row[3]=='UnrealWindow' or row[3].endswith(':UnrealWindow'),row[1] * row[2]))
    dc = user.GetDC(handle); memory = gdi.CreateCompatibleDC(dc)
    bitmap = gdi.CreateCompatibleBitmap(dc, width, height); previous = gdi.SelectObject(memory, bitmap)
    class Header(ctypes.Structure):
        _fields_ = [('size',w.DWORD),('width',w.LONG),('height',w.LONG),('planes',w.WORD),('bits',w.WORD),('compression',w.DWORD),('bytes',w.DWORD),('x',w.LONG),('y',w.LONG),('used',w.DWORD),('important',w.DWORD)]
    class Info(ctypes.Structure):
        _fields_ = [('header',Header),('colors',w.DWORD * 3)]
    gdi.GetDIBits.argtypes = [w.HDC,w.HBITMAP,w.UINT,w.UINT,w.LPVOID,ctypes.POINTER(Info),w.UINT]
    try:
        if not user.PrintWindow(handle, memory, 2):
            return {'captured': False, 'reason': 'PrintWindow failed'}
        info = Info(); info.header = Header(ctypes.sizeof(Header),width,-height,1,32,0,0,0,0,0,0)
        buffer = ctypes.create_string_buffer(width * height * 4)
        if gdi.GetDIBits(memory, bitmap, 0, height, buffer, ctypes.byref(info), 0) != height:
            return {'captured': False, 'reason': 'GetDIBits failed'}
        image = Image.frombytes('RGB', (width,height), buffer.raw, 'raw','BGRX')
        image.save(target)
        return {'captured': True, 'file': str(target), 'width':width,'height':height,'window_class':kind,
                'menu_or_gameplay_verified': False}
    finally:
        gdi.SelectObject(memory, previous); gdi.DeleteObject(bitmap); gdi.DeleteDC(memory); user.ReleaseDC(handle,dc)


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    client.isolation.select_box('PBZSteamLab')
    dll = client.isolation.api(); policy = client.isolation.check_policy(dll)
    if client.baseline.box_pids(dll) or client.host_steam_pids(dll) or client.preflight.games_running():
        raise RuntimeError('Existing client/game session preserved; cannot start controlled test')
    for relative, expected in EXPECTED.items():
        if digest(GAME / relative) != expected:
            raise RuntimeError('PBZ executable changed; audit required')
    for directory in (GAME/'steam', GAME/'platform/steam'):
        if any((directory/name).exists() for name in ('UE4SS.dll','UE4SS-settings.ini','dwmapi.dll','xinput1_3.dll')):
            raise RuntimeError('Unexpected loader in formal installation')
    latest_probe = json.loads((ROOT/'evidence/isolation-probe/latest-result.json').read_text(encoding='utf-8'))
    if latest_probe.get('box') != 'PBZSteamLab' or not latest_probe.get('passed'):
        raise RuntimeError('No passed isolation evidence for this box')
    container = client.isolation.get_root(dll)
    install = client.isolation.virtual_file(container, Path(r'E:\PBZSteamLabClient'))
    now = datetime.now(timezone(timedelta(hours=8)))
    work = ROOT/'evidence/rendered-startup'/now.strftime('%Y%m%d-%H%M%S-steam-offline')
    work.mkdir(parents=True)
    before = client.baseline.formal_files(); host = client.registry_host()
    report = {'time':now.isoformat(),'box':'PBZSteamLab','work':str(work),'policy_before':policy,
              'official_steam_applaunch':'--direct-native-launch' not in sys.argv[1:],
              'original_installed_exe_launch':'--direct-native-launch' in sys.argv[1:],
              'internet_allowed':False,'lan_allowed':False,
              'game_network_allowed':False,'ue4ss_deployed':False,'boss_script_enabled':False,
              'menu_verified':False,'gameplay_verified':False,'formal_file_count_before':len(before),
              'observations':[],'captures':[],'user_reported_offline':True}
    interactive = '--interactive-review' in sys.argv[1:]
    diagnostic = '--diagnose-startup' in sys.argv[1:]
    report['startup_diagnostic_requested']=diagnostic
    if interactive:
        # 用途：前置检查已确认本箱空闲，清除上一轮停止标记，避免新测试立即退出。
        (ROOT/'runtime/end-offline-game-review.flag').unlink(missing_ok=True)
    lease = {'running':False,'work':str(work),'internet_allowed':False,'gameplay_verified':False}
    report['interactive_user_review'] = interactive
    library_rules = [v for v in client.isolation.values(dll,'ClosedFilePath') if v.casefold().endswith(r'\steamlibrary\*')]
    game_rules = [v for v in client.isolation.values(dll,'ClosedFilePath') if v.casefold().endswith(r'\steamapps\common\pbz\*')]
    if not library_rules or not game_rules:
        raise RuntimeError('Expected preparation-time game blocks missing; inspect state')
    starter = None
    try:
        # 用途：认证例外已撤销，才暂时解除研究箱的游戏库封锁；默认文件虚拟化仍生效。
        # 不配置OpenFilePath，不直接给主机存档写权限；结束时恢复先前规则数量。
        for _ in library_rules:
            change('delete','PBZSteamLab','ClosedFilePath',LIBRARY_RULE)
        for _ in game_rules:
            change('delete','PBZSteamLab','ClosedFilePath',GAME_RULE)
        report['policy_during'] = client.isolation.check_policy(dll)
        # 复制真实已安装清单到箱内Steam库，不写正式清单、不伪造许可或AppID。
        manifest = GAME.parents[1]/'appmanifest_4115450.acf'
        destination = client.isolation.virtual_file(container,manifest)
        destination.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(manifest,destination)
        library = install/'steamapps/libraryfolders.vdf'
        report['library_before_sha256'] = digest(library)
        # 研究副本独立枚举已安装PBZ；账号认证和游戏许可仍交给官方Steam。
        library.write_text('"libraryfolders"\n{\n "0" { "path" "E:\\\\PBZSteamLabClient" "apps" { } }\n "1" { "path" "E:\\\\SteamLibrary" "apps" { "4115450" "0" } }\n}\n',encoding='utf-8')
        saved_count = 0
        for source_name in before:
            source = Path(source_name)
            if source.is_relative_to(GAME/'ProjectPBZ/Saved'):
                mirror = client.isolation.virtual_file(container,source)
                if not mirror.exists():
                    mirror.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,mirror)
                    if digest(mirror) != before[source_name]['sha256']:
                        raise RuntimeError('Virtual save seed hash mismatch')
                    saved_count += 1
        report['game_saved_files_seeded_only_in_box'] = saved_count
        report['saved_mirrors_before'] = {str(p.relative_to(container)):digest(p) for p in (client.isolation.virtual_file(container,GAME/'ProjectPBZ/Saved')).rglob('*') if p.is_file()}
        starter = subprocess.Popen([str(client.isolation.SBIE/'Start.exe'),'/box:PBZSteamLab','/silent',r'E:\PBZSteamLabClient\steam.exe','-offline'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        print('Offline isolated Steam requested; preparing official game launch. No loader deployed.',flush=True)
        login_seen_at=None
        for _ in range(20):
            time.sleep(3)
            if client.host_steam_pids(dll):
                raise RuntimeError('Host Steam appeared; preserve host and end research box')
            report['client_before_launch'] = client.bootstrap('inspect',work,container)
            current=client.box_processes(dll)
            visible_titles=[win['title'] for win in client.windows_for({p['ProcessId'] for p in current}) if win['visible']]
            # 用途：官方接口可能返回缓存的用户身份；登录窗口存在时，不能当作离线会话已就绪。
            if any('登录 Steam' in title or 'sign in to steam' in title.lower() for title in visible_titles):
                report['client_login_window_observed']=True
                if login_seen_at is None:login_seen_at=time.monotonic()
                # 用途：启动期间可能短暂显示登录窗；只在持续出现时判为阻塞，期间不启动游戏。
                if time.monotonic()-login_seen_at>=15:
                    report['startup_blocker']='research_steam_requires_user_login'
                    raise RuntimeError('Research Steam remained at login; cached identity is not a ready offline session')
                continue
            login_seen_at=None
            report['client_main_window_observed']='Steam' in visible_titles
            if (report['client_before_launch'].get('official_existing_global_user_available')
                    and report['client_main_window_observed']):
                break
        if (not report['client_before_launch'].get('official_existing_global_user_available')
                or not report.get('client_main_window_observed')):
            raise RuntimeError('Official client has no existing global user; do not launch game')
        # 用户会话可用不证明游戏许可；继续由官方客户端决定能否启动，不绕过校验。
        report['launch'] = client.bootstrap('direct-game' if '--direct-native-launch' in sys.argv[1:] else 'game',work,container)
        start = time.monotonic()
        if interactive:
            lease = {'started_at':now.isoformat(),'deadline_at':(datetime.now(timezone(timedelta(hours=8)))+timedelta(minutes=10)).isoformat(),
                     'work':str(work),'watcher_pid':__import__('os').getpid(),'running':True,'internet_allowed':False,
                     'legal_agreement_acceptance_requires_user':True,'gameplay_verified':False}
            (ROOT/'runtime/current-offline-game-review.json').write_text(json.dumps(lease,ensure_ascii=False,indent=2),encoding='utf-8')
            from show_research_steam import show
            report['research_window_shown'] = show(10)
        for index in range(300 if interactive else 45):
            time.sleep(2)
            if interactive and ((ROOT/'runtime/end-offline-game-review.flag').exists() or time.monotonic()-start>600):
                report['review_ended_or_deadline'] = True;break
            if client.host_steam_pids(dll):
                report['stopped_for_host_steam'] = True; break
            processes = client.box_processes(dll)
            game_pids = {p['ProcessId'] for p in processes if p['Name'].casefold()=='pbz.exe'}
            windows = client.windows_for({p['ProcessId'] for p in processes})
            elapsed = round(time.monotonic()-start,1)
            report['observations'].append({'elapsed_seconds':elapsed,'processes':processes,'windows':windows})
            if index in (5,15,30) and game_pids:
                capture = game_capture(dll,work/f'game-{index}.png'); report['captures'].append(capture)
                if capture.get('captured'):
                    print('Captured isolated PBZ window for visual verification.',flush=True)
            messages = ' '.join(win['title']+' '+' '.join(win['children']) for win in windows)
            if diagnostic and any(token in messages for token in ('无法访问服务器','无法连接服务器')):
                # 用途：遇到已知游戏端阻断即留证收尾，不重试、不联网、不进入正式进度。
                report['game_origin_blocker_windows']=[win for win in windows if win['pid'] in game_pids]
                report['startup_blocker']='game_server_unreachable'
                capture=game_capture(dll,work/'pbz-startup-blocker.png');report['captures'].append(capture)
                observed=subprocess.run([sys.executable,str(ROOT/'tools/capture_runtime_observation.py'),
                    '--steam-lab','--output',str(work/'runtime-observation.json')],
                    capture_output=True,timeout=25)
                report['read_only_runtime_observation']={'exit_code':observed.returncode,
                    'file':str(work/'runtime-observation.json'),
                    'report_exists':(work/'runtime-observation.json').is_file()}
                print('Real PBZ server-unreachable dialog captured; collecting read-only metadata and ending test.',flush=True)
                break
            if any(token in messages for token in ('加载 SteamAPI 失败','加载SteamAPI失败','致命错误','Fatal Error')):
                report['observed_blocker_text'] = messages; break
            if index in (9,19,29,39):
                print(f'Observed official offline launch for {elapsed}s; PBZ processes: {len(game_pids)}.',flush=True)
            if not interactive and elapsed > 45 and not game_pids:
                break
        report['client_after_launch'] = client.bootstrap('inspect',work,container)
        report['pbz_process_observed'] = any(any(p['Name'].casefold()=='pbz.exe' for p in row['processes']) for row in report['observations'])
    except Exception as error:
        report['error'] = str(error)
    finally:
        report['remaining_box_pids'] = client.cleanup(dll)
        # 用途：只恢复本箱暂时移除的配置，不覆盖用户其他Sandboxie设置。
        for _ in library_rules:
            change('append','PBZSteamLab','ClosedFilePath',LIBRARY_RULE)
        for _ in game_rules:
            change('append','PBZSteamLab','ClosedFilePath',GAME_RULE)
        report['policy_after'] = client.isolation.check_policy(dll)
        after = client.baseline.formal_files()
        report['formal_file_count_after'] = len(after)
        report['formal_files_changed'] = [p for p in sorted(set(before)|set(after)) if before.get(p)!=after.get(p)]
        report['host_steam_registry_unchanged'] = client.registry_host()==host
        report['original_backup_compare'] = client.preflight.compare(ROOT/'evidence/latest-preflight.json')
        mirror_root = client.isolation.virtual_file(container,GAME/'ProjectPBZ/Saved')
        report['saved_mirrors_after'] = {str(p.relative_to(container)):digest(p) for p in mirror_root.rglob('*') if p.is_file()}
        old = report.get('saved_mirrors_before',{}); new = report['saved_mirrors_after']
        report['virtual_saved_files_changed'] = [p for p in sorted(set(old)|set(new)) if old.get(p)!=new.get(p)]
        (work/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        (ROOT/'evidence/rendered-startup/latest-offline-steam-game-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if interactive:
            lease['running']=False;lease['remaining_box_pids']=report['remaining_box_pids']
            lease['formal_files_changed']=report['formal_files_changed']
            (ROOT/'runtime/current-offline-game-review.json').write_text(json.dumps(lease,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('policy_before','policy_during','policy_after','observations','saved_mirrors_before','saved_mirrors_after')},ensure_ascii=False,indent=2))
    return 0 if report.get('menu_verified') and not report['formal_files_changed'] and not report['remaining_box_pids'] else 2


if __name__=='__main__':
    raise SystemExit(main())
