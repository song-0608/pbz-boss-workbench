-- Exercise the actual session, arena and chooser composition with fake native
-- objects. No game, credentials, network rules or saves are accessed.
local root,candidate=assert(arg[1]),assert(arg[2])
local directory=candidate..'/PBZCoop/Scripts/'
local config=dofile(directory..'bwb_config.lua')
local checks=0
local function check(name,fn)fn();checks=checks+1;print('PASS '..name)end
local function fixture()
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
        return {lock=function()f.locked=true;return true end,unlock=function()f.locked=false;return true end}
    end
    local function host()
        return {on_game_thread=function(fn)fn()end,bind_key=function(key,fn)f.keys[key]=fn end,
            release_keys=function()f.keys={};f.releases=(f.releases or 0)+1;return true end,
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
            return function()t.active=false end
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
    local launch={assembly={bindings={}},lease_provider=function()return grant end,
        role='host',session='integration',issued_at=grant.issued_at,expires_at=grant.expires_at}
    local env=setmetatable({dofile=function(path)
        if path==directory..'bwb_online_scope.lua'then return {new=function()return scope end}end
        if path==directory..'bwb_spawn_native.lua'then return {new=function()return n end}end
        return dofile(path)
    end},{__index=_G})
    local Session=assert(loadfile(root..'/tools/phantom_boss_online_session.lua','t',env))()
    f.arena=Session.new({},launch,config,peer,observer,directory,{print=function(s)f.logs[#f.logs+1]=s end})
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
print('PASS '..checks..' online session groups; actual orchestration with fake native objects, no game started')
