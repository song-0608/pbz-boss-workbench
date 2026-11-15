"""用途：限时开放独立Steam本人登录；禁止访问游戏库，超时或收到结束指令即恢复离线规则。"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import os
import shutil
import subprocess
import sys
import time
import test_offline_client as client
from test_wfp_isolation import change

ROOT = Path(__file__).resolve().parent.parent
AUTH_RULES = ['steam.exe,Allow;Port=80,443,27014-27050;Protocol=TCP',
              'steamwebhelper.exe,Allow;Port=80,443;Protocol=TCP']
LIBRARY_DENY = r'E:\SteamLibrary\*'
LATEST = ROOT / 'runtime/latest-login-preparation.json'


def save(path, value):
    # 用途：Windows上看门狗短暂读取文件可能阻止原子替换；使用独立临时文件并有限重试。
    temporary = path.with_name(path.name + '.' + str(os.getpid()) + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    for attempt in range(20):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt==19:raise
            time.sleep(.05)


def restore(path, reason):
    state = json.loads(path.read_text(encoding='utf-8'))
    if state.get('restored'):
        return state
    client.isolation.select_box('PBZSteamLab')
    dll = client.isolation.api()
    # 用途：先关闭研究箱网络，再关研究客户端；绝不操作主机Steam或全机防火墙。
    change('set', 'PBZSteamLab', 'AllowNetworkAccess', 'n')
    remaining = client.cleanup(dll)
    for rule in AUTH_RULES:
        if rule in client.isolation.values(dll, 'NetworkAccess'):
            change('delete', 'PBZSteamLab', 'NetworkAccess', rule)
    library = Path(state['library_file'])
    backup = Path(state['library_backup'])
    if backup.is_file():
        shutil.copy2(backup, library)
    if not remaining:
        change('set', 'PBZSteamLab', 'AllowNetworkAccess', state['prior_allow_network'])
        client.isolation.check_policy(dll)
    after = client.baseline.formal_files()
    state.update({'restored': not remaining, 'restored_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
                  'restore_reason': reason, 'remaining_box_pids': remaining,
                  'formal_files_changed': [p for p in sorted(set(state['formal_before']) | set(after)) if state['formal_before'].get(p) != after.get(p)],
                  'host_steam_registry_unchanged': client.registry_host() == state['host_registry_before']})
    save(path, state)
    public = {key: state.get(key) for key in ('started_at','deadline_at','restored','restored_at','restore_reason','remaining_box_pids','formal_files_changed','host_steam_registry_unchanged')}
    save(ROOT / 'evidence/offline-steam/latest-login-preparation-result.json', public)
    model_path = ROOT / '项目状态.json'
    if model_path.is_file():
        model = json.loads(model_path.read_text(encoding='utf-8'))
        model.update({'updated_at': state['restored_at'], 'authentication_preparation_active': not state['restored'],
                      'status_summary': '认证准备已结束并恢复离线规则；等待验证本人建立的离线会话，游戏内测试尚未通过。',
                      'blocked_reason': '尚需确认合法离线会话和游戏真实存档隔离，不能据登录界面宣称Boss功能可用。'})
        save(model_path, model)
    return state


def watchdog(path):
    client.isolation.select_box('PBZSteamLab')
    dll = client.isolation.api()
    while True:
        state = json.loads(path.read_text(encoding='utf-8'))
        if state.get('restored'):
            return
        reason = None
        if path.with_suffix('.stop').exists():
            reason = 'User finished or preparation cancelled'
        elif time.time() >= state['deadline_unix']:
            reason = 'Ten-minute authentication preparation deadline'
        else:
            try:
                if client.host_steam_pids(dll):
                    reason = 'Host Steam restarted; preserve host session'
                elif client.preflight.games_running():
                    reason = 'Game process detected; authentication preparation must not run games'
            except Exception:
                reason = 'Process monitoring failed; close authentication preparation'
        if reason:
            restore(path, reason)
            return
        time.sleep(3)


def start():
    client.isolation.select_box('PBZSteamLab')
    dll = client.isolation.api()
    before = client.isolation.check_policy(dll)
    if before['AllowNetworkAccess'] != ['y']:
        raise RuntimeError('Verified client-loopback rule-engine mode is required')
    if client.baseline.box_pids(dll) or client.host_steam_pids(dll) or client.preflight.games_running():
        raise RuntimeError('Preserve existing Steam/game sessions; cannot start login preparation')
    if LATEST.is_file():
        previous = Path(json.loads(LATEST.read_text(encoding='utf-8'))['state_file'])
        if previous.is_file() and not json.loads(previous.read_text(encoding='utf-8')).get('restored'):
            raise RuntimeError('A login preparation lease already exists')
    if not any(v.casefold().endswith(r'\steamapps\common\pbz\*') for v in before['ClosedFilePath']):
        raise RuntimeError('PBZ launch block is missing')
    if not any(v.casefold().endswith(r'\steamlibrary\*') for v in before['ClosedFilePath']):
        raise RuntimeError('Formal library block is missing')
    container = client.isolation.get_root(dll)
    install = client.isolation.virtual_file(container, Path(r'E:\PBZSteamLabClient'))
    if any(p.name != 'appmanifest_228980.acf' for p in (install / 'steamapps').glob('appmanifest_*.acf')):
        raise RuntimeError('Unexpected installed games in preparation client')
    now = datetime.now(timezone(timedelta(hours=8)))
    work = ROOT / 'runtime' / now.strftime('auth-preparation-%Y%m%d-%H%M%S')
    work.mkdir()
    library = install / 'steamapps/libraryfolders.vdf'
    backup = work / 'libraryfolders-before.vdf'
    shutil.copy2(library, backup)
    path = work / 'state.json'
    deadline = now + timedelta(minutes=10)
    state = {'started_at': now.isoformat(), 'deadline_at': deadline.isoformat(), 'deadline_unix': deadline.timestamp(),
             'restored': False, 'prior_allow_network': before['AllowNetworkAccess'][0], 'library_file': str(library),
             'library_backup': str(backup), 'formal_before': client.baseline.formal_files(),
             'host_registry_before': client.registry_host(), 'account_contents_recorded': False, 'game_launched': False}
    save(path, state)
    save(LATEST, {'state_file': str(path)})
    # 用途：独立看门狗不依赖当前对话继续运行；即使用户未回复，也会到期关箱并恢复规则。
    watcher = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--watchdog', str(path)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    try:
        # 登录时不向客户端展示正式游戏库；文件限制只影响研究箱。
        library.write_text('"libraryfolders"\n{\n "0"\n {\n  "path" "E:\\\\PBZSteamLabClient"\n  "apps" { }\n }\n}\n', encoding='utf-8')
        # 用途：本轮已要求原有整库封锁存在，不重复追加，避免每次本人登录都累积同值规则。
        for rule in AUTH_RULES:
            change('append', 'PBZSteamLab', 'NetworkAccess', rule)
        rules = client.isolation.values(dll, 'NetworkAccess')
        if sorted(rules) != sorted([*before['NetworkAccess'], *AUTH_RULES]):
            raise RuntimeError('Authentication network policy mismatch')
        # 仅此处使用真实官方客户端；认证由用户在官方界面本人完成。
        launched = subprocess.Popen([str(client.isolation.SBIE / 'Start.exe'), '/box:PBZSteamLab', '/silent',
            r'E:\PBZSteamLabClient\steam.exe', '-tcp'], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        state.update({'watchdog_pid': watcher.pid, 'launcher_pid': launched.pid, 'authentication_network_enabled': True})
        save(path, state)
        print(json.dumps({'independent_client_launch_requested': True, 'deadline_at': deadline.isoformat(),
                          'pbz_and_formal_library_blocked': True, 'account_contents_recorded': False,
                          'watchdog_pid': watcher.pid, 'state_file': str(path)},ensure_ascii=False,indent=2))
    except Exception:
        path.with_suffix('.stop').touch()
        restore(path, 'Preparation setup failed')
        raise


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if len(sys.argv) == 3 and sys.argv[1] == '--watchdog':
        watchdog(Path(sys.argv[2])); return
    if len(sys.argv) == 2 and sys.argv[1] == '--open-window':
        current = None
        if LATEST.is_file():
            current = json.loads(Path(json.loads(LATEST.read_text(encoding='utf-8'))['state_file']).read_text(encoding='utf-8'))
        if not current or current.get('restored'):
            start()
        from show_research_steam import show
        result = show()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get('found_research_window'):
            raise RuntimeError('Client requested but visible window not found; inspect startup evidence')
        return
    if len(sys.argv) == 2 and sys.argv[1] == '--finish':
        path = Path(json.loads(LATEST.read_text(encoding='utf-8'))['state_file'])
        path.with_suffix('.stop').touch()
        for _ in range(15):
            value = json.loads(path.read_text(encoding='utf-8'))
            if value.get('restored'):
                print(json.dumps({'restored': True, 'remaining_box_pids': value.get('remaining_box_pids')},ensure_ascii=False)); return
            time.sleep(1)
        raise RuntimeError('Watchdog restore pending; inspect lease before continuing')
    if len(sys.argv) != 1:
        raise RuntimeError('Use no arguments to open, or --finish to close preparation')
    start()


if __name__ == '__main__':
    main()
