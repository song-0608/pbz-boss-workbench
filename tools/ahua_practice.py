"""用途：把阿花四技能与F7目标训练集中起来；只写研究箱，不安装到正式游戏。"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OWNER = ROOT / 'runtime/ahua-practice.json'


class PreconditionNotReady(RuntimeError):
    """用途：尚未发生游戏修改的前置条件失败，可留在当前游戏重试。"""


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save_owner(data):
    # 用途：用原子替换防止窗口刷新读到半份JSON。
    OWNER.parent.mkdir(parents=True, exist_ok=True)
    pending = OWNER.with_suffix('.' + str(os.getpid()) + '.pending')
    pending.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    pending.replace(OWNER)


def step(name, *args, timeout=100):
    print('正在处理：' + name, flush=True)
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    result = subprocess.run([sys.executable, str(ROOT / 'tools' / name), *args],
                            cwd=ROOT, env=env, capture_output=True, timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    # 用途：详细诊断只保留本地；给初学者显示步骤与结果。
    log = ROOT / 'runtime/ahua-practice-steps.log'
    with log.open('ab') as output:
        output.write(('\nSTEP ' + name + '\n').encode('utf-8'))
        output.write(result.stdout + result.stderr)
    if result.returncode:
        detail = result.stderr.decode('utf-8', errors='replace').strip().splitlines()
        raise RuntimeError(name + '：' + (detail[-1] if detail else '执行失败；查看本地步骤日志'))
    print('完成：' + name, flush=True)


def owned_session():
    import official_validation as v
    owner = read(OWNER)
    if str(v.state_path()) != owner['state_file']:
        raise RuntimeError('当前研究会话不属于此训练窗口，保留原会话')
    state = read(Path(owner['state_file']))
    if state.get('restored') or time.time() >= state['deadline_unix']:
        raise RuntimeError('本轮已结束；重新点击第1步准备')
    if not state.get('offline_validation') or state.get('network_active'):
        raise RuntimeError('本入口只允许完全离线研究')
    return owner, state


def log_path(state):
    return next(Path(row['physical_path']).parent / 'UE4SS.log'
                for row in state['ue4ss_loader_manifest']
                if row['physical_path'].endswith('UE4SS.dll'))


def deployed_controls(deployment):
    """显示实际部署的键位快照，不能读取可能已被用户修改的下一轮配置。"""
    import player_keymap
    keymap=deployment.get('player_keymap')
    if keymap is None and(deployment.get('boss_candidate')or deployment.get('skill_lab')or deployment.get('expanded')):
        return {'enter':'F6','exit':'F10','cycle_target':'F7'}
    return dict(player_keymap.validate(keymap)['controls'])


def validate_map_travel_loader(state,text):
    if not (state.get('load_map_hook_enabled') or state.get('load_map_hook_trial')) or not re.search(r'GameEngine::LoadMap address 0x[0-9a-fA-F]+',text):
        raise RuntimeError('玩家入口要求启动时启用LoadMap保护并核对真实引擎地址；当前旧会话不能补开')
    if re.search(r'\[(?:LoadMap|UE4SS\.LoadMap\.[^]]+)\][^\r\n]*(?:disabled|[Ff]ailed)',text):
        raise RuntimeError('LoadMap detour初始化失败，不能把Lua回调注册当作恢复保护已安装')
    if not re.search(r'\[UE4SS\.LoadMap\.LuaModImpl\] Added prehook with Id ',text):
        raise RuntimeError('LoadMap真实prehook安装回执缺失')


def wait_tokens(path, tokens, timeout=30, offset=0):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        data = path.read_text(encoding='utf-8', errors='replace')[offset:] if path.exists() else ''
        if all(token in data for token in tokens):
            return data
        if 'PBZ_CONTROL_LIFECYCLE:PREREQUISITE_RETRY_SAFE=true' in data:
            reasons = [line.split('PREREQUISITE_NOT_READY=', 1)[1]
                       for line in data.splitlines() if 'PREREQUISITE_NOT_READY=' in line]
            raise PreconditionNotReady('尚未就绪：' + (reasons[-1] if reasons else '前置条件不满足')
                                       + '。已确认未接管或已恢复主角，可在同一游戏再点第3步，不需要重启')
        if 'PBZ_CONTROL_LIFECYCLE:ISSUE_' in data or 'PBZ_COMBAT_CONTRACT:ISSUE=' in data:
            raise RuntimeError('本轮初始化未通过，未开放技能；诊断已保留。请结束本轮训练')
        time.sleep(.5)
    raise RuntimeError('等待超时；保留诊断，不会自动反复重启游戏')


def prepare():
    from mod_installation import active_mod_root
    active_mod_root()  # 在准备或启动Steam之前明确拒绝已停用、已卸载或校验不符的Mod。
    import official_validation as v
    import gameplay_save_probe
    previous = read(v.state_path()) if v.LATEST.exists() else None
    if previous and not previous.get('restored'):
        raise RuntimeError('已有研究会话，不能覆盖；先在原窗口结束')
    # 用途：复用已通过的隔离配置。这个函数没有任何联网分支，不增加联网许可。
    v.prepare(launch_ready=True, local_saved=True, block_steam_overlay=True,
              block_nvidia_overlay=True, token_setting='UnstrippedToken',
              offline_validation=True, lease_minutes=20)
    owner = {'state_file': str(v.state_path()), 'phase': 'preparing', 'created_at': v.utc8()}
    save_owner(owner)
    try:
        gameplay_save_probe.prepare()
        step('inspect_offline_window.py', '--offline-validation-review', '--properties')
        screenshot = ROOT / 'runtime/steam-menu-private.png'
        owner.update(phase='prepared', cloud_screenshot_sha256=hashlib.sha256(screenshot.read_bytes()).hexdigest())
        save_owner(owner)
        print('隔离副本已准备。请看研究Steam的游戏属性，确认云同步关闭，再点第2步。', flush=True)
    except Exception as error:
        work=Path(read(v.state_path())['work'])
        v.save(work/'preparation-failure.json',{'at':v.utc8(),'error_type':type(error).__name__,'reason':str(error)})
        try:v.finish()
        except Exception as cleanup_error:
            error.add_note('Research cleanup pending: '+str(cleanup_error))
        raise


def launch(cloud_off_reviewed,load_map_hook_trial=False):
    from mod_installation import active_mod_root
    active_mod_root()
    if not cloud_off_reviewed:
        raise RuntimeError('请先在研究Steam确认云同步关闭')
    import official_validation as v
    from pbz_ue4ss_baseline import deploy_and_launch
    import shutil
    owner, state = owned_session()
    if owner['phase'] != 'prepared':
        raise RuntimeError('先完成第1步；已经启动时不要重复点击')
    screenshot = ROOT / 'runtime/steam-menu-private.png'
    if hashlib.sha256(screenshot.read_bytes()).hexdigest() != owner['cloud_screenshot_sha256']:
        raise RuntimeError('属性截图已被其他操作更新，请重新准备')
    work = Path(state['work'])
    shutil.copy2(screenshot, work / 'cloud-off-reviewed.png')
    v.save(work / 'cloud-gate.json', {'at': v.utc8(), 'ui_off_verified': True,
           'reviewed_by': 'explicit cloud-off-reviewed launch action', 'screenshot': 'cloud-off-reviewed.png'})
    state.update(test_purpose='User-operated protected Ahua four-key offline practice; no map exploration',
                 restart_reason='User explicitly started one new bounded practice session',
                 save_isolation_acceptance_repeated=False)
    state['load_map_hook_trial']=bool(load_map_hook_trial)
    state['load_map_hook_enabled']=True
    v.save(v.state_path(), state)
    carrier = ROOT / 'adaptation/pbz-26367565/Mods/PBZObserveAI/Scripts/main.lua'
    original = carrier.read_bytes()
    try:
        # 用途：游戏启动只载入待机标记，不扫描地图，不自动生成Boss或操控主角。
        carrier.write_bytes(b'print("PBZ_PRACTICE:WAITING=load your isolated scene then enable practice\\n")\n')
        deploy_and_launch(with_signature=True, readonly_ai=True, readonly_hot_reload=True,
                          load_map_hook_trial=True)
    except Exception as error:
        v.save(work/'launch-failure.json',{'at':v.utc8(),'error_type':type(error).__name__,'reason':str(error)})
        try:v.finish()
        except Exception as cleanup_error:
            error.add_note('Research cleanup pending: '+str(cleanup_error))
        raise
    finally:
        carrier.write_bytes(original)
    owner['phase'] = 'game_launched'
    save_owner(owner)
    print('训练游戏已启动。只进入研究副本的场景，站稳后切回此窗口点第3步。', flush=True)


def review_cloud():
    """准备状态下重新打开精确游戏属性，避免Steam尚未显示属性时把主窗口误作云同步证据。"""
    import official_validation as v
    owner,state=owned_session()
    if owner['phase']!='prepared':raise RuntimeError('仅未启动游戏的已准备会话可刷新云同步核对')
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    c.isolation.check_policy(dll,allow_offline_validation=True)
    if c.host_steam_pids(dll)or any(p['Name'].lower()=='pbz.exe'for p in c.box_processes(dll)):
        raise RuntimeError('保留现有客户端或游戏，不能刷新此准备状态')
    subprocess.run([str(c.isolation.SBIE/'Start.exe'),'/box:PBZSteamLab','/silent',
        r'E:\PBZSteamLabClient\steam.exe','steam://gameproperties/4115450'],capture_output=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
    step('inspect_offline_window.py','--offline-validation-review','--properties')
    owner['cloud_screenshot_sha256']=hashlib.sha256((ROOT/'runtime/steam-menu-private.png').read_bytes()).hexdigest()
    save_owner(owner)
    print('属性截图已刷新；须查看本次截图后确认云同步关闭。',flush=True)


def arm(expanded=False, skill_lab=False, player_key_trial=False,death_trial=False,native_death_trial=False,active_skill_death_trial=False,scene_transition_trial=False,arena_navigation_trial=False,combo_scheduler_trial=False,incoming_combat_trial=False,active_skill_disposal_trial=False,performance_profile=False,boss_candidate=None,boss_candidate_bundle=None):
    from mod_installation import active_mod_root
    active_mod_root()
    active_skill_death_trial=active_skill_death_trial or active_skill_disposal_trial
    if combo_scheduler_trial and not skill_lab:raise RuntimeError('连招调度只允许显式开发技能试验台')
    native_death_trial=native_death_trial or active_skill_death_trial
    death_trial=death_trial or native_death_trial or incoming_combat_trial
    if boss_candidate_bundle and not boss_candidate:
        raise RuntimeError('独立开发包必须指定候选Boss')
    if boss_candidate:
        if any((expanded,skill_lab,player_key_trial,death_trial,combo_scheduler_trial,scene_transition_trial)):
            raise RuntimeError('独立Boss候选不能混用阿花实验模式')
        from boss_candidate_gate import validate
        validate(boss_candidate,bundle=boss_candidate_bundle)
    player_entry=not(boss_candidate or expanded or skill_lab or player_key_trial or death_trial)
    arena_navigation_trial=arena_navigation_trial or player_entry or active_skill_disposal_trial or bool(boss_candidate)
    if arena_navigation_trial and not(player_entry or boss_candidate or skill_lab or combo_scheduler_trial or player_key_trial or active_skill_disposal_trial):
        raise RuntimeError('导航装配只用于完整玩家入口，不能混合开发技能或死亡按键')
    if expanded and skill_lab:
        raise RuntimeError('F8/F9由两种开发模式共用，请只选择其中一种')
    if player_key_trial and (expanded or skill_lab):
        raise RuntimeError('玩家键位验收不能与开发候选键位共用F8')
    import official_validation as v
    owner, state = owned_session()
    if owner['phase'] != 'game_launched':
        raise RuntimeError('先完成第2步并进入游戏场景；同轮只装配一次')
    if state['deadline_unix'] - time.time() < 180:
        raise RuntimeError('本轮剩余时间不足；请结束本轮后再开始')
    path = log_path(state)
    if player_entry or scene_transition_trial:
        validate_map_travel_loader(state,path.read_text(encoding='utf-8',errors='replace'))
    if not owner.get('native_contracts_ready'):
        offset = len(path.read_text(encoding='utf-8', errors='replace'))
        step('probe_combat_readonly.py')
        wait_tokens(path, ['PBZ_CAMERA_CONTRACT:PASS=', 'PBZ_COMBAT_CONTRACT:PASS='], offset=offset)
        # 用途：只核对本次进程调用契约；静止前置失败后不重复读声明或重启。
        for name in ('inspect_camera_contract.py', 'inspect_combat_contract.py', 'inspect_combat_types.py',
                     'inspect_remote_contract.py', 'inspect_input_barrier_contract.py', 'inspect_player_protection_contract.py'):
            step(name, timeout=100)
        owner['native_contracts_ready'] = True
        save_owner(owner)
    if player_entry or((boss_candidate or skill_lab or combo_scheduler_trial or player_key_trial or active_skill_disposal_trial)and arena_navigation_trial):
        step('inspect_player_ui_contract.py')
    if arena_navigation_trial:
        step('inspect_arena_contract.py')
    offset = len(path.read_text(encoding='utf-8', errors='replace'))
    if death_trial and not (Path(state['work'])/'boss-lifecycle-contract.json').exists():
        step('inspect_boss_lifecycle_contract.py')  # 下游仍逐项核对当前PID、声明及枚举。
    step('run_control_lifecycle_probe.py', '--interactive', '--camera', '--combat', '--remote',
         *(['--performance-profile']if performance_profile else[]),
         '--barrier', '--protect-player', '--batch-skills', '--practice', '--update-modules',
         '--target-cycle', *(['--extra-skills'] if expanded else []),
         *(['--scene-transition-trial']if scene_transition_trial else[]),
         *(['--arena-navigation-trial']if arena_navigation_trial else[]),
         *(['--player-entry']if player_entry else[]),
         *(['--boss-candidate',boss_candidate]if boss_candidate else[]),
         *(['--boss-candidate-bundle',str(boss_candidate_bundle)]if boss_candidate_bundle else[]),
         *(['--skill-lab'] if skill_lab else []),
         *(['--combo-scheduler-trial'] if combo_scheduler_trial else []),
         *(['--player-key-trial'] if player_key_trial else []),
         *(['--death-trial'] if death_trial else []),
         *(['--incoming-combat-trial'] if incoming_combat_trial else []),
         *(['--native-death-trial'] if native_death_trial else []),
         *(['--active-skill-death-trial'] if active_skill_death_trial else []),
         *(['--active-skill-disposal-trial'] if active_skill_disposal_trial else []))
    try:
        wait_tokens(path, ['PBZ_CONTROL_LIFECYCLE:INTERACTIVE_READY=']
                    + (['PBZ_CONTROL_LIFECYCLE:MAP_TRAVEL_GUARD_READY=true'] if player_entry else []),
                    timeout=100, offset=offset)
    except PreconditionNotReady:
        # 用途：Lua明确证明未发生修改时，保留游戏和本轮声明以便原地重试。
        raise
    except Exception:
        # 用途：不在不明初始化状态下继续试玩。失败后结束研究箱，不修改或回滚正式进度。
        v.finish()
        owner['phase'] = 'failed_and_closed'
        save_owner(owner)
        step('postcheck_native_diagnostic.py')
        raise
    owner.update(phase='armed', log_offset=offset, expanded=expanded, skill_lab=skill_lab,
                 player_key_trial=player_key_trial, death_trial=death_trial,native_death_trial=native_death_trial,
                 active_skill_death_trial=active_skill_death_trial,skill_lab_cast_key='F8')
    owner['scene_transition_trial']=scene_transition_trial
    owner['player_entry']=player_entry
    owner['boss_candidate']=boss_candidate
    owner['boss_candidate_bundle']=str(Path(boss_candidate_bundle).resolve())if boss_candidate_bundle else None
    owner['active_skill_disposal_trial']=active_skill_disposal_trial
    owner['incoming_combat_trial']=incoming_combat_trial
    owner['arena_navigation_trial']=arena_navigation_trial
    owner['combo_scheduler_trial']=combo_scheduler_trial
    # 用途：把本次Lua实际装配结果交给窗口显示；配置文件中的候选键不等于已被启用。
    current=path.read_text(encoding='utf-8',errors='replace')[offset:]
    owner['actual_bindings']=[{'slot':slot,'skill':skill,'key':key}
        for slot,skill,key in re.findall(r'PLAYER_BINDING=(\w+)\|(\w+)\|([\w_]+)',current)]
    owner['actual_controls']=deployed_controls(read(Path(state['work'])/'control-lifecycle-deployment.json'))
    import workbench_support
    deployment=read(Path(state['work'])/'control-lifecycle-deployment.json')
    owner['workbench']=deployment.get('workbench')if (
        player_entry and 'PBZ_CONTROL_LIFECYCLE:WORKBENCH_READY='+workbench_support.READY in current)else None
    save_owner(owner)
    with (ROOT / 'runtime/ahua-practice-monitor.log').open('ab') as output:
        process = subprocess.Popen([sys.executable, str(Path(__file__)), '--monitor'], cwd=ROOT,
                         stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    owner['monitor_pid'] = process.pid
    if player_entry or boss_candidate:
        with (ROOT/'runtime/player-overlay.log').open('ab')as output:
            overlay=subprocess.Popen([sys.executable,str(ROOT/'tools/player_overlay.py')],cwd=ROOT,
                stdin=subprocess.DEVNULL,stdout=output,stderr=output,creationflags=subprocess.CREATE_NO_WINDOW)
        owner['hud_pid']=overlay.pid
    save_owner(owner)
    keys=owner['actual_controls']
    print(('独立Boss候选已就绪：'if boss_candidate else'阿花已就绪：')+keys['enter']+'开始，WASD移动，鼠标镜头，'
          +keys['cycle_target']+'切敌人，'+keys['exit']+'恢复主角。最长10分钟。',flush=True)
    print('本轮实际技能键：'+'；'.join(row['key']+' = '+row['skill']for row in owner['actual_bindings']),flush=True)
    print('Esc先恢复主角，再按Esc进入原菜单；按键修改在下次装配生效。',flush=True)
    if skill_lab:
        print('开发试验台：F9选择候选，F8试放；仅绑定本次已授予白名单，不代表玩家可用技能。', flush=True)


def stop():
    import official_validation as v
    if not OWNER.exists():
        print('本训练窗口没有启动过研究会话。', flush=True)
        return
    owner = read(OWNER)
    if str(v.state_path()) != owner['state_file']:
        raise RuntimeError('这是其他工具的会话，此窗口不会关闭它')
    if not read(v.state_path()).get('restored'):
        v.finish()
    # 箱内回收与正式核对分别记录；核对异常不遗留“游戏仍运行”的阶段状态。
    owner.update(phase='closed',postcheck_review_required=True)
    save_owner(owner)
    step('postcheck_native_diagnostic.py')
    owner['postcheck_review_required']=False
    save_owner(owner)
    print('训练已结束：研究箱已关闭，正式文件与本轮开始时一致；没有回写或回档。', flush=True)


def monitor():
    import official_validation as v
    owner, state = owned_session()
    expected = owner['state_file']
    path = log_path(state)
    while time.time() < state['deadline_unix']:
        if str(v.state_path()) != expected or read(Path(expected)).get('restored'):
            return
        current = read(OWNER)
        if current.get('phase') != 'armed' or current.get('log_offset') != owner['log_offset']:
            return  # 用途：恢复后原地重新装配时，旧监督器退出，保留总会话的独立看门狗。
        data = path.read_text(encoding='utf-8', errors='replace')[owner['log_offset']:] if path.exists() else ''
        # 用途：切图/对象失效导致恢复失败时只结束研究箱；不会重开游戏或改写正式存档。
        fatal = any(token in data for token in ('state=FAULTED', 'PBZ_CONTROL_LIFECYCLE:ISSUE_', '[Lua::execute_file]', 'idle_world_check success=false'))
        ended = 'PBZ_CONTROL_LIFECYCLE:INTERACTIVE_END=' in data
        if fatal or ended:
            print('训练停止原因：' + ('检测到恢复/初始化异常' if fatal else '训练时间结束'), flush=True)
            stop()
            return
        time.sleep(1)


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description='阿花离线训练入口，不接触正式存档')
    parser.add_argument('--performance-profile',action='store_true',help='开发性能验收：只读统计游戏线程回调与反射开销')
    parser.add_argument('action', nargs='?', choices=('prepare', 'review', 'launch', 'arm', 'stop', 'status'))
    parser.add_argument('--cloud-off-reviewed', action='store_true')
    parser.add_argument('--load-map-hook-trial',action='store_true',help='启动时显式启用引擎LoadMap detour，仅用于开发切图验收')
    parser.add_argument('--monitor', action='store_true')
    parser.add_argument('--expanded', action='store_true', help='开发验收：F8/F9为重击02和特殊03候选')
    parser.add_argument('--skill-lab', action='store_true', help='开发验收：F9选择、F8试放；普攻01隔离禁用')
    parser.add_argument('--combo-scheduler-trial',action='store_true',help='仅开发技能台：Attack_01最多25秒Brain调度许可')
    parser.add_argument('--player-key-trial', action='store_true', help='开发验收：只对受保护默认键位临时开放待验F8')
    parser.add_argument('--death-trial',action='store_true',help='开发验收：F12仅对本轮自建Boss尝试一次原生伤害，不改血量字段')
    parser.add_argument('--incoming-combat-trial',action='store_true',help='开发验收：F12让两个本轮训练角色用真实技能07攻击自建Boss，最多360秒')
    parser.add_argument('--native-death-trial',action='store_true',help='开发验收：核对当轮死亡枚举后，F12仅对本轮自建Boss调用一次Kill')
    parser.add_argument('--active-skill-death-trial',action='store_true',help='开发验收：F12仅在本轮技能08真实活动时请求一次自建阿花原生死亡')
    parser.add_argument('--active-skill-disposal-trial',action='store_true',help='开发验收：F12同线程销毁精确活动技能08的自建Actor，销毁后不读旧Spec')
    parser.add_argument('--scene-transition-trial',action='store_true',help='开发切图验收：恢复后经原菜单重载；F12仅在空闲接管时重载当前研究地图一次')
    parser.add_argument('--arena-navigation-trial',action='store_true',help='开发验收：只使用当前导航投影核对的同层分离落点')
    parser.add_argument('--boss-candidate',choices=('057_wanjun','073_yanqiansui'),help='独立候选验收；不注册为玩家可玩Boss')
    parser.add_argument('--boss-candidate-bundle',type=Path,help='冻结的独立开发覆盖包；不替换已安装版本')
    args = parser.parse_args()
    if args.monitor:
        monitor()
    elif args.action == 'prepare':
        prepare()
    elif args.action == 'launch':
        launch(args.cloud_off_reviewed,load_map_hook_trial=args.load_map_hook_trial)
    elif args.action == 'review':
        review_cloud()
    elif args.action == 'arm':
        arm(expanded=args.expanded, skill_lab=args.skill_lab, player_key_trial=args.player_key_trial,
            performance_profile=args.performance_profile,
            incoming_combat_trial=args.incoming_combat_trial,
            death_trial=args.death_trial,native_death_trial=args.native_death_trial,active_skill_death_trial=args.active_skill_death_trial,
            scene_transition_trial=args.scene_transition_trial,arena_navigation_trial=args.arena_navigation_trial,
            combo_scheduler_trial=args.combo_scheduler_trial,active_skill_disposal_trial=args.active_skill_disposal_trial,boss_candidate=args.boss_candidate,
            boss_candidate_bundle=args.boss_candidate_bundle)
    elif args.action == 'stop':
        stop()
    else:
        print(json.dumps(read(OWNER) if OWNER.exists() else {'phase': 'not_started'}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        import traceback
        with (ROOT / 'runtime/ahua-practice-errors.log').open('a', encoding='utf-8') as output:
            traceback.print_exc(file=output)
        print('本步骤未完成：' + str(error), flush=True)
        sys.exit(2 if isinstance(error, PreconditionNotReady) else 1)
