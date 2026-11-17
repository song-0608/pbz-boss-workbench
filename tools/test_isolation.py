"""用途：用临时哨兵验证专用沙盒；不启动PBZ、不写正式存档、不修改主机网络。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid
import winreg

ROOT = Path(__file__).resolve().parent.parent
BOX = "PBZBossLab"
SBIE = Path(r"E:\Sandboxie-Plus")


def select_box(name):
    """用途：只允许两个明确的研究箱；不接受任意名称或用户原有箱。"""
    global BOX
    if name not in ('PBZBossLab','PBZSteamLab'):
        raise RuntimeError('Unknown research box')
    BOX=name


def api():
    """用途：使用官方Unicode驱动查询，避免SbieIni控制台显示中文截断导致误判。"""
    dll = ctypes.WinDLL(str(SBIE / "SbieDll.dll"))
    dll.SbieApi_QueryConf.argtypes = [w.LPCWSTR, w.LPCWSTR, w.ULONG, w.LPWSTR, w.ULONG]
    dll.SbieApi_QueryConf.restype = w.LONG
    dll.SbieApi_QueryBoxPath.argtypes = [w.LPCWSTR, w.LPWSTR, w.LPWSTR, w.LPWSTR,
                                       ctypes.POINTER(w.ULONG), ctypes.POINTER(w.ULONG), ctypes.POINTER(w.ULONG)]
    dll.SbieApi_QueryBoxPath.restype = w.LONG
    return dll


def values(dll, key):
    result = []
    for index in range(256):
        buf = ctypes.create_unicode_buffer(8192)
        if dll.SbieApi_QueryConf(BOX, key, index, buf, ctypes.sizeof(buf)) != 0:
            break
        result.append(buf.value)
    return result


def get_root(dll):
    """用途：取得驱动实际使用的文件容器；允许D盘初测或已记录的E盘NTFS专用容器。"""
    buffers = [ctypes.create_unicode_buffer(4096) for _ in range(3)]
    sizes = [w.ULONG(ctypes.sizeof(buf)) for buf in buffers]
    status = dll.SbieApi_QueryBoxPath(BOX, *buffers, *[ctypes.byref(size) for size in sizes])
    if status != 0:
        raise RuntimeError(f"Cannot query box root: {status}")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.QueryDosDeviceW.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD]
    kernel.QueryDosDeviceW.restype = w.DWORD
    for drive in ("D:", "E:"):
        name = ctypes.create_unicode_buffer(4096)
        if kernel.QueryDosDeviceW(drive, name, len(name)):
            if buffers[0].value.casefold().startswith(name.value.casefold() + "\\"):
                path = Path(drive + buffers[0].value[len(name.value):])
                from research_storage import container_path
                allowed = [container_path(BOX,root=ROOT)]
                if BOX=='PBZBossLab':allowed.extend([ROOT / "sandbox" / "PBZBossLabDriveLayout", SBIE / "PBZBossLabRoot"])
                if any(str(path).casefold() == str(candidate).casefold() for candidate in allowed):
                    return path
    raise RuntimeError("Unexpected sandbox file root; refusing tests")


def check_policy(dll, allow_eula_web=False, allow_official_validation=False, allow_auth_preparation=False,allow_official_client_preparation=False,allow_offline_validation=False):
    """用途：核对当前专用箱策略，任何直接放行文件/Steam通信的例外都停止测试。"""
    policy = {key: values(dll, key) for key in ["Enabled", "AutoRecover", "AutoDelete", "NeverDelete",
             "DropAdminRights", "AllowNetworkAccess", "NetworkAccess", "ClosedFilePath", "ClosedIpcPath",
             "OpenFilePath", "OpenPipePath", "OpenIpcPath", "NormalIpcPath", "NormalFilePath", "BreakoutProcess", "BreakoutFolder", "NetworkEnableWFP"]}
    # 用途：令牌兼容实验必须属于有独立回收看门狗的有效租期；拒绝绕过整套安全隔离。
    for key in ('NoSecurityIsolation','UnfilteredToken','KeepTokenIntegrity'):
        if values(dll,key) not in ([],['n']):raise RuntimeError('Unexpected isolation relaxation: '+key)
    for key in ('NoUntrustedToken','UnstrippedToken','UnrestrictedToken'):
        actual=values(dll,key)
        if actual in ([],['n']):continue
        lease=ROOT/'runtime/latest-official-validation.json'
        if BOX!='PBZSteamLab' or actual!=['y'] or not lease.is_file():
            raise RuntimeError('Unexpected token policy: '+key)
        state=json.loads(Path(json.loads(lease.read_text(encoding='utf-8'))['state_file']).read_text(encoding='utf-8'))
        if (state.get('restored') or time.time()>=state['deadline_unix'] or not state.get('compatibility_setting_applied')
                or state.get('compatibility_setting')!=key):
            raise RuntimeError('Token experiment has no valid recovery lease')
    local_rules = [f'{image},Allow;Address={address};Protocol=TCP' for image in ('steam.exe','steamwebhelper.exe') for address in ('127.0.0.1','::1')]
    probe_rules = [f'isolation-probe.exe,Allow;Address={address};Protocol=TCP' for address in ('127.0.0.1','::1')]
    local_mode = BOX == 'PBZSteamLab' and policy['NetworkEnableWFP'] == ['y'] and policy['AllowNetworkAccess'] == ['y']
    allowed_sets = [sorted(['*,Block', *local_rules]), sorted(['*,Block', *local_rules, *probe_rules])]
    local_saved_virtualized=False
    if allow_offline_validation:
        # 用途：离线复测允许同一租期已验证的文件副本机制，但不允许任何公网规则。
        lease=ROOT/'runtime/latest-official-validation.json'
        state=json.loads(Path(json.loads(lease.read_text(encoding='utf-8'))['state_file']).read_text(encoding='utf-8'))
        if (BOX!='PBZSteamLab' or not local_mode or state.get('restored') or time.time()>=state['deadline_unix']
                or not state.get('offline_validation') or state.get('network_active') or state.get('client_network_preparation')):
            raise RuntimeError('No active strictly offline validation lease')
        if sorted(policy['NetworkAccess'])!=sorted(['*,Block',*local_rules]):
            raise RuntimeError('Offline validation has unexpected network permissions')
        local_saved_virtualized=bool(state.get('local_saved_virtualization') and state.get('local_saved_probe_passed'))
    if allow_eula_web:
        # 用途：仅截图已获授权的协议准备窗口；严格核对有效租期及PBZ独立封锁。
        lease=ROOT/'runtime/latest-eula-preparation.json'
        state_path=Path(json.loads(lease.read_text(encoding='utf-8'))['state_file'])
        state=json.loads(state_path.read_text(encoding='utf-8'))
        if BOX!='PBZSteamLab' or not local_mode or state.get('restored') or time.time()>=state['deadline_unix']:
            raise RuntimeError('No active EULA web preparation lease')
        if r'*\PBZ.exe' not in policy['ClosedFilePath']:
            raise RuntimeError('Independent PBZ executable deny missing')
        web_rules=[f'{image},Allow;Port=80,443;Protocol=TCP' for image in ('steam.exe','steamwebhelper.exe')]
        allowed_sets.append(sorted(['*,Block',*local_rules,*web_rules]))
    if allow_auth_preparation:
        # 用途：只观察已有本人认证授权的独立客户端菜单；PBZ和正式库仍封锁。
        lease=ROOT/'runtime/latest-login-preparation.json'
        auth_path=Path(json.loads(lease.read_text(encoding='utf-8'))['state_file'])
        auth=json.loads(auth_path.read_text(encoding='utf-8'))
        model=json.loads((ROOT/'项目状态.json').read_text(encoding='utf-8'))
        if (BOX!='PBZSteamLab' or not local_mode or auth.get('restored')
                or time.time()>=auth['deadline_unix'] or not auth.get('authentication_network_enabled')
                or not model.get('client_authentication_preparation_authorized')):
            raise RuntimeError('No active authorized client authentication lease')
        for suffix in (r'\steamlibrary\*',r'\steamapps\common\pbz\*'):
            if not any(v.casefold().endswith(suffix) for v in policy['ClosedFilePath']):
                raise RuntimeError('Authentication game/library block missing')
        auth_rules=['steam.exe,Allow;Port=80,443,27014-27050;Protocol=TCP',
                    'steamwebhelper.exe,Allow;Port=80,443;Protocol=TCP']
        allowed_sets.append(sorted(['*,Block',*local_rules,*auth_rules]))
    if allow_official_client_preparation:
        lease=ROOT/'runtime/latest-official-validation.json'
        path=Path(json.loads(lease.read_text(encoding='utf-8'))['state_file'])
        state=json.loads(path.read_text(encoding='utf-8'))
        model=json.loads((ROOT/'项目状态.json').read_text(encoding='utf-8'))
        if (BOX!='PBZSteamLab' or not local_mode or state.get('restored') or time.time()>=state['deadline_unix']
                or not state.get('client_network_preparation') or state.get('game_stage') or state.get('network_active')
                or not model.get('client_authentication_preparation_authorized') or not model.get('game_online_validation_authorized')):
            raise RuntimeError('No active authorized client-only validation preparation')
        allowed_sets.append(sorted(['*,Block',*local_rules,
            'steam.exe,Allow;Port=80,443,27014-27050;Protocol=TCP',
            'steamwebhelper.exe,Allow;Port=80,443;Protocol=TCP']))
        local_saved_virtualized=bool(state.get('local_saved_virtualization') and state.get('local_saved_probe_passed'))
    if allow_official_validation:
        # 用途：只接受本人已授权、未过期且云关闭已验收的原版验证租期，用于观察窗口。
        lease=ROOT/'runtime/latest-official-validation.json'
        state_path=Path(json.loads(lease.read_text(encoding='utf-8'))['state_file'])
        state=json.loads(state_path.read_text(encoding='utf-8'))
        model=json.loads((ROOT/'项目状态.json').read_text(encoding='utf-8'))
        if (BOX!='PBZSteamLab' or not local_mode or state.get('restored')
                or time.time()>=state['deadline_unix'] or not state.get('network_active')
                or not state.get('game_stage') or not state.get('cloud_verified')
                or not model.get('game_online_validation_authorized')):
            raise RuntimeError('No active authorized official validation lease')
        gate=Path(state['work'])/'cloud-gate.json'
        if not json.loads(gate.read_text(encoding='utf-8')).get('ui_off_verified'):
            raise RuntimeError('Current session cloud OFF evidence missing')
        online_rules=['steam.exe,Allow;Port=80,443,27014-27050;Protocol=TCP',
                      'steamwebhelper.exe,Allow;Port=80,443;Protocol=TCP',
                      'PBZ.exe,Allow;Port=80,443;Protocol=TCP',
                      'PBZ.exe,Allow;Address=127.0.0.1;Port=7890;Protocol=TCP']
        allowed_sets.append(sorted(['*,Block',*local_rules,*online_rules]))
        local_saved_virtualized=bool(state.get('local_saved_virtualization') and state.get('local_saved_probe_passed'))
    if local_mode and sorted(policy['NetworkAccess']) not in allowed_sets:
        raise RuntimeError('Unexpected loopback rules; no launch')
    for key, expected in {"Enabled": "y", "AutoRecover": "n", "AutoDelete": "n", "NeverDelete": "y",
                          "DropAdminRights": "y", "AllowNetworkAccess": "y" if local_mode else "n"}.items():
        if policy[key] != [expected]:
            raise RuntimeError(f"Unsafe policy {key}: {policy[key]}")
    if not local_mode and policy["NetworkAccess"] != ["*,Block"]:
        raise RuntimeError("Missing blanket network rule")
    # 驱动可能把DOS路径扩展成NT路径，因此设备规则按精确字符串、Steam目录按末尾核对。
    required_devices=[r"\Device\RawIp", r"\Device\Ip*", r"\Device\Tcp*"]
    # 用途：Steam需要建立套接字；WFP模式在连接层断网，仍禁止所有连接含本机回环。
    # 只在明确的专用客户端箱和全局WFP开关已启用时接受此模式，其他箱继续封锁AFD。
    if BOX != 'PBZSteamLab' or policy['NetworkEnableWFP'] != ['y']:
        required_devices.append(r"\Device\Afd*")
    if BOX=='PBZBossLab':required_devices.append(r"\Device\NamedPipe\*steam*")
    for rule in required_devices:
        if rule not in policy["ClosedFilePath"]:
            raise RuntimeError(f"Missing kernel file rule: {rule}")
    if BOX=='PBZBossLab':
        if policy["ClosedIpcPath"] != ["*steam*"]:
            raise RuntimeError("Steam IPC deny rule missing")
    else:
        # Normal恢复虚拟化，并非Open/允许访问主机；必须通过主机阴性与箱内阳性通信测试。
        if policy['ClosedIpcPath'] or policy['NormalIpcPath'] != ['*steam*']:
            raise RuntimeError('Unexpected independent-client IPC policy')
        if r'\Device\NamedPipe\*steam*' not in policy['NormalFilePath']:
            raise RuntimeError('Missing virtualized pipe policy')
    for suffix in (r"\steam\*", r"\AppData\Local\ProjectPBZ\*", r"\AppData\Local\PBZBossLabProbe\*"):
        if local_saved_virtualized and suffix.casefold()==r'\appdata\local\projectpbz\*':
            # 用途：仅当前有效验证租期、且已用标记/原件哈希验收的默认虚拟化模式；其余保护不变。
            continue
        if not any(rule.casefold().endswith(suffix.casefold()) for rule in policy["ClosedFilePath"]):
            raise RuntimeError(f"Missing protected host path rule: {suffix}")
    if values(dll,"SeparateUserFolders") != ["n"]:
        raise RuntimeError("Unexpected user-folder mapping")
    for key in ("OpenFilePath", "OpenPipePath", "BreakoutProcess", "BreakoutFolder"):
        if policy[key]:
            raise RuntimeError(f"Direct host exception in {key}")
    if any("steam" in rule.casefold() for rule in policy["OpenIpcPath"]):
        raise RuntimeError("Host Steam IPC exception present")
    return policy


def virtual_file(container, logical):
    """用途：定位测试报告的D盘镜像；不向此处导出或恢复正式存档。"""
    return container / "drive" / logical.drive[0] / str(logical)[3:]


def registry_value_exists(name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\PBZBossLabProbe") as key:
            winreg.QueryValueEx(key, name)
            return True
    except FileNotFoundError:
        return False


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    dll = api()
    policy = check_policy(dll)
    container = get_root(dll)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    work = ROOT / "evidence" / "isolation-probe" / run_id
    work.mkdir(parents=True)
    # 三个测试盘符都使用本次新建目录，不借用游戏或用户已有文件。
    native_e = Path(r"E:\PBZBossLabProbe") / run_id
    native_c = Path(os.environ["USERPROFILE"]) / "PBZBossLabProbe" / run_id
    native_e.mkdir(parents=True); native_c.mkdir(parents=True)
    sentinels = [work / "host-D.txt", native_e / "host-E.txt", native_c / "host-C.txt"]
    blocked_dir = Path(os.environ["LOCALAPPDATA"]) / "PBZBossLabProbe" / run_id
    blocked_dir.mkdir(parents=True)
    blocked_sentinel = blocked_dir / "denied.txt"
    sentinels.append(blocked_sentinel)
    for path in sentinels:
        path.write_bytes(("HOST_UNCHANGED_" + run_id).encode("ascii"))
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sentinels}
    for path in sentinels:
        observation = subprocess.run([str(ROOT / "build" / "isolation-probe" / "isolation-probe.exe"),
                                      "--observe", str(path)], capture_output=True, timeout=10)
        if observation.returncode:
            raise RuntimeError(f"Host native process cannot read sentinel {path}: {observation.stdout!r}")
    if registry_value_exists(run_id):
        raise RuntimeError("Registry marker unexpectedly preexists")
    report_path = work / "probe-report.json"
    pipe_name = r"\\.\pipe\Steam_PBZBossLabProbe_" + run_id
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateNamedPipeW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.LPVOID]
    kernel.CreateNamedPipeW.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    pipe = kernel.CreateNamedPipeW(pipe_name, 0x40000003, 0, 1, 4096, 4096, 0, None)
    if pipe == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    sockets = []
    report = {"time": datetime.now().astimezone().isoformat(), "run_id": run_id, "box": BOX,
              "container": str(container), "policy": policy, "host_files_before": before,
              "game_launched": False, "passed": False}
    try:
        ports = []
        for family, kind, address in [(socket.AF_INET, socket.SOCK_STREAM, "127.0.0.1"),
                                      (socket.AF_INET6, socket.SOCK_STREAM, "::1"),
                                      (socket.AF_INET, socket.SOCK_DGRAM, "127.0.0.1")]:
            sock = socket.socket(family, kind); sock.bind((address, 0))
            if kind == socket.SOCK_STREAM:
                sock.listen(4)
                # 用主机自连接证实接收端确实可达，避免把不存在的服务当作沙盒阻断。
                client = socket.socket(family, kind); client.settimeout(1)
                client.connect((address, sock.getsockname()[1])); accepted, _ = sock.accept()
                client.close(); accepted.close()
            else:
                # 用途：先证明UDP接收端可以接收主机发送的数据，再测试箱内发送是否实际被丢弃。
                sender = socket.socket(family, kind); sock.settimeout(1)
                sender.sendto(b'host-positive-control', sock.getsockname())
                payload, _ = sock.recvfrom(1024); sender.close()
                if payload != b'host-positive-control':
                    raise RuntimeError('UDP positive control failed')
            sock.setblocking(False); sockets.append(sock); ports.append(sock.getsockname()[1])
        command = [str(SBIE / "Start.exe"), "/box:" + BOX, "/silent", "/hide_window", "/wait",
                   str(ROOT / "build" / "isolation-probe" / "isolation-probe.exe"), BOX,
                   str(report_path), *map(str, sentinels[:3]), *map(str, ports), pipe_name, run_id, str(blocked_sentinel)]
        probe_loopback = 'isolation-probe.exe,Allow;Address=127.0.0.1;Protocol=TCP' in policy['NetworkAccess']
        if probe_loopback:
            command.append('--local-tcp')
        # 用途：只运行刚编译的测试程序；严格60秒超时，不调用任何PBZ程序。
        result = subprocess.run(command, capture_output=True, timeout=60)
        # 用途：给内核异步UDP投递留出时间；sendto返回成功不代表数据已经抵达。
        time.sleep(1)
        report["launcher_exit_code"] = result.returncode
        report["launcher_stdout"] = result.stdout.decode("utf-8", errors="replace")
        report["launcher_stderr"] = result.stderr.decode("utf-8", errors="replace")
        physical_report = virtual_file(container, report_path)
        if physical_report.is_file():
            report["probe"] = json.loads(physical_report.read_text(encoding="utf-8"))
        else:
            report["error"] = "No virtualized report; launch is unproven"
        report["host_files_unchanged"] = all(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == before[str(path)] for path in sentinels)
        report["host_registry_unchanged"] = not registry_value_exists(run_id)
        received = []
        for sock in sockets:
            try:
                if sock.type == socket.SOCK_STREAM:
                    connection, addr = sock.accept(); connection.close(); received.append({'protocol': 'TCP', 'peer': str(addr)})
                else:
                    data, addr = sock.recvfrom(1024); received.append({'protocol': 'UDP', 'peer': str(addr)})
            except BlockingIOError:
                pass
        report["host_listeners_received"] = received
        # 逐个镜像核对实际数据，不能只相信测试程序输出或Start.exe退出码。
        mirrors = []
        for path in sentinels[:3]:
            # C盘用户路径由默认SeparateUserFolders映射到user/current。
            if path.drive.casefold() == "c:" and values(dll, "SeparateUserFolders") != ["n"]:
                relative = path.relative_to(Path(os.environ["USERPROFILE"]))
                mirror = container / "user" / "current" / relative
            else:
                mirror = virtual_file(container, path)
            mirrors.append({"path": str(mirror), "changed_only_in_box": mirror.is_file() and mirror.read_bytes() == b"SANDBOX_CHANGED_ONLY"})
        report["file_mirrors"] = mirrors
        probe = report.get("probe", {})
        wfp_mode = policy['NetworkEnableWFP'] == ['y'] and r'\Device\Afd*' not in policy['ClosedFilePath']
        udp_blocked = probe.get('udp_error') == 10013 or (wfp_mode and probe.get('udp_error') == 0 and not any(row['protocol']=='UDP' for row in received))
        local_expected = 0 if probe_loopback else 10013
        receive_expected = len(received)==2 and all(row['protocol']=='TCP' for row in received) if probe_loopback else not received
        report['probe_loopback_tcp_allowed'] = probe_loopback
        report['udp_positive_control_passed'] = True
        report['udp_blocking_evidence'] = 'Host UDP listener receives host control; receives no sandbox datagram after one-second wait. WFP may drop after successful sendto.'
        report["passed"] = (result.returncode == 0 and probe.get("sandbox_verified") is True
                            and all(probe.get(key) is True for key in ("file_d", "file_e", "file_c", "registry"))
                            and all(probe.get(key) == local_expected for key in ("tcp4_error", "tcp6_error"))
                            and probe.get('external_error') == 10013 and udp_blocked
                            and probe.get("pipe_error") in (2, 5) and probe.get("appdata_deny_error") == 5
                            and (BOX!='PBZSteamLab' or probe.get('internal_pipe_ok') is True)
                            and report["host_files_unchanged"] and report["host_registry_unchanged"]
                            and receive_expected and all(row["changed_only_in_box"] for row in mirrors))
    except subprocess.TimeoutExpired:
        report["error"] = "Probe launch timeout; isolation NOT verified"
    finally:
        for sock in sockets:
            sock.close()
        kernel.CloseHandle(pipe)
        # 只删除本次创建且内容未变的C/E测试哨兵，不递归删除任何目录。
        for path in sentinels[1:]:
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == before[str(path)]:
                path.unlink()
                path.parent.rmdir()
        (work / "host-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (ROOT / "evidence" / "isolation-probe" / "latest-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    # 用途：微软商店版Python可能对AppData另行重定向，转到本机已存在的普通运行时。
    if "windowsapps" in sys.executable.casefold():
        python = Path(os.environ["USERPROFILE"]) / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
        if not python.is_file():
            raise SystemExit("Run this test with a non-Store Python interpreter")
        raise SystemExit(subprocess.call([str(python), str(Path(__file__).resolve()), *sys.argv[1:]]))
    if len(sys.argv)==2 and sys.argv[1]=='--steam-lab':select_box('PBZSteamLab')
    elif len(sys.argv)!=1:raise SystemExit('Usage: test_isolation.py [--steam-lab]')
    raise SystemExit(main())
