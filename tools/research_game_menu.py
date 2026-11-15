"""用途：操作已核实研究箱菜单；玩法继续仅限已完成新备份的原版隔离探针。"""
import ctypes
from ctypes import wintypes as w
import json
from pathlib import Path
import sys
import time
import official_validation as v


def validate_startup_positioning(owner,state,text):
    """仅允许尚未装配的隔离场景做有界站位调整。"""
    last_spawn=text.rfind('PBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT=')
    rejected=text[last_spawn:]if last_spawn>=0 else ''
    cleaned=(last_spawn>=0 and 'PBZ_CONTROL_LIFECYCLE:PREREQUISITE_RETRY_SAFE=true'in rejected
        and 'PBZ_CONTROL_LIFECYCLE:END=initialization rejected before takeover; original player restoration verified'in rejected
        and all('OWNED_DESTROY_VERIFIED='+name+'|engine_unusable=true'in rejected for name in
            ('boss','boss_controller','target','target_controller','extra_target','extra_target_controller'))
        and not any(k in rejected for k in ('enter success=true','PLAYER_ENTRY_READY=','ISSUE_','state=FAULTED')))
    if not(owner.get('phase')=='game_launched' and owner.get('state_file')==state.get('state_file')
           and state.get('offline_validation') and not state.get('network_active')
           and state.get('ue4ss_deployed') and not state.get('restored')
           and 'PBZ_PRACTICE:WAITING=load your isolated scene then enable practice'in text
           and (last_spawn<0 or cleaned)):
        raise RuntimeError('Unarmed isolated startup scene required for bounded positioning')


def validate_control_menu_transition(owner,text):
    # 用途：切图测试只在主角已恢复且全部自建角色已回收后开放，拒绝借用旧接管记录。
    from control_action_evidence import restoration_result,world_retirement_result
    if owner.get('phase')=='armed'and (owner.get('player_entry') or owner.get('scene_transition_trial')):
        current=text[owner.get('log_offset',0):]
        enter=current.rfind('[PBZBossControl] enter success=true')
        restored=max(current.rfind('[PBZBossControl] '+label+' success=true')for label in ('exit','menu_exit','auto_exit'))
        if (enter>=0 and restored>enter and 'IDLE_WORLD_WATCH_READY='in current[:enter]
                and 'SPAWN_ATTEMPT='not in current[restored:] and restoration_result(current[enter:])['passed']):
            return  # 显式切图验收：主角已完整恢复，保留空闲观察器核对原菜单造成的对象退役。
        proof=world_retirement_result(text)
        if proof['passed']and 'SPAWN_ATTEMPT='not in text[proof['retirement_event_end']:]:return
        raise RuntimeError('Complete disposed-world proof required before recovery menu transition')
    if owner.get('phase')!='game_launched':raise RuntimeError('Retired owned actors required before menu transition')
    retired=text.rfind('PBZ_REARM_RETIRE:PASS=')
    if retired<0 or 'SPAWN_ATTEMPT='in text[retired:]:raise RuntimeError('Current assembly must be retired before menu transition')
    segment=text[:retired]
    enter=segment.rfind('[PBZBossControl] enter success=true')
    restored=max(segment.rfind('[PBZBossControl] '+label+' success=true')for label in ('exit','menu_exit','auto_exit'))
    if enter<0 or restored<enter or not restoration_result(segment[enter:])['passed']:
        raise RuntimeError('Current player restoration proof required before menu transition')


