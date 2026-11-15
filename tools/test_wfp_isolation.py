"""用途：在WFP全断网策略下解除重复的AFD设备封锁；探针失败立即回滚，不启动游戏。"""
from pathlib import Path
import subprocess
import json
import sys
import time
from datetime import datetime, timezone, timedelta
import test_isolation as isolation
import run_sandbox_baseline as baseline

ROOT = Path(__file__).resolve().parent.parent


def change(operation, section, key, value):
    command = [str(isolation.SBIE / 'SbieIni.exe'), operation, section, key]
    if value is not None:
        command.append(value)
    result = subprocess.run(command, capture_output=True, timeout=15)
    if result.returncode:
        raise RuntimeError('Configuration operation failed: ' + operation + ' ' + key)


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    isolation.select_box('PBZSteamLab')
    dll = isolation.api()
    before = isolation.check_policy(dll)
    if baseline.box_pids(dll):
        raise RuntimeError('Dedicated box is occupied')
    if before['NetworkEnableWFP']:
        raise RuntimeError('Global WFP already configured; inspect before changing')
    work = ROOT / 'evidence/offline-steam' / datetime.now().strftime('%Y%m%d-%H%M%S-wfp')
    work.mkdir()
    (work / 'Sandboxie-before.ini').write_bytes(Path(r'C:\Windows\Sandboxie.ini').read_bytes())
    report = {'time': datetime.now(timezone(timedelta(hours=8))).isoformat(),
              'reason': 'Steam dump CommentStreamA: PlatformSocketsInit failed WSAEACCES 10013',
              'internet_allowed': False, 'loopback_allowed': False, 'game_launched': False,
              'global_wfp_before': before['NetworkEnableWFP'], 'probe_passed': False}
    try:
        # 用途：先启用内核连接过滤，核对后才解除AFD重复封锁；始终保留AllowNetworkAccess=n。
        change('set', 'GlobalSettings', 'NetworkEnableWFP', 'y')
        if isolation.values(dll, 'NetworkEnableWFP') != ['y']:
            raise RuntimeError('WFP setting did not reload')
        change('delete', isolation.BOX, 'ClosedFilePath', r'\Device\Afd*')
        report['effective_policy'] = isolation.check_policy(dll)
        probe = subprocess.run([sys.executable, str(ROOT / 'tools/test_isolation.py'), '--steam-lab'],
                               capture_output=True, timeout=60)
        report['probe_exit'] = probe.returncode
        (work / 'probe-stdout.txt').write_bytes(probe.stdout)
        (work / 'probe-stderr.txt').write_bytes(probe.stderr)
        if probe.returncode:
            raise RuntimeError('WFP isolation probe failed; restore device restrictions')
        result = json.loads((ROOT / 'evidence/isolation-probe/latest-result.json').read_text(encoding='utf-8'))
        report['probe_report'] = result
        report['probe_passed'] = True
    except Exception as error:
        report['error'] = str(error)
    finally:
        # 用途：清理本次从空箱启动的探针及箱内辅助服务，下一轮客户端测试需从空箱开始。
        subprocess.run([str(isolation.SBIE / 'Start.exe'), '/box:' + isolation.BOX, '/terminate'], capture_output=True, timeout=15)
        for _ in range(20):
            if not baseline.box_pids(dll):
                break
            time.sleep(.1)
        report['remaining_box_pids'] = baseline.box_pids(dll)
        if report['remaining_box_pids']:
            report['probe_passed'] = False
        if not report['probe_passed']:
            if baseline.box_pids(dll):
                subprocess.run([str(isolation.SBIE / 'Start.exe'), '/box:' + isolation.BOX, '/terminate'], capture_output=True, timeout=15)
            if r'\Device\Afd*' not in isolation.values(dll, 'ClosedFilePath'):
                change('append', isolation.BOX, 'ClosedFilePath', r'\Device\Afd*')
            change('set', 'GlobalSettings', 'NetworkEnableWFP', None)
            report['rolled_back'] = True
        (work / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        (ROOT / 'evidence/offline-steam/latest-wfp-test.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('effective_policy', 'probe_report')}, ensure_ascii=False, indent=2))
    return 0 if report['probe_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
