local root=assert(arg[1]);local Arena=dofile(root..'/tools/phantom_boss_online_arena.lua')
local checks=0
local function check(name,fn)fn();checks=checks+1;print('PASS '..name)end
local function fixture()
    local f={clock=0,events={},timers={},destroyed={},restored=0,controls=0,revoked=false,signature='settled'}
    local function event(s)f.events[#f.events+1]=s end
    local scope={attest=function(_,restore)assert(restore or not f.revoked);return {mode='two-player-online-research'}end,
        revoke=function()f.revoked=true end}
    local peer={world='W'}
    local observer={bind_control_probe=function(probe)
        assert(not f.probe);f.probe=probe
        return function()assert(f.probe()==nil);f.probe=nil;return true end
    end}
    local n={prepare=function(id)event('prepare');assert(id=='boss');return {world=f.world or 'W'}end,
        protect=function()event('protect');f.protected=true end,
        spawn=function(c,remember)
            local record={id='body'};remember(record);event('spawn');assert(f.arena.owned[1]==record)
            if f.spawn_failure then error('partial deferred construction')end;return record
        end,
        resolve=function(o)event('resolve');return o end,
        register_controller=function(body,c,remember)
            if not c.ai then c.ai=true;remember({id='ai'});event('register_ai')end
        end,
        readiness=function()event('readiness');return f.signature end,
        suspend=function()event('suspend');if f.suspend_failure then error('AI restart')end end,
        release_initialization=function()event('release');if f.release_failure then error('faction changed')end end,
        restore_player=function()event('restore');f.restored=f.restored+1;f.protected=false;return true end,
        create_control=function()
            event('control');f.controls=f.controls+1
            local control={session={}}
            function control:start()event('start');f.running=true;return not f.start_failure end
            function control:observed_body()return f.running and f.active_body or nil end
            control.runtime={stop=function()
                event('stop');if f.restore_failure then control.session.receipt={};return false end
                f.running=false;control.session.receipt=nil;return true
            end}
            return control
        end,
        destroy=function(o)
            event('destroy_'..o.id);if f.destroy_failure==o.id then error('destroy unreadable')end
            f.destroyed[o.id]=true;return true
        end,
        schedule=function(ms,fn)
            assert(ms==250);if f.schedule_failure then error('missing scheduler')end
            local timer={fn=fn,active=true};f.timers[#f.timers+1]=timer
            return function()timer.active=false;event('cancel')end
        end,
        now=function()return f.clock end,log=function()end}
    f.scope,f.peer,f.observer=scope,peer,observer
    f.arena=Arena.new(scope,peer,observer,n)
    function f:tick(n)
        local timer=self.timers[#self.timers]
        for i=1,n or 1 do self.clock=self.clock+0.25;if timer.active then timer.fn()end end
    end
    return f
end
check('deferred ownership is remembered before a partial construction failure',function()
    local f=fixture();f.spawn_failure=true;assert(not f.arena:start('boss'))
    assert(f.arena.state=='REJECTED' and f.destroyed.body and not f.protected and f.controls==0)
end)
check('only stable initialized grants expose controls after AI suspension and player restoration',function()
    local f=fixture();assert(f.arena:start('boss'));f:tick(12)
    assert(f.controls==0 and f.protected);f:tick()
    assert(f.arena.state=='READY' and f.controls==1 and not f.protected and f.probe and not f.timers[1].active)
    assert(table.concat(f.events,','):find('suspend,release,restore,control,start,cancel',1,true))
end)
check('changing or missing readiness restarts the stability observation',function()
    local f=fixture();f.arena:start('boss');f:tick(10);f.signature=nil;f:tick()
    f.signature='changed';f:tick(12);assert(f.controls==0);f:tick();assert(f.controls==1)
end)
check('initial World mismatch rejects before applying protection or spawning',function()
    local f=fixture();f.world='elsewhere';assert(not f.arena:start('boss'))
    assert(not table.concat(f.events,','):find('protect',1,true) and not f.destroyed.body)
end)
check('World changes during initialization cancel the timer and clean owned actors',function()
    local f=fixture();f.arena:start('boss');f:tick();f.peer.world='new';f:tick()
    assert(f.arena.state=='REJECTED' and f.destroyed.body and f.destroyed.ai and not f.protected)
end)
check('initialization never retries or creates extra Bosses after its poll budget',function()
    local f=fixture();f.signature=nil;f.arena:start('boss');f:tick(65)
    assert(f.arena.state=='REJECTED' and f.arena.polls==64 and f.controls==0 and #f.timers==1)
    local count=#f.events;f.timers[1].fn();assert(#f.events==count)
end)
check('suspension and faction-release failures clean before controls become accessible',function()
    for _,key in ipairs({'suspend_failure','release_failure'})do
        local f=fixture();f[key]=true;f.arena:start('boss');f:tick(13)
        assert(f.arena.state=='REJECTED' and f.controls==0 and f.destroyed.ai and f.destroyed.body and not f.protected)
    end
end)
check('partial runtime startup failure stops controls and detaches its observer',function()
    local f=fixture();f.start_failure=true;f.arena:start('boss');f:tick(13)
    assert(f.arena.state=='REJECTED' and not f.running and not f.probe and f.destroyed.body)
end)
check('unverified native restoration preserves its recovery receipt, actors and observer',function()
    local f=fixture();f.arena:start('boss');f:tick(13);f.restore_failure=true;f.active_body={}
    assert(not f.arena:stop('disconnect') and f.arena.state=='FAULTED')
    assert(f.arena.control.session.receipt and f.probe and not f.destroyed.body and not f.destroyed.ai)
    f.restore_failure=false;assert(f.arena:stop('retry cleanup') and not f.probe and f.destroyed.body)
end)
check('one failed owned destruction still attempts the other Actor and original player restoration',function()
    local f=fixture();f.arena:start('boss');f:tick();f.destroy_failure='ai'
    assert(not f.arena:stop('close') and f.arena.state=='FAULTED')
    assert(f.destroyed.body and not f.protected and f.restored>0 and #f.arena.owned==2)
end)
check('revocation cancels queued initialization and cannot start another takeover',function()
    local f=fixture();f.arena:start('boss');f:tick();assert(f.arena:revoke('expired'))
    assert(f.revoked and f.arena.state=='IDLE' and not f.protected)
    local count=#f.events;f.timers[1].fn();assert(#f.events==count)
    assert(not pcall(f.arena.start,f.arena,'boss'))
end)
check('retired timer cannot interfere with a new clean assembly',function()
    local f=fixture();f.arena:start('boss');f:tick();local old=f.timers[1].fn
    assert(f.arena:stop('change Boss'));assert(f.arena:start('boss'))
    local count=#f.events;old();assert(#f.events==count and f.arena.state=='INITIALIZING')
    f:tick(13);assert(f.arena.state=='READY')
end)
check('scheduler failure performs cleanup without leaving an inaccessible actor',function()
    local f=fixture();f.schedule_failure=true;assert(not f.arena:start('boss'))
    assert(f.destroyed.body and not f.protected and f.arena.state=='REJECTED')
end)
check('closed or unrecovered peer never begins native assembly',function()
    for _,key in ipairs({'closed','restore_pending'})do
        local f=fixture();f.peer[key]=true;assert(not pcall(f.arena.start,f.arena,'boss') and #f.events==0)
    end
end)
print('PASS '..checks..' online arena groups; simulated lifecycle, no engine/game/relay')
