"""用途：在原有隔离策略下记录Steam启动模块/异常，不启动游戏、不改Steam文件。"""
from datetime import datetime, timezone, timedelta
import json
import sys
import test_offline_client as client


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    client.isolation.select_box('PBZSteamLab')
    dll = client.isolation.api()
    policy = client.isolation.check_policy(dll)
    if client.baseline.box_pids(dll) or client.preflight.games_running():
        raise RuntimeError('Box or PBZ already running; preserve session')
    container = client.isolation.get_root(dll)
    work = client.ROOT / 'evidence/offline-steam' / datetime.now().strftime('%Y%m%d-%H%M%S-trace')
    work.mkdir()
    formal_before = client.baseline.formal_files()
    host_before = client.registry_host()
    report = {'time': datetime.now(timezone(timedelta(hours=8))).isoformat(), 'policy': policy,
              'network_allowed': False, 'host_steam_contact_allowed': False,
              'game_launched': False, 'debugger_changes_timing': True}
    try:
        report['trace'] = client.bootstrap('trace-client', work, container)
        report['processes'] = client.box_processes(dll)
    finally:
        report['remaining_box_pids'] = client.cleanup(dll)
        after = client.baseline.formal_files()
        report['formal_files_changed'] = [p for p in sorted(set(formal_before) | set(after)) if formal_before.get(p) != after.get(p)]
        report['host_steam_registry_unchanged'] = client.registry_host() == host_before
        report['original_backup_compare'] = client.preflight.compare(client.ROOT / 'evidence/latest-preflight.json')
        (work / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        (client.ROOT / 'evidence/offline-steam/latest-trace-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'policy'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
