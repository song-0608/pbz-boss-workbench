"""用途：将真实准备结果写入工作台状态；不把客户端登录界面冒充游戏或Boss实测。"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import sys
from research_storage import container_path

ROOT = Path(__file__).resolve().parent.parent


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    lease = json.loads((ROOT / 'runtime/latest-login-preparation.json').read_text(encoding='utf-8'))
    current = json.loads(Path(lease['state_file']).read_text(encoding='utf-8'))
    path = ROOT / '项目状态.json'
    status = json.loads(path.read_text(encoding='utf-8'))
    now = datetime.now(timezone(timedelta(hours=8))).isoformat()
    summary = '独立Steam官方更新及登录界面已跑通；按用户授权限时开放本人认证，PBZ和正式游戏库仍被封锁。'
    status.update({'updated_at': now, 'status_summary': summary,
        'blocked_reason': '等待用户在独立官方客户端本人登录并切为离线；还需验证离线会话、原版菜单和游戏真实存档隔离，不能操控Boss。',
        'awaiting_user': '本人完成独立Steam登录，在Steam菜单选择进入离线模式，回复“已切离线”。',
        'user_exit_completion_received': True, 'client_update_preparation_authorized': True,
        'client_authentication_preparation_authorized': True, 'authentication_preparation_active': not current['restored'],
        'authentication_preparation_state': lease['state_file'], 'authentication_preparation_deadline': current['deadline_at'],
        'authentication_watchdog_pid': current.get('watchdog_pid'), 'prepared_steam_client_version': '1794424036',
        'game_initialization_verified': False, 'boss_control_verified': False, 'real_bridge_available': False,
        'no_loader_deployment': True, 'current_authentication_stage_game_launched': False,
        'sandboxie_global_wfp_enabled': True, 'client_offline_network_mode': 'Steam/steamwebhelper localhost TCP only; other network default-deny; auth exceptions are leased separately',
        'experimental_client_copy': str(container_path() / 'drive/E/PBZSteamLabClient'),
        'client_virtual_english_entry': r'E:\PBZSteamLabClient',
        'latest_client_test': str(ROOT / 'evidence/offline-steam/latest-client-result.json'),
        'latest_client_loopback_probe': str(ROOT / 'evidence/offline-steam/client-loopback-policy.json'),
        'latest_official_client_install': str(ROOT / 'evidence/offline-steam/official-client-install.json')})
    status.pop('client_ascii_junction', None)
    additions = ['退出主机Steam后的对照实验完成，不再等待退出通知',
        '从转储明确定位AFD套接字初始化被拒，并验证WFP连接层阻断方案',
        '英文箱内安装入口替代中文实体路径联接，客户端文件仍集中在D盘',
        '18个当前官方更新包校验、6631个客户端文件统一安装，官方客户端完成安装验证',
        '仅客户端本机TCP规则探针通过，独立客户端正常显示登录Steam',
        '已获本人认证联网授权；正式库/PBZ封锁、10分钟看门狗及紧急结束入口已准备']
    for item in additions:
        if item not in status['completed']:
            status['completed'].append(item)
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    profile_path = ROOT.parent / 'profiles/pbz-offline.json'
    profile = json.loads(profile_path.read_text(encoding='utf-8'))
    profile.update({'status': 'official-client-updated-awaiting-user-offline-login',
        'note': summary + '登录界面不是游戏菜单；Boss桥接仍未实现。',
        'user_exit_completion_received': True, 'client_authentication_preparation_authorized': True,
        'authentication_preparation_active': not current['restored'], 'authentication_preparation_state': lease['state_file'],
        'authentication_preparation_deadline': current['deadline_at'], 'runtime_launch_allowed': False,
        'boss_control_verified': False, 'real_bridge_available': False})
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'state_updated': True, 'current_stage': summary, 'deadline': current['deadline_at'],
                      'real_game_or_boss_success_claimed': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
