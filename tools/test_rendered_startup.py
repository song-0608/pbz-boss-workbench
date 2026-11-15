"""用途：隔离断网条件下实测原版窗口启动，读取目标窗口错误；不测试或注入Boss功能。"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json
import sys
import time
import hashlib

import test_isolation as iso
import run_sandbox_baseline as base
import test_offline_client as client
import preflight

ROOT=Path(__file__).resolve().parent.parent
EXPECTED={'steam/PBZ.exe':'17bf1e56c1a63f1dcde66d468b3f50fb308a8d29d2283ede7b275d953e47485d',
          'platform/steam/PBZ.exe':'4415933ce33476f14c837abb61a1b60af8b78cd81783896501913a7aac69e423'}


def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    if 'windowsapps' in sys.executable.casefold():raise RuntimeError('Use non-Store Python')
    iso.select_box('PBZSteamLab');dll=iso.api();policy=iso.check_policy(dll)
    if preflight.games_running() or base.box_pids(dll):raise RuntimeError('Existing game/session preserved; not launching')
    for relative,expected in EXPECTED.items():
        path=base.GAME/relative
        with path.open('rb') as f:current=hashlib.file_digest(f,'sha256').hexdigest()
        if current!=expected:raise RuntimeError('Game build changed; stop and audit')
    # 不能用未知已安装Mod的原版入口来判断适配错误。
    for directory in (base.GAME/'steam',base.GAME/'platform/steam'):
        for name in ('UE4SS.dll','UE4SS-settings.ini','dwmapi.dll','xinput1_3.dll'):
            if (directory/name).exists():raise RuntimeError('Unexpected loader in formal install: '+name)
    container=iso.get_root(dll);before=base.formal_files();host_before=client.registry_host()
    now=datetime.now(timezone(timedelta(hours=8)));work=ROOT/'evidence/rendered-startup'/now.strftime('%Y%m%d-%H%M%S');work.mkdir(parents=True)
    report={'time':now.isoformat(),'box':iso.BOX,'policy':policy,'rendered_window_start_requested':True,
            'nullrhi_requested':False,'ue4ss_deployed':False,'boss_script_enabled':False,'gameplay_verified':False,
            'formal_file_count_before':len(before),'host_steam_registry_before':host_before,'work':str(work)}
    try:
        report['start']=client.bootstrap('direct-game',work,container)
        print('Real PBZ native window startup requested inside offline sandbox; capturing only its window text.',flush=True)
        observations=[]
        for index in range(12):
            time.sleep(2)
            processes=client.box_processes(dll);windows=client.windows_for({p['ProcessId'] for p in processes})
            observations.append({'elapsed_seconds':(index+1)*2,'processes':processes,'windows':windows})
            messages=' '.join(row['title']+' '+' '.join(row['children']) for row in windows)
            if any(token in messages for token in ('加载 SteamAPI 失败','加载SteamAPI失败','SteamAPI','致命错误','Fatal Error')):
                report['observed_blocker_text']=messages;break
            if not any(p.get('Name','').casefold()=='pbz.exe' for p in processes) and index>=2:break
        report['observations']=observations
        # 只根据窗口出现不能宣称进入主菜单、已加载存档或可以操控Boss。
        report['game_process_observed']=any(any(p.get('Name','').casefold()=='pbz.exe' for p in row['processes']) for row in observations)
    finally:
        report['remaining_box_pids']=client.cleanup(dll)
        after=base.formal_files();report['formal_file_count_after']=len(after)
        report['formal_files_changed']=[name for name in sorted(set(before)|set(after)) if before.get(name)!=after.get(name)]
        report['host_steam_registry_after']=client.registry_host();report['host_steam_registry_unchanged']=host_before==report['host_steam_registry_after']
        report['original_backup_compare']=preflight.compare(ROOT/'evidence/latest-preflight.json')
        report['remaining_pbz_processes']=preflight.games_running()
        (work/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        (ROOT/'evidence/rendered-startup/latest-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    compact={k:v for k,v in report.items() if k not in ('policy','observations')}
    compact['last_windows']=[win for row in report.get('observations',[])[-1:] for win in row['windows']]
    print(json.dumps(compact,ensure_ascii=False,indent=2))
    # 没捕获到错误文字不等于启动成功；没有菜单/玩法证据就不返回“实测通过”。
    return 0 if report.get('gameplay_verified') is True and not report['formal_files_changed'] and not report['remaining_box_pids'] else 2


if __name__=='__main__':raise SystemExit(main())