def click(x,y,width,height,purpose):
    registered_mouse=None
    positioning_key={'practice_position_left':65,'practice_position_forward':87,
                     'practice_position_back':83}.get(purpose)
    from workbench_support import ACTIONS,validate_dispatch
    workbench_key=ACTIONS.get(purpose)
    if workbench_key is not None:
        owner=json.loads((v.ROOT/'runtime/ahua-practice.json').read_text(encoding='utf-8'))
        validate_dispatch(v.ROOT,v.state_path(),owner)
        purpose='control_skill9'
    lab_cancel=purpose=='control_cancel_lab_cast'
    if lab_cancel:purpose='control_lab_cast'
    registered_cancel=purpose.startswith('control_cancel_registered_skill_')
    if registered_cancel:purpose=purpose.replace('control_cancel_registered_skill_','control_registered_skill_',1)
    death_after=purpose=='control_death_skill08'
    if death_after:
        owner=json.loads((v.ROOT/'runtime/ahua-practice.json').read_text(encoding='utf-8'))
        if not(owner.get('active_skill_death_trial')and owner.get('native_death_trial')and owner.get('death_trial')
               and owner.get('phase')=='armed'and owner.get('state_file')==str(v.state_path())):
            raise RuntimeError('Explicit current-session active skill08 death trial required')
        purpose='control_skill8'
    # 用途：取消验收在一次窗口/断网/文件校验之后发送有界的“出招、F10”，避免二次文件核对错过短招式活动窗口。
    cancel_action={'control_cancel_heavy01':'control_skill2','control_cancel_skill02':'control_skill3',
        'control_cancel_skill06':'control_skill5','control_cancel_skill08':'control_skill8',
        'control_cancel_skill07':'control_skill9','control_cancel_teleport_left':'control_teleport_left',
        'control_cancel_teleport_right':'control_teleport_right'}.get(purpose)
    cancel_after=cancel_action is not None or registered_cancel or lab_cancel
    if cancel_action is not None:purpose=cancel_action
    # 用途：新技能键复用同一离线/研究窗口/交互租约检查，按键值仍是有限白名单。
    skill_key_override={'control_teleport_left':81,'control_teleport_right':69}.get(purpose)
    if workbench_key is not None:skill_key_override=workbench_key
    if purpose.startswith('control_registered_skill_'):
        import player_keymap
        slot=purpose.removeprefix('control_registered_skill_')
        if slot not in player_keymap.SKILLS | player_keymap.OPTIONAL_SKILLS:
            raise RuntimeError('Unregistered skill action rejected')
        owner=json.loads((v.ROOT/'runtime/ahua-practice.json').read_text(encoding='utf-8'))
        if (owner.get('phase')!='armed' or owner.get('state_file')!=str(v.state_path())
                or owner.get('skill_lab') or owner.get('expanded')):
            raise RuntimeError('Current ordinary player entry required')
        rows=[r for r in owner.get('actual_bindings',[])if r.get('slot')==slot
              and r.get('skill')==player_keymap.ability_for_slot(slot)]
        key_codes={f'F{i}':111+i for i in range(1,13)}
        key_codes.update({k:ord(k)for k in 'QERTZXCVBGH'})
        key_codes.update(dict(zip(('ONE','TWO','THREE','FOUR','FIVE','SIX','SEVEN','EIGHT','NINE'),range(49,58))))
        key_codes['SPACE']=32
        mouse_flags={'LEFT_MOUSE_BUTTON':(2,4),'RIGHT_MOUSE_BUTTON':(8,16),'MIDDLE_MOUSE_BUTTON':(32,64)}
        if len(rows)!=1 or rows[0].get('key') not in key_codes.keys() | mouse_flags.keys():
            raise RuntimeError('Exact current deployed keyboard binding required')
        if rows[0]['key'] in mouse_flags:
            registered_mouse=mouse_flags[rows[0]['key']];purpose='control_attack'
        else:skill_key_override=key_codes[rows[0]['key']];purpose='control_skill9'
    if purpose=='control_native_combo':
        owner=json.loads((v.ROOT/'runtime/ahua-practice.json').read_text(encoding='utf-8'))
        if (owner.get('phase')!='armed'or owner.get('state_file')!=str(v.state_path())
                or not any(r.get('slot')=='native_combo'and r.get('skill')=='attack_01'and r.get('key')in('R','F11')for r in owner.get('actual_bindings',[]))):
            raise RuntimeError('Exact current deployed native combo binding required')
        native_key=next(r['key']for r in owner['actual_bindings']if r.get('slot')=='native_combo')
        skill_key_override={'R':82,'F11':122}[native_key];purpose='control_skill9'
    if skill_key_override is not None:purpose='control_skill9'
    if purpose=='control_pause':skill_key_override=27;purpose='control_skill9'
    if purpose=='control_scene_transition':
        owner=json.loads((v.ROOT/'runtime/ahua-practice.json').read_text(encoding='utf-8'))
        if not owner.get('scene_transition_trial')or owner.get('phase')!='armed' or owner['state_file']!=str(v.state_path()):
            raise RuntimeError('Explicit current-session transition trial required')
        skill_key_override=123;purpose='control_skill9'
    if purpose=='control_owned_damage':
        owner=json.loads((v.ROOT/'runtime/ahua-practice.json').read_text(encoding='utf-8'))
        if not owner.get('death_trial')or owner.get('phase')!='armed' or owner['state_file']!=str(v.state_path()):
            raise RuntimeError('Explicit current-session owned death trial required')
        skill_key_override=123;purpose='control_skill9'
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    c.isolation.check_policy(dll,allow_offline_validation=True)
    if c.host_steam_pids(dll):raise RuntimeError('Preserve host Steam')
    state=json.loads(v.state_path().read_text(encoding='utf-8'))
    if state.get('restored') or time.time()>=state['deadline_unix']:raise RuntimeError('Research lease has ended')
    # 用途：任何正式文件偏离本轮基线时，拒绝后续菜单或玩法输入；不自动回档。
    if c.baseline.formal_files()!=state['formal_before']:raise RuntimeError('Formal files changed; no research input allowed')
    if not state.get('offline_validation') or state.get('network_active'):raise RuntimeError('Menu input must be strictly offline')
    if purpose not in ('control_focus','control_menu_pause','control_menu_system','control_menu_return','control_menu_confirm','control_menu_continue','control_lab_next','control_lab_cast','control_target','control_skill5','control_skill8','control_skill9','control_look','control_enter','control_forward','control_skill','control_skill2','control_skill3','control_skill4','control_attack','control_exit','control_reload','open_settings','audio_tab','adjust_audio','back_to_menu','exit_game','observe_continue','observe_pause','observe_interact','observe_globalmap','observe_reload','observe_codex_down','observe_menu','probe_continue','probe_load_menu','probe_return_to_title','probe_confirm_return','probe_pause','probe_interact','probe_shrine_action'):
        if positioning_key is None:raise RuntimeError('No gameplay input supported')
    if positioning_key is not None:
        import ahua_practice as practice
        owner,owned=practice.owned_session()
        validate_startup_positioning(owner,state,practice.log_path(state).read_text(encoding='utf-8',errors='replace'))
        proof=json.loads((v.ROOT/'evidence/latest-gameplay-save-isolation.json').read_text(encoding='utf-8'))
        if not proof.get('passed'):raise RuntimeError('Proven isolated startup gameplay required')
        v.verify_build(state.get('ue4ss_loader_manifest'))
    if purpose.startswith('control_'):
        if purpose.startswith('control_menu_'):
            import ahua_practice as practice
            owner,owned_state=practice.owned_session()
            if owned_state['state_file']!=state['state_file']:raise RuntimeError('Current menu transition session required')
            validate_control_menu_transition(owner,practice.log_path(state).read_text(encoding='utf-8',errors='replace'))
        proof=json.loads((v.ROOT/'evidence/latest-gameplay-save-isolation.json').read_text(encoding='utf-8'))
        if not proof.get('passed') or not state.get('boss_lifecycle_experiment') or not state.get('ue4ss_deployed'):
            raise RuntimeError('Declared bounded boss lifecycle experiment and proven save isolation required')
        v.verify_build(state.get('ue4ss_loader_manifest'))
    if purpose.startswith('observe_'):
        proof=json.loads((v.ROOT/'evidence/latest-gameplay-save-isolation.json').read_text(encoding='utf-8'))
        if not proof.get('passed') or not state.get('readonly_ai_experiment') or not state.get('ue4ss_deployed'):
            raise RuntimeError('Verified save isolation and declared read-only AI experiment required')
    if purpose.startswith('probe_'):
        # 用途：不能用这个入口跳过本轮备份、断网、无Mod和存档隔离测试准备。
        if not state.get('save_gameplay_allowed') or not state.get('gameplay_save_probe') or state.get('ue4ss_deployed'):
            raise RuntimeError('Original gameplay save-probe gate required')
        gate=Path(state['work'])/'gameplay-probe-allowed.json'
        if not gate.exists() or json.loads(gate.read_text(encoding='utf-8'))['state_file']!=str(v.state_path()):
            raise RuntimeError('Fresh gameplay snapshot gate required')
    ids={p['ProcessId'] for p in c.box_processes(dll) if p['Name'].lower()=='pbz.exe'}
    u=ctypes.WinDLL('user32',use_last_error=True);u.SetProcessDPIAware()
    cb=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    u.EnumWindows.argtypes=[cb,w.LPARAM];u.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
    u.GetClassNameW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int];u.IsWindowVisible.argtypes=[w.HWND]
    u.GetClientRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)];u.GetForegroundWindow.restype=w.HWND
    u.SetForegroundWindow.argtypes=[w.HWND];u.ClientToScreen.argtypes=[w.HWND,ctypes.POINTER(w.POINT)]
    u.WindowFromPoint.argtypes=[w.POINT];u.WindowFromPoint.restype=w.HWND
    u.GetCursorPos.argtypes=[ctypes.POINTER(w.POINT)];u.AttachThreadInput.argtypes=[w.DWORD,w.DWORD,w.BOOL]
    found=[]
    @cb
    def visit(h,l):
        pid=w.DWORD();u.GetWindowThreadProcessId(h,ctypes.byref(pid))
        if pid.value in ids and u.IsWindowVisible(h):
            name=ctypes.create_unicode_buffer(256);u.GetClassNameW(h,name,256);rect=w.RECT();u.GetClientRect(h,ctypes.byref(rect))
            # 用途：技能开发键可能同时触发游戏切换窗口；纯按键不依赖屏幕坐标，接受本研究窗口的有界尺寸。
            size_ok=(rect.right,rect.bottom)==(width,height)
            if purpose.startswith('control_') and not purpose.startswith('control_menu_'):
                size_ok=320<=rect.right<=7680 and 200<=rect.bottom<=4320
            if name.value.endswith(':UnrealWindow') and size_ok:found.append(h)
        return True
    u.EnumWindows(visit,0)
    if len(found)!=1 or not (0<=x<width and 0<=y<height):raise RuntimeError('Exact game window and dimensions not verified')
    h=found[0];front=u.GetForegroundWindow();other=u.GetWindowThreadProcessId(front,None) if front else 0
    own=ctypes.WinDLL('kernel32').GetCurrentThreadId();attached=False
    try:
        if other and other!=own:attached=bool(u.AttachThreadInput(own,other,True))
        u.SetForegroundWindow(h)
    finally:
        if attached:u.AttachThreadInput(own,other,False)
    time.sleep(.2)
    if u.GetForegroundWindow()!=h:
        # 用途：Windows可能限制后台激活；恢复唯一研究游戏窗口后再请求焦点。
        u.ShowWindow.argtypes=[w.HWND,ctypes.c_int]
        u.ShowWindow(h,9)
        u.keybd_event(18,0,0,0)
        u.keybd_event(18,0,2,0)
        u.SetForegroundWindow(h)
        time.sleep(.3)
    if u.GetForegroundWindow()!=h:raise RuntimeError('Game is not foreground')
    if purpose=='control_focus':
        return {'focused':True,'only_research_game_targeted':True,'input_sent':False}
    if positioning_key is not None:
        u.keybd_event(positioning_key,0,0,0)
        try:time.sleep(.75)
        finally:u.keybd_event(positioning_key,0,2,0)
        path=Path(state['work'])/'practice-position-actions.json'
        data=json.loads(path.read_text(encoding='utf-8'))if path.exists()else[]
        data.append({'at':v.utc8(),'purpose':purpose,'key':chr(positioning_key),'seconds':.75})
        v.save(path,data)
        return {'pressed':purpose,'seconds':.75,'only_research_game_targeted':True}
    if purpose in ('control_lab_next','control_lab_cast','control_target','control_skill5','control_skill8','control_skill9','control_look','control_enter','control_forward','control_skill','control_skill2','control_skill3','control_skill4','control_attack','control_exit'):
        if not state.get('control_probe_interactive') or time.time()>=state.get('control_probe_expires_at',0)-5:
            raise RuntimeError('Active interactive control probe grant required')
        if purpose=='control_look':
            # 用途：仅对已聚焦的限时研究窗口分帧右移60像素，验证真实鼠标输入；不提供任意输入接口。
            for _ in range(6):
                if u.GetForegroundWindow()!=h:raise RuntimeError('Research window lost focus')
                u.mouse_event(1,10,0,0,0);time.sleep(.04)
            return {'pressed':purpose,'relative_mouse_x':60,'only_research_game_targeted':True}
        if purpose.startswith('control_lab_'):
            owner=json.loads((v.ROOT/'runtime/ahua-practice.json').read_text(encoding='utf-8'))
            if not owner.get('skill_lab') or owner.get('phase')!='armed' or owner['state_file']!=state['state_file']:
                raise RuntimeError('Explicit current-session developer skill lab required')
        lab_cast=119 if purpose=='control_lab_cast' and owner.get('skill_lab_cast_key')=='F8' else 122
        key={'control_lab_next':120,'control_lab_cast':lab_cast,'control_target':118,'control_skill5':116,'control_skill8':119,'control_skill9':120,'control_enter':117,'control_forward':87,'control_skill':112,'control_skill2':113,'control_skill3':114,'control_skill4':115,'control_exit':121}.get(purpose)
        if skill_key_override is not None:key=skill_key_override
        if purpose=='control_attack':
            flags=registered_mouse or (2,4)
            u.mouse_event(flags[0],0,0,0,0)
            try:time.sleep(.08)
            finally:u.mouse_event(flags[1],0,0,0,0)
        else:
            u.keybd_event(key,0,0,0)
            try:time.sleep(.35 if purpose=='control_forward' else .08)
            finally:u.keybd_event(key,0,2,0)
        if cancel_after or death_after:
            # 用途：留出UE4SS输入轮询与游戏线程调度窗口；过短的80ms退出键曾未产生任何回调。
            # 原始日志可能延迟刷新；使用已有固定输入时序，事后逐实例验证真实活动取消。
            time.sleep(.20)
            if u.GetForegroundWindow()!=h:raise RuntimeError('Research window lost focus; cancellation input preserved')
            followup_key=123 if death_after else 121
            u.keybd_event(followup_key,0,0,0)
            try:time.sleep(.65 if registered_cancel or lab_cancel or death_after else .20)
            finally:u.keybd_event(followup_key,0,2,0)
        return {'pressed':purpose,'only_research_game_targeted':True}
    if purpose in ('observe_reload','control_reload'):
        if not state.get('readonly_hot_reload_enabled'):raise RuntimeError('Hot reload not declared')
        # 用途：只为此只读研究会话发送固定Ctrl+R，不提供任意按键接口。
        u.keybd_event(17,0,0,0)
        try:
            u.keybd_event(82,0,0,0);time.sleep(.12);u.keybd_event(82,0,2,0)
        finally:u.keybd_event(17,0,2,0)
        return {'pressed':'CTRL+R','only_research_game_targeted':True}
    if purpose in ('probe_pause','probe_interact','observe_pause','observe_interact','observe_globalmap','control_menu_pause'):
        # 普通玩家入口须先通过上方control_menu_完整恢复门槛，再发送一次固定Esc。
        # 用途：截图确认后，只发送一次Esc菜单键或E交互键；不提供任意按键执行入口。
        key=9 if purpose=='observe_globalmap' else 69 if purpose in ('probe_interact','observe_interact') else 27
        u.keybd_event(key,0,0,0);time.sleep(.08);u.keybd_event(key,0,2,0)
        path=Path(state['work'])/'settings-menu-actions.json'
        data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
        label='TAB' if key==9 else 'ESC' if key==27 else 'E'
        data.append({'at':v.utc8(),'purpose':purpose,'key':label,'gameplay_requested':True});v.save(path,data)
        return {'pressed':label,'only_research_game_targeted':True}
    point=w.POINT(x,y);u.ClientToScreen(h,ctypes.byref(point));pid=w.DWORD()
    u.GetWindowThreadProcessId(u.WindowFromPoint(point),ctypes.byref(pid))
    if pid.value not in ids:raise RuntimeError('Hit point belongs to a different application')
    old=w.POINT();u.GetCursorPos(ctypes.byref(old))
    u.SetCursorPos(point.x,point.y)
    time.sleep(.08)  # 用途：让游戏至少经过一帧，识别鼠标移入控件。
    if purpose=='observe_codex_down':
        # 用途：仅在截图确认的图鉴列表发送三格向下滚动，不提供任意输入注入。
        u.mouse_event(0x0800,0,0,ctypes.c_uint32(-360).value,0)
        u.SetCursorPos(old.x,old.y)
        return {'scrolled':'codex_down_three_notches','only_research_game_targeted':True}
    u.mouse_event(2,0,0,0,0)
    time.sleep(.08)  # 用途：按住80毫秒，避免逐帧采样漏掉瞬时点击。
    u.mouse_event(4,0,0,0,0)
    u.SetCursorPos(old.x,old.y)
    path=Path(state['work'])/'settings-menu-actions.json'
    data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    data.append({'at':v.utc8(),'purpose':purpose,'client_position':[x,y],'gameplay_requested':purpose.startswith('probe_')});v.save(path,data)
    return {'clicked':purpose,'only_research_game_targeted':True}


if __name__=='__main__':
    if len(sys.argv)!=6:raise RuntimeError('Use x y width height purpose after visual review')
    print(json.dumps(click(*map(int,sys.argv[1:5]),sys.argv[5])))
