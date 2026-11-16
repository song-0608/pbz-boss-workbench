local root=assert(arg[1]);local checks=0
local function check(name,fn)fn();checks=checks+1;print('PASS '..name)end
local function fixture(role)
    local s={cancelled=0,closed=0,invalidated=0,stopped=0,revoked=0,received=0,ticks=0}
    local visual={receive=function(_,line,sender)s.received=s.received+1;s.sender=sender;return true end,
        tick=function()s.ticks=s.ticks+1 end,
        close=function()s.closed=s.closed+1;return not s.cleanup_error end,
        invalidate=function()s.invalidated=s.invalidated+1;return not s.cleanup_error end}
    local api={coop={handlers={},net={enabled=true,role=role=='guest' and 'client' or 'host'},
        sendEvent=function()end,linked=function()return not s.disconnected end}}
    local arena={stop=function()s.stopped=s.stopped+1;return not s.control_error end,
        revoke=function(self,reason)s.revoked=s.revoked+1;return self:stop(reason)end}
    local env=setmetatable({dofile=function(path)
        if path=='candidate/bwb_visual_native.lua' then return {new=function()return {animations={},sample=function()end}end}end
        assert(path=='candidate/bwb_visual.lua');return {EVENT='BWV1',new=function(options)s.options=options;return visual end}
    end},{__index=_G})
    local module=assert(loadfile(root..'/tools/phantom_boss_visual_session.lua','t',env))()
    local g={LoopInGameThreadWithDelay=function(ms,fn)assert(ms==50);s.callback=fn;return 9 end,
        CancelDelayedAction=function(h)assert(h==9);s.cancelled=s.cancelled+1 end}
    local peer={protocol={}};local observer={now=function()return 1 end,log=function()end}
    s.service=module.attach(api,{},peer,observer,{}, {},{role=role or 'host',session='S',bosses={}},arena,'candidate/',g)
    s.api,s.arena,s.peer=api,arena,peer
    return s
end
check('cosmetic callbacks are installed only once with a cancellable fifty millisecond cadence',function()
    local s=fixture();assert(s.peer.visual==s.service and s.api.coop.handlers.BWV1)
    s.callback();assert(s.ticks==1);assert(s.service:close());s.callback()
    assert(s.ticks==1 and s.cancelled==1 and not s.api.coop.handlers.BWV1)
end)
check('slot role and fixed two-player transport are enforced before visual parsing',function()
    local s=fixture();local handler=s.api.coop.handlers.BWV1
    assert(not handler('x',1) and handler('x',2) and s.sender=='guest')
    for _,key in ipairs({'party','pvp'})do s.api.coop.net[key]=true;assert(not handler('x'));s.api.coop.net[key]=nil end
    s.api.coop.net.enabled=false;assert(not handler('x'));s.api.coop.net.enabled=true
    s.disconnected=true;assert(not handler('x'));s.disconnected=false;s.peer.closed=true;assert(not handler('x'))
    s=fixture('guest');handler=s.api.coop.handlers.BWV1
    assert(not handler('x',2) and handler('x') and s.sender=='host')
end)
check('Boss switching retires cosmetics and still restores local control if cosmetic cleanup fails',function()
    local s=fixture();s.cleanup_error=true
    local ok,why=s.arena:stop('selection');assert(not ok and why=='visual recovery remains pending')
    assert(s.stopped==1 and s.invalidated==1 and s.closed==0)
end)
check('revocation stops scheduler removes handler and restores both owned lifecycles',function()
    local s=fixture();assert(s.arena:revoke('expired'))
    assert(s.closed==1 and s.invalidated==1 and s.revoked==1 and s.stopped==1 and s.cancelled==1)
    assert(not s.api.coop.handlers.BWV1);s.callback();assert(s.ticks==0)
end)
check('failed cosmetic recovery stays observable and can be retried without replacing another handler',function()
    local s=fixture();s.cleanup_error=true;assert(not s.arena:revoke('disconnect'))
    local replacement=function()end;s.api.coop.handlers.BWV1=replacement
    s.cleanup_error=false;assert(s.service:close());assert(s.api.coop.handlers.BWV1==replacement and s.cancelled==1)
end)
print('PASS '..checks..' visual session groups; lifecycle integration with fake transport, no game started')
