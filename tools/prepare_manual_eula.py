"""用途：本人阅读Steam许可协议的限时准备；PBZ文件和网络始终封锁，不代替用户接受协议。"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import errno
import os
import subprocess
import sys
import time
import test_offline_client as client
from test_wfp_isolation import change
from prepare_manual_login import save

ROOT = Path(__file__).resolve().parent.parent
LATEST = ROOT/'runtime/latest-eula-preparation.json'
WEB_RULES = [f'{image},Allow;Port=80,443;Protocol=TCP'
             for image in ('steam.exe','steamwebhelper.exe')]
EXE_DENY = r'*\PBZ.exe'
LIBRARY_DENY = r'E:\SteamLibrary\*'
GAME_DENY = str(client.baseline.GAME)+r'\*'


def update_status(state):
    """用途：只写本项目的阶段状态；不读取或修改Steam的协议接受记录。"""
    active = not state.get('restored', False)
    offline_confirmation = state.get('offline_confirmation_only', False)
    for path in (ROOT/'项目状态.json', ROOT.parent/'profiles/pbz-offline.json'):
        obj = json.loads(path.read_text(encoding='utf-8'))
        obj.update({'eula_preparation_network_authorized': True,
                    'eula_preparation_active': active,
                    'eula_preparation_state': state['state_file'],
                    'eula_preparation_deadline': state['deadline_at'],
                    'eula_preparation_external_network_enabled': active and state.get('client_web_network_enabled',False),
                    'offline_eula_confirmation_active': active and offline_confirmation,
                    'user_reports_eula_read': state.get('user_reports_eula_read',False),
                    'authentication_preparation_active': False,
                    'eula_acceptance_checked_by_agent': False})
        if path.name == '项目状态.json':
            obj.update({'updated_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
                        'status_summary': ('已收到本人已阅读通知；离线协议确认窗口准备中，PBZ程序封锁，等待本人选择。' if offline_confirmation else '仅客户端协议加载准备中；PBZ程序封锁，等待本人阅读处理。') if active else '协议准备窗口已结束，外网例外已撤销；协议处理和离线菜单仍需核对。',
                        'awaiting_user': '在研究Steam中本人阅读许可协议，处理后回复“协议已处理”；不要启动游戏。' if active else '核对许可协议是否已由本人处理，继续之前需复核离线规则。'})
        save(path, obj)


def restore(path, reason):
    """用途：先撤销联网再清理本研究箱；恢复原规则，不触碰主机Steam。"""
    state = json.loads(path.read_text(encoding='utf-8'))
    if state.get('restored'):
        return state
    client.isolation.select_box('PBZSteamLab'); dll = client.isolation.api()
    change('set','PBZSteamLab','AllowNetworkAccess','n')
    remaining = client.cleanup(dll)
    for rule in WEB_RULES:
        if rule in client.isolation.values(dll,'NetworkAccess'):
            change('delete','PBZSteamLab','NetworkAccess',rule)
    # 用途：先恢复原有整库/整游戏限制，再撤销临时EXE限制，始终存在启动封锁。
    for _ in range(state.get('library_rules_removed',0)):
        change('append','PBZSteamLab','ClosedFilePath',LIBRARY_DENY)
    for _ in range(state.get('game_rules_removed',0)):
        change('append','PBZSteamLab','ClosedFilePath',GAME_DENY)
    if state.get('exe_deny_added'):
        if EXE_DENY in client.isolation.values(dll,'ClosedFilePath'):
            change('delete','PBZSteamLab','ClosedFilePath',EXE_DENY)
    if not remaining:
        change('set','PBZSteamLab','AllowNetworkAccess',state['prior_allow_network'])
        client.isolation.check_policy(dll)
    after = client.baseline.formal_files()
    state.update({'restored': not remaining,
                  'restored_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
                  'restore_reason': reason, 'remaining_box_pids': remaining,
                  'formal_files_changed': [p for p in sorted(set(after)|set(state['formal_before']))
                                           if after.get(p) != state['formal_before'].get(p)],
                  'host_steam_registry_unchanged': client.registry_host() == state['host_registry_before']})
    save(path,state); update_status(state)
    public = {k:state.get(k) for k in ('started_at','deadline_at','restored','restored_at',
              'restore_reason','remaining_box_pids','formal_files_changed','host_steam_registry_unchanged')}
    save(ROOT/'evidence/offline-steam/latest-eula-preparation-result.json',public)
    return state


def watchdog(path):
    """用途：独立倒计时，即使对话结束，十分钟后仍会自动撤销网络例外。"""
    client.isolation.select_box('PBZSteamLab'); dll = client.isolation.api()
    while True:
        state = json.loads(path.read_text(encoding='utf-8'))
        if state.get('restored'):
            return
        reason = None
        if path.with_suffix('.stop').exists():
            reason = 'User finished or preparation cancelled'
        elif time.time() >= state['deadline_unix']:
            reason = 'Ten-minute EULA preparation deadline'
        else:
            try:
                if client.host_steam_pids(dll):
                    reason = 'Host Steam resumed; preserve host session'
                elif client.preflight.games_running():
                    reason = 'Game process detected; end client-only preparation'
            except Exception:
                reason = 'Monitoring failed; revoke client network'
        if reason:
            restore(path,reason); return
        time.sleep(3)


def probe_files(output):
    """用途：在箱内尝试只读打开两个游戏EXE，必须被拒绝；从不创建游戏进程。"""
    client.isolation.select_box('PBZSteamLab'); dll=client.isolation.api()
    if os.getpid() not in client.baseline.box_pids(dll):
        raise RuntimeError('File probe must run inside research box')
    rows=[]
    for relative in ('steam/PBZ.exe','platform/steam/PBZ.exe'):
        try:
            with (client.baseline.GAME/relative).open('rb') as stream:
                stream.read(1)
            rows.append({'relative':relative,'read_denied':False})
        except OSError as error:
            rows.append({'relative':relative,
                         'read_denied':isinstance(error,PermissionError) or error.winerror == 5 or error.errno == errno.EACCES,
                         'winerror':error.winerror,'errno':error.errno,'error_type':type(error).__name__})
    save(output,{'inside_box':True,'files':rows,'passed':all(r['read_denied'] for r in rows)})


def start(offline_confirmation=False):
    """用途：默认限时加载协议；离线确认模式全程不添加任何外网规则。"""
    client.isolation.select_box('PBZSteamLab'); dll=client.isolation.api()
    before=client.isolation.check_policy(dll)
    if client.baseline.box_pids(dll) or client.host_steam_pids(dll) or client.preflight.games_running():
        raise RuntimeError('Existing session preserved; cannot start preparation')
    for suffix in (r'\steamlibrary\*',r'\steamapps\common\pbz\*'):
        if not any(v.casefold().endswith(suffix) for v in before['ClosedFilePath']):
            raise RuntimeError('Required PBZ/library deny missing')
    if LATEST.is_file():
        old=Path(json.loads(LATEST.read_text(encoding='utf-8'))['state_file'])
        if not json.loads(old.read_text(encoding='utf-8')).get('restored'):
            raise RuntimeError('EULA preparation already active')
    now=datetime.now(timezone(timedelta(hours=8)))
    work=ROOT/'runtime'/now.strftime('eula-preparation-%Y%m%d-%H%M%S');work.mkdir()
    container=client.isolation.get_root(dll)
    probe=work/'file-gate.json'
    check=subprocess.run([str(client.isolation.SBIE/'Start.exe'),'/box:PBZSteamLab',
        '/silent','/hide_window','/wait',sys.executable,str(Path(__file__).resolve()),
        '--probe-files',str(probe)],capture_output=True,timeout=25)
    physical=client.isolation.virtual_file(container,probe)
    try:
        if check.returncode or not physical.is_file():
            raise RuntimeError('File-denial probe did not complete')
        gate=json.loads(physical.read_text(encoding='utf-8'))
        if not gate['passed']:
            raise RuntimeError('PBZ EXE read not denied; no external networking permitted')
        save(work/'verified-file-gate.json',gate)
    finally:
        if client.cleanup(dll):
            raise RuntimeError('Probe cleanup incomplete')
    path=work/'state.json'; deadline=now+timedelta(minutes=10)
    state={'state_file':str(path),'started_at':now.isoformat(),'deadline_at':deadline.isoformat(),
           'deadline_unix':deadline.timestamp(),'restored':False,
           'prior_allow_network':before['AllowNetworkAccess'][0],
           'formal_before':client.baseline.formal_files(),'host_registry_before':client.registry_host(),
           'exe_deny_added':False,'game_launched':False,'agreement_accepted_by_agent':False,
           'offline_confirmation_only':offline_confirmation,
           'user_reports_eula_read':offline_confirmation,
           'library_rules_removed':0,'game_rules_removed':0,
           'official_eula_url':'https://store.steampowered.com/eula/4115450_eula_0',
           'url_source':'local Steam appinfo common/eulas/0/url'}
    save(path,state);save(LATEST,{'state_file':str(path)})
    watcher=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--watchdog',str(path)],
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP)
    try:
        # 用途：即使客户端试图继续启动，任何位置的PBZ.exe也被本箱文件规则封锁。
        if EXE_DENY not in client.isolation.values(dll,'ClosedFilePath'):
            state['exe_deny_added']=True;save(path,state)
            change('append','PBZSteamLab','ClosedFilePath',EXE_DENY)
        # 用途：Steam可读取真实安装清单；所有PBZ.exe仍被独立封锁，写入仍按原策略虚拟化。
        # 必须再次用箱内只读探针验证EXE封锁，验证通过前绝不开放网页网络。
        for value in before['ClosedFilePath']:
            if value.casefold().endswith(r'\steamlibrary\*'):
                change('delete','PBZSteamLab','ClosedFilePath',LIBRARY_DENY)
                state['library_rules_removed']+=1;save(path,state)
            elif value.casefold().endswith(r'\steamapps\common\pbz\*'):
                change('delete','PBZSteamLab','ClosedFilePath',GAME_DENY)
                state['game_rules_removed']+=1;save(path,state)
        exe_probe=work/'exe-only-gate.json'
        checked=subprocess.run([str(client.isolation.SBIE/'Start.exe'),'/box:PBZSteamLab',
            '/silent','/hide_window','/wait',sys.executable,str(Path(__file__).resolve()),
            '--probe-files',str(exe_probe)],capture_output=True,timeout=25)
        exe_physical=client.isolation.virtual_file(container,exe_probe)
        if checked.returncode or not exe_physical.is_file():
            raise RuntimeError('EXE-only gate probe did not complete')
        exe_gate=json.loads(exe_physical.read_text(encoding='utf-8'))
        if not exe_gate['passed']:
            raise RuntimeError('Independent EXE block failed; no web access permitted')
        save(work/'verified-exe-only-gate.json',exe_gate)
        if client.cleanup(dll):
            raise RuntimeError('EXE probe helpers remain')
        state.update({'watchdog_pid':watcher.pid,'client_web_network_enabled':False})
        save(path,state);update_status(state)
        # 用途：先在外网全拒绝环境建立已有离线会话，避免部分联网触发登录重试。
        subprocess.Popen([str(client.isolation.SBIE/'Start.exe'),'/box:PBZSteamLab','/silent',
            r'E:\PBZSteamLabClient\steam.exe','-offline'],stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        from show_research_steam import show
        main_ready=False
        for _ in range(20):
            time.sleep(2)
            inspected=client.bootstrap('inspect',work,container)
            processes=client.box_processes(dll)
            main_ready=any(row['title']=='Steam' for row in client.windows_for({p['ProcessId'] for p in processes}))
            if inspected.get('official_existing_global_user_available') and main_ready:
                break
        if not inspected.get('official_existing_global_user_available') or not main_ready:
            raise RuntimeError('Existing offline main window unavailable; no new login requested')
        extra_rules=[] if offline_confirmation else WEB_RULES
        for rule in extra_rules:
            change('append','PBZSteamLab','NetworkAccess',rule)
        if sorted(client.isolation.values(dll,'NetworkAccess')) != sorted([*before['NetworkAccess'],*extra_rules]):
            raise RuntimeError('Unexpected web network policy')
        state['client_web_network_enabled']=bool(extra_rules);save(path,state);update_status(state)
        shown=show(15);save(work/'window.json',shown)
        # 用途：仅向官方客户端请求已有的协议流程；游戏程序读权限始终被拒绝。
        # Steam是否能展示协议由真实窗口验证，返回码不能当作已展示或已接受。
        action=client.bootstrap('game',work,container)
        save(work/'official-dialog-request.json',action)
        print(json.dumps({'deadline_at':deadline.isoformat(),'file_denial_probe_passed':gate['passed'],
                          'pbz_exe_blocked':True,'library_metadata_readable':True,'research_window':shown,
                          'external_network_enabled':bool(extra_rules),'offline_confirmation_only':offline_confirmation,
                          'state_file':str(path),'agreement_accepted_by_agent':False},ensure_ascii=False,indent=2))
    except Exception:
        path.with_suffix('.stop').touch();restore(path,'Preparation failed');raise


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    args=sys.argv[1:]
    if len(args)==2 and args[0]=='--probe-files':
        probe_files(Path(args[1]))
    elif len(args)==2 and args[0]=='--watchdog':
        watchdog(Path(args[1]))
    elif args==['--finish']:
        path=Path(json.loads(LATEST.read_text(encoding='utf-8'))['state_file'])
        path.with_suffix('.stop').touch()
        for _ in range(20):
            state=json.loads(path.read_text(encoding='utf-8'))
            if state.get('restored'):
                print(json.dumps({'restored':True,'remaining_box_pids':state['remaining_box_pids']},ensure_ascii=False));break
            time.sleep(1)
        else:
            raise RuntimeError('Restore pending; inspect lease')
    elif args==['--offline-confirmation']:
        start(offline_confirmation=True)
    elif not args:
        start()
    else:
        raise RuntimeError('Unsupported command')
