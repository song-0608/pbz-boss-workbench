-- Exercise the actual session, arena and chooser composition with fake native
-- objects. No game, credentials, network rules or saves are accessed.
local root,candidate=assert(arg[1]),assert(arg[2])
local directory=candidate..'/PBZCoop/Scripts/'
local config=dofile(directory..'bwb_config.lua')
local checks=0
local function check(name,fn)fn();checks=checks+1;print('PASS '..name)end
local function fixture(with_ui,construction_error)
    local f={clock=0,keys={},timers={},logs={},fail_prepare=true,clean=true,valid=true,created=0,recovery_hosts=0}
    local grant={issued_at=os.time(),expires_at=os.time()+600,session_id='integration',role='host'}
    local scope={attest=function(_,restore)assert(restore or not f.expired);return grant end,
        revoke=function()f.expired=true end}
    local pc={};local peer={world='W',protocol={ready=false},refresh_local_body=function()return true end}
    local observer={bind_control_probe=function()
        assert(not f.probe);f.probe=true
        return function()f.probe=false;return true end
    end}
    local function layer()
        return {lock=function()f.locked=true;return true end,unlock=function()
            if f.unlock_error then return false end;f.locked=false;return true
        end}
    end
    local function host()
        return {on_game_thread=function(fn)fn()end,bind_key=function(key,fn)f.keys[key]=fn end,
            release_keys=function()
                if f.release_error then return false end
                f.keys={};f.releases=(f.releases or 0)+1;return true
            end,
            after_key_release=function(_,fn)f.released=fn end}
    end
    local n={prepare=function(id)
        if f.fail_prepare then error('no clearance')end
        return {world='W',profile={id=id}}
    end,protect=function()f.protected=true end,
        spawn=function(_,remember)local r={};remember(r);f.created=f.created+1;return r end,
        resolve=function(r)return r end,register_controller=function()end,readiness=function()return 'settled'end,
        suspend=function()end,release_initialization=function()end,
        restore_player=function()f.protected=false;return true end,destroy=function()return not f.destroy_failure end,
        now=function()return f.clock end,log=function(message)f.logs[#f.logs+1]=message end,
        schedule=function(ms,fn)
            assert(ms==250);local t={active=true,fn=fn};f.timers[#f.timers+1]=t
            return function()t.active=false;if f.cancel_error then error('timer cancellation failed')end end
        end}
    n.recovery_menu=function()
        assert(f.clean);f.recovery_hosts=f.recovery_hosts+1
        return host(),layer(),pc,function()return f.valid end
    end
    n.create_control=function(_,context)
        local h=host();local c={session={state='OFF'}}
        c.session.restore=function()return true end
        c.observed_body=function()return nil end
        c.runtime={stop=function()
            if not f.clean then c.session.receipt={};return false end
            if h.workbench then h.workbench:shutdown()end
            return true
        end}
        c.start=function()return true end
        n.mount_workbench(c,h,layer(),pc,context.profile.id)
        return c
    end
    local launch={assembly={bindings={workbench_ui=with_ui and {}or nil}},lease_provider=function()return grant end,
        role='host',session='integration',issued_at=grant.issued_at,expires_at=grant.expires_at}
    local env=setmetatable({dofile=function(path)
        if path==directory..'bwb_online_scope.lua'then return {new=function()return scope end}end
        if path==directory..'bwb_spawn_native.lua'then return {new=function()return n end}end
        if path==directory..'bwb_workbench_native.lua'then return {new=function()return {
            render=function()return true end,close=function()
                f.ui_closes=(f.ui_closes or 0)+1
                if f.ui_error then error('native widget still owned')end;return true
            end}end}end
        return dofile(path)
    end},{__index=_G})
    local Session=assert(loadfile(root..'/tools/phantom_boss_online_session.lua','t',env))()
    local function mount()
        if construction_error then
            launch.assembly.bindings.workbench_ui={}
        end
        return Session.new({},launch,config,peer,observer,directory,{print=function(s)f.logs[#f.logs+1]=s end},function(owner)
            f.published=owner;return true
        end)
    end
    if construction_error then
        -- Fail a later private dependency, after the arena owner exists.
        launch.assembly.bindings.visual={}
        local original=env.dofile
        env.dofile=function(path)
            if path==directory..'bwb_visual_session.lua'then return {attach=function()error('visual attachment failed')end}end
            return original(path)
        end
        f.mount=mount
    else f.arena=mount()end
    f.peer=peer
    function f:tick(count)
        for _=1,count or 1 do
            self.clock=self.clock+.25
            local timers={};for i,t in ipairs(self.timers)do timers[i]=t end
            for _,t in ipairs(timers)do if t.active then t.fn()end end
        end
    end
    function f:retry()
        self.keys.INS();self.keys.DOWN_ARROW();self.keys.RETURN();self.released()
    end
    return f
end
check('initial terrain rejection mounts one recovery chooser with no temporary Boss',function()
    local f=fixture();assert(not f.peer:select_boss('ahua_guitoudao'))
    assert(f.arena.state=='REJECTED'and f.keys.INS and f.recovery_hosts==1 and f.created==0 and not f.protected)
end)
check('repeated terrain rejection reuses the same recovery owner',function()
    local f=fixture();assert(not f.peer:select_boss('ahua_guitoudao'))
    for _=1,3 do f:retry();assert(f.arena.state=='REJECTED'and not f.locked)end
    assert(f.recovery_hosts==1 and #f.timers==1 and f.created==0)
end)
check('explicit recovery selection mounts a real runtime and retires recovery timer',function()
    local f=fixture();assert(not f.peer:select_boss('ahua_guitoudao'))
    local recovery_timer=f.timers[1];f.fail_prepare=false;f:retry();f:tick(13)
    assert(f.arena.state=='READY'and f.arena.context.profile.id=='057_wanjun'and not recovery_timer.active)
    assert(f.created==1 and f.releases==1 and not f.locked and not f.protected and f.probe)
end)
check('clean initialization timeout returns to the same retryable chooser',function()
    local f=fixture();assert(not f.peer:select_boss('ahua_guitoudao'))
    f.fail_prepare=false;f:retry();f.arena.polls=64;f:tick()
    assert(f.arena.state=='REJECTED'and f.keys.INS and f.recovery_hosts==1 and not f.protected)
    f:retry();f:tick(13);assert(f.arena.state=='READY')
end)
check('scope revocation cancels recovery routes timer and menu input',function()
    local f=fixture();assert(not f.peer:select_boss('ahua_guitoudao'));f.keys.INS();assert(f.locked)
    assert(f.arena:revoke('closed')and not f.locked and next(f.keys)==nil and not f.timers[1].active)
    assert(not pcall(f.peer.select_boss,f.peer,'057_wanjun'))
end)
check('unrestored control faults without mounting another chooser or spawning',function()
    local f=fixture();f.fail_prepare=false;assert(f.peer:select_boss('ahua_guitoudao'));f:tick(13)
    f.clean=false;assert(not f.peer:select_boss('057_wanjun'))
    assert(f.arena.state=='FAULTED'and f.recovery_hosts==0 and f.created==1 and f.probe)
end)
check('lost native player retires recovery without automatic retry or takeover',function()
    local f=fixture();assert(not f.peer:select_boss('ahua_guitoudao'));f.keys.INS()
    f.valid=false;f:tick();assert(next(f.keys)==nil and not f.locked and f.created==0 and not f.timers[1].active)
end)
check('failed cleanup during a retry retires chooser keys instead of accepting another request',function()
    local f=fixture();assert(not f.peer:select_boss('ahua_guitoudao'))
    f.fail_prepare=false;f:retry();f.destroy_failure=true;f.arena.polls=64;f:tick()
    assert(f.arena.state=='FAULTED'and next(f.keys)==nil and not f.locked)
    for _,timer in ipairs(f.timers)do assert(not timer.active)end
    local created=f.created;assert(not f.peer:select_boss('057_wanjun')and f.created==created)
end)
check('recovery timer cancellation failure still unlocks input and faults the actual assembly',function()
    local f=fixture();assert(not f.peer:select_boss('ahua_guitoudao'));f.keys.INS();f.cancel_error=true
    assert(not f.arena:revoke('closed')and f.arena.state=='FAULTED')
    assert(not f.locked and next(f.keys)==nil and not f.timers[1].active)
    f.cancel_error=false;assert(f.arena:stop('retry menu cleanup')and f.arena.state=='IDLE')
end)
check('failed recovery key removal cannot retain the menu barrier or accept stale actions',function()
    local f=fixture();assert(not f.peer:select_boss('ahua_guitoudao'));f.keys.INS()
    local stale=f.keys.INS;f.release_error=true
    assert(not f.arena:revoke('closed')and f.arena.state=='FAULTED'and not f.locked)
    stale();assert(not f.locked and f.created==0)
    f.release_error=false;assert(f.arena:stop('retry key cleanup')and next(f.keys)==nil)
end)
check('idle widget revocation failure cannot be hidden by successful empty Actor cleanup',function()
    local f=fixture(true);f.ui_error=true
    assert(not f.arena:revoke('closed')and f.arena.state=='FAULTED'and f.created==0)
    assert(f.arena.failure:find('workbench recovery',1,true))
    f.ui_error=false;assert(f.arena:stop('retry widget cleanup')and f.arena.state=='IDLE')
end)
check('unremoved native menu retains controlled Actor recovery until all owners acknowledge',function()
    local f=fixture(true);f.fail_prepare=false;assert(f.peer:select_boss('ahua_guitoudao'));f:tick(13)
    f.ui_error=true;assert(not f.arena:revoke('closed')and f.arena.state=='FAULTED')
    assert(f.arena.control and f.probe and f.arena.context)
    f.ui_error=false;assert(f.arena:stop('retry menu and control')and f.arena.state=='IDLE'and not f.probe)
end)
check('retrying an assembly fault cannot forget a recovery menu whose keys remain registered',function()
    local f=fixture();assert(not f.peer:select_boss('ahua_guitoudao'))
    f.fail_prepare=false;f:retry();f.destroy_failure=true;f.release_error=true;f.arena.polls=64;f:tick()
    assert(f.arena.state=='FAULTED'and next(f.keys)~=nil and not f.locked)
    f.destroy_failure=false;assert(not f.arena:stop('retry native cleanup')and f.arena.state=='FAULTED')
    f.release_error=false;assert(f.arena:stop('retry key cleanup')and f.arena.state=='IDLE'and next(f.keys)==nil)
end)
check('public status distinguishes idle assembly from retired World activation without exposing mutable ownership',function()
    local f=fixture();local status=f.peer:assembly_status()
    assert(status.state=='IDLE'and status.activation_state=='ACTIVE'and not status.restore_pending)
    f.peer.world_transition={previous='W',observed='NewW'};f.peer.revoked_reason='world changed'
    assert(f.arena:revoke('world changed'));status=f.peer:assembly_status()
    assert(status.state=='IDLE'and status.activation_state=='RETIRED'and status.reason=='world changed')
    assert(status.world_transition.previous=='W'and status.world_transition.observed=='NewW')
    status.world_transition.observed='tampered';assert(f.peer:assembly_status().world_transition.observed=='NewW')
    assert(status.source_only and status.runtime_acceptance_current==false)
end)
check('public recovery status takes priority over a retired activation until native cleanup succeeds',function()
    local f=fixture(true);f.peer.revoked_reason='world changed';f.ui_error=true
    assert(not f.arena:revoke('world changed'));local status=f.peer:assembly_status()
    assert(status.state=='FAULTED'and status.activation_state=='RECOVERY_PENDING'and status.restore_pending)
    assert(status.reason:find('workbench recovery',1,true))
    f.ui_error=false;assert(f.arena:stop('retry'));status=f.peer:assembly_status()
    assert(status.activation_state=='RETIRED'and not status.restore_pending)
    f.peer.restore_pending=true;assert(f.peer:assembly_status().activation_state=='RECOVERY_PENDING')
end)
check('public status exposes control observation and runtime cleanup pending before assembly faults',function()
    local f=fixture();f.fail_prepare=false;assert(f.peer:select_boss('ahua_guitoudao'));f:tick(13)
    local c=f.arena.control;assert(c and f.arena.state=='READY')
    c.session.online_restore_pending=true;c.session.online_restore_reason='observation pending'
    local status=f.peer:assembly_status()
    assert(status.activation_state=='RECOVERY_PENDING'and status.reason=='observation pending')
    c.session.online_restore_pending=false;c.runtime.online_stop_pending=true
    assert(f.peer:assembly_status().restore_pending)
    c.runtime.online_stop_pending=false;assert(f.peer:assembly_status().activation_state=='ACTIVE')
    c.runtime.online_stopped=true;assert(f.peer:assembly_status().activation_state=='RETIRED')
end)
check('partial optional attachment publishes the actual arena before construction can fail',function()
    local f=fixture(true,true);local ok,why=pcall(f.mount)
    assert(not ok and why:find('visual attachment failed',1,true)and f.published and not f.arena)
    assert(f.published:revoke('failed construction')and f.published.state=='IDLE'and f.created==0)
end)
print('PASS '..checks..' online session groups; actual orchestration with fake native objects, no game started')
