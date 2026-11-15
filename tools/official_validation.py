"""用途：经本人授权，限时运行原版官方验证；关闭研究云同步后才联网，到期自动撤销。"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,sys,time,subprocess,hashlib,shutil,os
import test_offline_client as c
from test_wfp_isolation import change
from prepare_manual_login import save
from test_rendered_startup import EXPECTED

ROOT=Path(__file__).resolve().parent.parent
LATEST=ROOT/'runtime/latest-official-validation.json'
EXE_DENY=r'*\PBZ.exe'
LIB_DENY=r'E:\SteamLibrary\*'
GAME_DENY=str(c.baseline.GAME)+r'\*'
LOCAL_SAVED_DENY=str(Path(os.environ['LOCALAPPDATA'])/'ProjectPBZ')+r'\*'
# 用途：单变量兼容性对照，只禁止研究箱 PBZ 读取 Steam 叠加层 DLL；不触碰游戏或认证模块。
STEAM_OVERLAY_DENY=r'PBZ.exe,*\gameoverlayrenderer64.dll'
NVIDIA_OVERLAY_DENIES=[r'PBZ.exe,*\nvspcap64.dll',r'PBZ.exe,*\nvppex.dll']
TOKEN_COMPATIBILITY_KEYS=('NoUntrustedToken','UnstrippedToken','UnrestrictedToken')
ONLINE_RULES=['steam.exe,Allow;Port=80,443,27014-27050;Protocol=TCP',
              'steamwebhelper.exe,Allow;Port=80,443;Protocol=TCP',
              'PBZ.exe,Allow;Port=80,443;Protocol=TCP',
              # 用途：本机既有系统代理使用127.0.0.1:7890；仅本研究PBZ允许接入，不修改系统代理。
              'PBZ.exe,Allow;Address=127.0.0.1;Port=7890;Protocol=TCP']


def utc8():return datetime.now(timezone(timedelta(hours=8))).isoformat()


def state_path():return Path(json.loads(LATEST.read_text(encoding='utf-8'))['state_file'])


def update(state):
    """用途：同步项目状态，区分已授权、联网中、实际菜单验收。"""
    for path in (ROOT/'项目状态.json',ROOT.parent/'profiles/pbz-offline.json'):
        data=json.loads(path.read_text(encoding='utf-8'))
        data.update({'game_online_validation_authorized':True,
                     'official_validation_active':not state['restored'],
                     'official_validation_network_active':not state['restored'] and state.get('network_active',False),
                     'official_client_preparation_network_active':not state['restored'] and state.get('client_network_preparation',False) and not state.get('game_stage'),
                     'official_validation_state':state['state_file'],
                     'research_cloud_disabled_verified':True,
                     'official_validation_deadline':state['deadline_at']})
        save(path,data)


def verify_build(loader_manifest=None):
    """用途：只接受已经核对的两个原版EXE；正式和虚拟游戏目录都不能有UE4SS加载器。"""
    c.isolation.select_box('PBZSteamLab');dll=c.isolation.api();container=c.isolation.get_root(dll)
    for relative,expected in EXPECTED.items():
        with (c.baseline.GAME/relative).open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=expected:
                raise RuntimeError('Game executable changed; stop')
    allowed={row['physical_path']:row['sha256'] for row in (loader_manifest or [])}
    for directory in (c.baseline.GAME/'steam',c.baseline.GAME/'platform/steam'):
        for is_virtual,location in ((False,directory),(True,c.isolation.virtual_file(container,directory))):
            for name in ('UE4SS.dll','UE4SS-settings.ini','dwmapi.dll','xinput1_3.dll','ue4ss/UE4SS.dll','ue4ss/UE4SS-settings.ini'):
                marker=location/name
                if not marker.is_file():continue
                if not is_virtual or str(marker) not in allowed:
                    raise RuntimeError('Unexpected loader: '+str(marker))
                if hashlib.sha256(marker.read_bytes()).hexdigest()!=allowed[str(marker)]:
                    raise RuntimeError('Declared research loader hash changed')


def restore(path,reason):
    from validation_cleanup_lock import cleanup_lock
    with cleanup_lock(path):
        return _restore_unlocked(path,reason)


def _restore_unlocked(path,reason):
    """用途：先断本研究箱网络，再清理并恢复原规则；不回写任何正式存档。"""
    s=json.loads(path.read_text(encoding='utf-8'))
    if s['restored']:return s
    c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    change('set','PBZSteamLab','AllowNetworkAccess','n')
    for rule in ONLINE_RULES:
        if rule in c.isolation.values(dll,'NetworkAccess'):
            change('delete','PBZSteamLab','NetworkAccess',rule)
    remaining=c.cleanup(dll)
    if s.get('ue4ss_deployed'):
        if remaining:raise RuntimeError('Do not remove research loader while box processes remain')
        from pbz_ue4ss_baseline import remove_declared_loader
        remove_declared_loader(s,dll)
        s['research_loader_removed']=True
    if s.get('compatibility_setting_applied'):
        key=s['compatibility_setting']
        if key not in TOKEN_COMPATIBILITY_KEYS:raise RuntimeError('Unexpected compatibility key during restore')
        # 用途：set省略值才是删除整项；delete必须提供要匹配的具体值。
        change('set','PBZSteamLab',key,None)
        for value in s['compatibility_setting_prior']:change('append','PBZSteamLab',key,value)
        s['compatibility_setting_restored']=c.isolation.values(dll,key)==s['compatibility_setting_prior']
        if not s['compatibility_setting_restored']:raise RuntimeError('Compatibility setting restore failed')
    for rule in s.get('nvidia_overlay_rules_added',[]):
        if rule in c.isolation.values(dll,'ClosedFilePath'):
            change('delete','PBZSteamLab','ClosedFilePath',rule)
    if s.get('nvidia_overlay_rules_added'):
        s['nvidia_overlay_blocks_restored']=all(rule not in c.isolation.values(dll,'ClosedFilePath') for rule in s['nvidia_overlay_rules_added'])
        if not s['nvidia_overlay_blocks_restored']:raise RuntimeError('NVIDIA overlay experiment rules not removed')
    if s.get('steam_overlay_block_added'):
        if STEAM_OVERLAY_DENY in c.isolation.values(dll,'ClosedFilePath'):
            change('delete','PBZSteamLab','ClosedFilePath',STEAM_OVERLAY_DENY)
        s['steam_overlay_block_restored']=STEAM_OVERLAY_DENY not in c.isolation.values(dll,'ClosedFilePath')
        if not s['steam_overlay_block_restored']:raise RuntimeError('Overlay experiment rule not removed')
    if s.get('local_saved_rule_removed'):
        suffix=r'\appdata\local\projectpbz\*'
        count=sum(v.casefold().endswith(suffix) for v in c.isolation.values(dll,'ClosedFilePath'))
        for _ in range(s['original_local_saved_rule_count']-count):
            change('append','PBZSteamLab','ClosedFilePath',LOCAL_SAVED_DENY)
    for suffix,rule,target in ((r'\steamlibrary\*',LIB_DENY,s.get('original_library_count',s.get('library_removed',0))),
                               (r'\steamapps\common\pbz\*',GAME_DENY,s.get('original_game_count',s.get('game_removed',0)))):
        count=sum(v.casefold().endswith(suffix) for v in c.isolation.values(dll,'ClosedFilePath'))
        if count>target:
            change('delete','PBZSteamLab','ClosedFilePath',rule);count=0
        for _ in range(target-count):change('append','PBZSteamLab','ClosedFilePath',rule)
    if s.get('exe_added') and EXE_DENY in c.isolation.values(dll,'ClosedFilePath'):
        change('delete','PBZSteamLab','ClosedFilePath',EXE_DENY)
    if not remaining:
        change('set','PBZSteamLab','AllowNetworkAccess',s['prior_allow_network'])
        c.isolation.check_policy(dll)
    after=c.baseline.formal_files()
    host_changed=[]
    for name,digest in s['host_config_hashes'].items():
        f=Path(name)
        if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest()!=digest:host_changed.append(name)
    s.update({'restored':not remaining,'restored_at':utc8(),'restore_reason':reason,
              'network_active':False,'remaining_box_pids':remaining,
              'formal_files_changed':[n for n in sorted(set(after)|set(s['formal_before'])) if after.get(n)!=s['formal_before'].get(n)],
              'host_config_files_changed':host_changed,
              'host_registry_unchanged':c.registry_host()==s['host_registry_before'],
              'backup_check':c.preflight.compare(ROOT/'evidence/latest-preflight.json')})
    save(path,s);update(s)
    public={k:s.get(k) for k in ('started_at','deadline_at','restored','restored_at','restore_reason','network_active',
                                'remaining_box_pids','formal_files_changed','host_config_files_changed','host_registry_unchanged','backup_check')}
    save(ROOT/'evidence/official-validation/latest-cleanup.json',public)
    return s


def watchdog(path):
    """用途：不依赖对话的独立倒计时；主机Steam恢复、超时或停止标记即撤销联网。"""
    c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    while True:
        s=json.loads(path.read_text(encoding='utf-8'))
        if s['restored']:return
        reason=None;outside=[];monitor_error=None
        if path.with_suffix('.stop').exists():reason='Official validation finished or cancelled'
        elif time.time()>=s['deadline_unix']:reason='Official validation deadline reached'
        else:
            try:
                outside=c.host_steam_pids(dll)
                if outside:reason='Host Steam resumed; preserve it'
                elif not s.get('game_stage') and c.preflight.games_running():reason='Unexpected game during blocked preparation'
            except Exception as error:
                reason='Monitoring failed; revoke network';monitor_error=type(error).__name__
        if reason:
            # 用途：先断网和回收，再写只含进程元数据的诊断，不记录命令行、账号或令牌。
            stopped_at=utc8();restore(path,reason)
            diagnostic={'observed_at':stopped_at,'reason':reason,'outside_steam_pids':outside,
                        'monitor_error_type':monitor_error,'metadata':[]}
            try:
                if outside:
                    command='Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -in @('+','.join(map(str,outside))+')} | Select-Object Name,ProcessId,ParentProcessId,ExecutablePath,CreationDate | ConvertTo-Json -Compress'
                    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,timeout=10)
                    if not result.returncode and result.stdout.strip():
                        rows=json.loads(result.stdout)
                        diagnostic['metadata']=rows if isinstance(rows,list) else [rows]
            except Exception as error:diagnostic['metadata_error_type']=type(error).__name__
            save(Path(s['work'])/'monitor-stop.json',diagnostic)
            return
        time.sleep(2)


def prepare(launch_ready=False,client_network=False,local_saved=False,block_steam_overlay=False,block_nvidia_overlay=False,token_setting=None,offline_validation=False,lease_minutes=12):
    # 用途：批量采集只在开始前选择20分钟上限；不延长已经运行的会话，也不开联网例外。
    if lease_minutes not in (12,20) or (lease_minutes==20 and (not offline_validation or client_network)):
        raise RuntimeError('Batch duration is available only for strictly offline preparation')
    c.isolation.select_box('PBZSteamLab');dll=c.isolation.api();policy=c.isolation.check_policy(dll)
    if c.baseline.box_pids(dll) or c.host_steam_pids(dll) or c.preflight.games_running():
        raise RuntimeError('Existing session preserved')
    if any(rule in policy['ClosedFilePath'] for rule in [STEAM_OVERLAY_DENY,*NVIDIA_OVERLAY_DENIES]):
        raise RuntimeError('Unexpected inherited overlay experiment; restore it before a new lease')
    if token_setting is not None and token_setting not in TOKEN_COMPATIBILITY_KEYS:
        raise RuntimeError('Unknown token compatibility setting')
    model=json.loads((ROOT/'项目状态.json').read_text(encoding='utf-8'))
    cloud=json.loads((ROOT/'evidence/offline-steam/research-cloud-disable-verification.json').read_text(encoding='utf-8'))
    if not model.get('game_online_validation_authorized') or not cloud.get('persists_after_offline_restart'):
        raise RuntimeError('Explicit online authorization or persistent cloud gate missing')
    verify_build()
    if LATEST.exists() and not json.loads(state_path().read_text(encoding='utf-8')).get('restored'):
        raise RuntimeError('Validation already active')
    now=datetime.now(timezone(timedelta(hours=8)));deadline=now+timedelta(minutes=lease_minutes)
    work=ROOT/'evidence/official-validation'/now.strftime('%Y%m%d-%H%M%S');work.mkdir(parents=True)
    private=ROOT/'runtime'/now.strftime('official-validation-%Y%m%d-%H%M%S');private.mkdir()
    path=private/'state.json'
    s={'state_file':str(path),'started_at':now.isoformat(),'deadline_at':deadline.isoformat(),'deadline_unix':deadline.timestamp(),
       'restored':False,'work':str(work),'network_active':False,'game_stage':False,'cloud_verified':False,
       'launch_ready_preparation':launch_ready,
       'client_network_preparation':client_network,
       'offline_validation':offline_validation,
       'local_saved_virtualization':local_saved,'local_saved_probe_passed':False,'local_saved_rule_removed':False,
       'steam_overlay_block_requested':block_steam_overlay,'steam_overlay_block_added':False,
       'nvidia_overlay_block_requested':block_nvidia_overlay,'nvidia_overlay_rules_added':[],
       'compatibility_setting':token_setting,'compatibility_setting_applied':False,
       'compatibility_setting_prior':c.isolation.values(dll,token_setting) if token_setting else [],
       'compatibility_probe_passed':False,
       'original_local_saved_rule_count':sum(v.casefold().endswith(r'\appdata\local\projectpbz\*') for v in policy['ClosedFilePath']),
       'prior_allow_network':policy['AllowNetworkAccess'][0],'prior_network_rules':policy['NetworkAccess'],
       'library_removed':0,'game_removed':0,'exe_added':False,'formal_before':c.baseline.formal_files(),
       'original_library_count':sum(v.casefold().endswith(r'\steamlibrary\*') for v in policy['ClosedFilePath']),
       'original_game_count':sum(v.casefold().endswith(r'\steamapps\common\pbz\*') for v in policy['ClosedFilePath']),
       # 用途：每轮重新记录主机配置哈希；本人上轮正常使用Steam可能已合法改变旧哈希。
       'host_registry_before':c.registry_host(),
       'host_config_hashes':{name:hashlib.sha256(Path(name).read_bytes()).hexdigest()
                             for name in cloud['host_config_files']},
       'ue4ss_deployed':False,'save_gameplay_allowed':False}
    save(path,s);save(LATEST,{'state_file':str(path)})
    watcher=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--watchdog',str(path)],
       stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
       creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP)
    try:
        s['watchdog_pid']=watcher.pid
        if token_setting:
            # 用途：只改变一个官方令牌兼容选项。先在断网、正式库封锁下重跑隔离探针。
            # 不使用UnfilteredToken/NoSecurityIsolation，不解除DropAdminRights和文件保护。
            s['compatibility_setting_applied']=True;save(path,s)
            change('set','PBZSteamLab',token_setting,'y')
            probe=subprocess.run([sys.executable,str(ROOT/'tools/test_isolation.py'),'--steam-lab'],capture_output=True,timeout=75)
            save(work/'compatibility-probe-launch.json',{'at':utc8(),'exit_code':probe.returncode,'setting':token_setting})
            result=json.loads((ROOT/'evidence/isolation-probe/latest-result.json').read_text(encoding='utf-8'))
            save(work/'compatibility-isolation-proof.json',result)
            if probe.returncode or not result.get('passed') or result.get('box')!='PBZSteamLab':
                raise RuntimeError('Token compatibility isolation probe failed; game launch prohibited')
            if c.cleanup(dll):raise RuntimeError('Probe processes remain')
            s['compatibility_probe_passed']=True;save(path,s)
        if block_steam_overlay:
            s['steam_overlay_block_added']=True;save(path,s)
            change('append','PBZSteamLab','ClosedFilePath',STEAM_OVERLAY_DENY)
            if STEAM_OVERLAY_DENY not in c.isolation.values(dll,'ClosedFilePath'):
                raise RuntimeError('Overlay experiment rule failed to apply')
        if block_nvidia_overlay:
            for rule in NVIDIA_OVERLAY_DENIES:
                s['nvidia_overlay_rules_added'].append(rule);save(path,s)
                change('append','PBZSteamLab','ClosedFilePath',rule)
                if rule not in c.isolation.values(dll,'ClosedFilePath'):
                    raise RuntimeError('NVIDIA overlay rule failed to apply')
        if launch_ready and EXE_DENY in policy['ClosedFilePath']:
            raise RuntimeError('Unexpected inherited executable block')
        if not launch_ready and EXE_DENY not in policy['ClosedFilePath']:
            s['exe_added']=True;save(path,s);change('append','PBZSteamLab','ClosedFilePath',EXE_DENY)
        # 用途：SbieIni delete会移除所有重复同值规则，原数量先落盘，恢复时按目标数量核对。
        s['library_removed']=s['original_library_count'];s['game_removed']=s['original_game_count'];save(path,s)
        if s['library_removed']:change('delete','PBZSteamLab','ClosedFilePath',LIB_DENY)
        if s['game_removed']:change('delete','PBZSteamLab','ClosedFilePath',GAME_DENY)
        container=c.isolation.get_root(dll)
        if local_saved:
            # 用途：改用Sandboxie默认文件副本机制，绝不添加OpenFilePath或主机写例外。
            # 本轮先用箱内标记与原件哈希验收；失败则回收，绝不启动联网游戏。
            if s['original_local_saved_rule_count']!=1:raise RuntimeError('Unexpected local Saved protection count')
            s['local_saved_rule_removed']=True;save(path,s)
            change('delete','PBZSteamLab','ClosedFilePath',LOCAL_SAVED_DENY)
            from local_saved_probe import verify_virtualized_read_write
            verify_virtualized_read_write(path)
            s=json.loads(path.read_text(encoding='utf-8'))
        if launch_ready:
            # 用途：在离线状态下，让全新客户端从允许读取游戏的策略启动，排除旧进程缓存封锁。
            # 只复制真实已安装清单到箱内，不更改许可、版本字段或正式安装；意外游戏启动仍触发回收。
            manifest=c.baseline.GAME.parents[1]/'appmanifest_4115450.acf'
            target=c.isolation.virtual_file(container,manifest)
            s['virtual_manifest_previous_sha256']=hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(manifest,target)
            s['installed_manifest_source_sha256']=hashlib.sha256(manifest.read_bytes()).hexdigest()
            if hashlib.sha256(target.read_bytes()).hexdigest()!=s['installed_manifest_source_sha256']:
                raise RuntimeError('Installed manifest mirror mismatch')
            save(path,s)
        if client_network:
            # 用途：只让研究Steam完成已有授权的认证/更新；PBZ网络仍默认拒绝，意外启动触发回收。
            for rule in ONLINE_RULES[:2]:change('append','PBZSteamLab','NetworkAccess',rule)
            if sorted(c.isolation.values(dll,'NetworkAccess'))!=sorted(s['prior_network_rules']+ONLINE_RULES[:2]):
                raise RuntimeError('Client preparation rules mismatch')
            update(s)
        subprocess.Popen([str(c.isolation.SBIE/'Start.exe'),'/box:PBZSteamLab','/silent',r'E:\PBZSteamLabClient\steam.exe','-offline'],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        login_seen_at=None;preparation_rows=[]
        for _ in range(25):
            time.sleep(2)
            if c.host_steam_pids(dll):raise RuntimeError('Host Steam detected')
            result=c.bootstrap('inspect',work,container)
            ps=c.box_processes(dll)
            titles=[w['title'] for w in c.windows_for({p['ProcessId'] for p in ps}) if w['visible']]
            # 用途：保存有限的就绪证据；不记录登录内容、账号或令牌，避免把陈旧PID误当故障原因。
            preparation_rows.append({'at':utc8(),'steam_pids':[p['ProcessId'] for p in ps if p['Name'].lower()=='steam.exe'],
                'main_window_visible':'Steam' in titles,
                'login_window_visible':any('登录 Steam' in title or 'sign in to steam' in title.lower() for title in titles),
                'official_existing_global_user_available':result.get('official_existing_global_user_available'),
                'active_client_in_same_box':result.get('active_client_in_same_box')})
            save(work/'client-ready-observations.json',preparation_rows)
            if any('登录 Steam' in title or 'sign in to steam' in title.lower() for title in titles):
                if login_seen_at is None:login_seen_at=time.monotonic()
                continue
            login_seen_at=None
            if result.get('official_existing_global_user_available') and 'Steam' in titles:break
        else:raise RuntimeError('Research client did not reach a ready main window in the bounded preparation')
        subprocess.run([str(c.isolation.SBIE/'Start.exe'),'/box:PBZSteamLab','/silent',r'E:\PBZSteamLabClient\steam.exe','steam://gameproperties/4115450'],capture_output=True,timeout=10)
        save(path,s);update(s)
        print(json.dumps({'prepared':True,'game_blocked':not launch_ready,'game_launch_requested':False,
                          'unexpected_game_aborts_preparation':True,'client_internet_allowed':client_network,'game_internet_allowed':False,
                          'deadline_at':s['deadline_at'],'work':str(work)},ensure_ascii=False))
    except Exception as error:
        restore(path,'Preparation failed')
        save(work/'preparation-failure.json',{'at':utc8(),'error_type':type(error).__name__,
             'reason':str(error),'game_network_opened':False,'cleanup_requested':True})
        raise


def launch(offline=False,readonly_ue4ss=False):
    path=state_path();s=json.loads(path.read_text(encoding='utf-8'))
    if s['restored'] or time.time()>=s['deadline_unix']:raise RuntimeError('Lease expired')
    # 用途：开始研究游戏前再次确认正式进度未变化；变化时拒绝启动，不覆盖用户进度。
    if c.baseline.formal_files()!=s['formal_before']:raise RuntimeError('Formal files changed; no research launch allowed')
    gate=Path(s['work'])/'cloud-gate.json'
    if not gate.exists() or not json.loads(gate.read_text(encoding='utf-8')).get('ui_off_verified'):
        raise RuntimeError('This client session cloud OFF gate not yet verified')
    if readonly_ue4ss:
        if not offline or not s.get('ue4ss_deployed') or not s.get('readonly_ue4ss_experiment'):
            raise RuntimeError('Self-built baseline requires a declared strictly offline research experiment')
        verify_build(s['ue4ss_loader_manifest'])
    else:
        verify_build()
    c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    if offline!=bool(s.get('offline_validation')):raise RuntimeError('Launch mode does not match prepared lease')
    policy=c.isolation.check_policy(dll,allow_official_client_preparation=s.get('client_network_preparation',False),allow_offline_validation=offline)
    if c.host_steam_pids(dll) or c.preflight.games_running():raise RuntimeError('Existing game or host session preserved')
    s.update({'cloud_verified':True,'game_stage':True,'network_active':not offline,'launch_requested_at':utc8()});save(path,s)
    try:
        for rule in ([] if offline else ONLINE_RULES):
            if rule not in c.isolation.values(dll,'NetworkAccess'):change('append','PBZSteamLab','NetworkAccess',rule)
        if sorted(c.isolation.values(dll,'NetworkAccess'))!=sorted([*s['prior_network_rules'],*([] if offline else ONLINE_RULES)]):raise RuntimeError('Network rules mismatch')
        denied=EXE_DENY in c.isolation.values(dll,'ClosedFilePath')
        if s.get('launch_ready_preparation'):
            if denied:raise RuntimeError('Launch-ready client inherited executable deny')
        else:
            if not denied:raise RuntimeError('Expected preparation game deny missing')
            change('delete','PBZSteamLab','ClosedFilePath',EXE_DENY)
        update(s)
        result=c.bootstrap('game',Path(s['work']),c.isolation.get_root(dll))
        save(Path(s['work'])/'launch.json',result)
        print(json.dumps({'official_launch_requested':True,'network_scope':'Steam client localhost TCP only; PBZ all network blocked' if offline else 'research Steam auth TCP and PBZ HTTP/HTTPS only','deadline_at':s['deadline_at'],'work':s['work']},ensure_ascii=False))
    except Exception:
        restore(path,'Official launch failed');raise


def finish():
    path=state_path();path.with_suffix('.stop').touch()
    for _ in range(25):
        s=json.loads(path.read_text(encoding='utf-8'))
        if s['restored']:
            print(json.dumps({'restored':True,'remaining_box_pids':s['remaining_box_pids'],'formal_files_changed':s['formal_files_changed']},ensure_ascii=False));return
        time.sleep(1)
    raise RuntimeError('Validation cleanup pending')


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    args=sys.argv[1:]
    if args==['--prepare']:prepare()
    elif args==['--prepare-launch-ready']:prepare(launch_ready=True)
    elif args==['--prepare-client-online']:prepare(launch_ready=True,client_network=True)
    elif args==['--prepare-local-saved']:prepare(launch_ready=True,client_network=True,local_saved=True)
    elif args==['--prepare-overlay-blocked']:prepare(launch_ready=True,client_network=True,local_saved=True,block_steam_overlay=True)
    elif args==['--prepare-overlays-blocked']:prepare(launch_ready=True,client_network=True,local_saved=True,block_steam_overlay=True,block_nvidia_overlay=True)
    elif len(args)==2 and args[0]=='--prepare-token-compatibility':prepare(launch_ready=True,client_network=True,local_saved=True,block_steam_overlay=True,block_nvidia_overlay=True,token_setting=args[1])
    elif args==['--prepare-offline-compatible']:prepare(launch_ready=True,local_saved=True,block_steam_overlay=True,block_nvidia_overlay=True,token_setting='UnstrippedToken',offline_validation=True)
    elif args==['--prepare-offline-batch']:prepare(launch_ready=True,local_saved=True,block_steam_overlay=True,block_nvidia_overlay=True,token_setting='UnstrippedToken',offline_validation=True,lease_minutes=20)
    elif args==['--launch']:launch()
    elif args==['--finish']:finish()
    elif len(args)==2 and args[0]=='--watchdog':watchdog(Path(args[1]))
    else:raise RuntimeError('Use --prepare, --prepare-launch-ready, --launch or --finish')
