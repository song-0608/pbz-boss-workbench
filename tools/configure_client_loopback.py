"""用途：只为独立Steam/界面进程允许本机TCP，公网/LAN及UDP继续默认拒绝；先用同规则探针验收。"""
from pathlib import Path
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
import test_offline_client as client
from test_wfp_isolation import change

ROOT = Path(__file__).resolve().parent.parent
RULES = [f'{image},Allow;Address={address};Protocol=TCP' for image in ('steam.exe','steamwebhelper.exe') for address in ('127.0.0.1','::1')]
PROBES = [f'isolation-probe.exe,Allow;Address={address};Protocol=TCP' for address in ('127.0.0.1','::1')]


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    client.isolation.select_box('PBZSteamLab')
    dll = client.isolation.api()
    initial = client.isolation.check_policy(dll)
    if client.baseline.box_pids(dll):
        raise RuntimeError('Box occupied')
    if initial['AllowNetworkAccess'] != ['n'] or initial['NetworkEnableWFP'] != ['y']:
        raise RuntimeError('Inspect existing policy before changing it')
    if client.preflight.games_running():
        raise RuntimeError('PBZ running; preserve session')
    # 用途：本机TCP不是网络命名空间隔离；若主机Steam重新出现，不能继续实验。
    host = subprocess.run(['powershell.exe','-NoProfile','-Command',"@(Get-Process steam,steamwebhelper -ErrorAction SilentlyContinue).Count"],capture_output=True,timeout=10)
    if host.stdout.strip() != b'0':
        raise RuntimeError('Host Steam detected; no network policy change')
    report = {'time': datetime.now(timezone(timedelta(hours=8))).isoformat(), 'passed': False,
              'internet_allowed': False, 'lan_allowed': False, 'client_loopback_tcp_allowed': True,
              'loopback_is_not_network_namespace_isolation': True, 'game_launched': False}
    try:
        for rule in [*RULES, *PROBES]:
            change('append', 'PBZSteamLab', 'NetworkAccess', rule)
        # 此y只让WFP使用精确规则；*,Block仍拒绝所有不匹配的地址和协议，并非打开公网。
        change('set', 'PBZSteamLab', 'AllowNetworkAccess', 'y')
        client.isolation.check_policy(dll)
        tested = subprocess.run([sys.executable, str(ROOT / 'tools/test_isolation.py'), '--steam-lab'],capture_output=True,timeout=60)
        report['probe_exit'] = tested.returncode
        report['probe_report'] = json.loads((ROOT / 'evidence/isolation-probe/latest-result.json').read_text(encoding='utf-8'))
        if tested.returncode or not report['probe_report'].get('passed'):
            raise RuntimeError('Loopback policy verification failed')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
    finally:
        report['remaining_box_pids'] = client.cleanup(dll)
        # 用途：移除临时探针许可；实际环境仅Steam和steamwebhelper享有本机TCP例外。
        for rule in PROBES:
            change('delete', 'PBZSteamLab', 'NetworkAccess', rule)
        if not report['passed'] or report['remaining_box_pids']:
            change('set', 'PBZSteamLab', 'AllowNetworkAccess', 'n')
            for rule in RULES:
                change('delete', 'PBZSteamLab', 'NetworkAccess', rule)
            report['rolled_back'] = True
            report['passed'] = False
        report['final_policy'] = client.isolation.check_policy(dll)
        (ROOT / 'evidence/offline-steam/client-loopback-policy.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('probe_report','final_policy')},ensure_ascii=False,indent=2))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
