local root,candidate=assert(arg[1]),assert(arg[2])
local directory=candidate..'/PBZCoop/Scripts/'
local dependencies=dofile(directory..'bwb_local_dependencies.lua')(directory)
local Control=dofile(directory..'bwb_online_control.lua')
local Scope=dofile(directory..'bwb_online_scope.lua')
-- Reuse the existing native-bridge fake UObject fixture, including its real
-- reciprocal Possess/view/ability readbacks. Execute no existing offline tests.
local file=assert(io.open(root..'/tests/test_native_bridge.lua','rb'));local raw=file:read('a');file:close()
local marker='\nlocal function test(name, fn)'
local at=assert(raw:find(marker,1,true));assert(not raw:find(marker,at+1,true))
local environment=setmetatable({arg={root},package={path=''},require=dependencies.require},{__index=_G})
local fixture=assert(load(raw:sub(1,at-1)..'\nreturn fixture\n','@pinned_native_fixture','t',environment))()
local checks=0
local function check(name,fn)fn();checks=checks+1;print('PASS '..name)end
local function env()
    local f=fixture();f.refreshes,f.transitions,f.keys,f.queue=0,0,{},{}
    f.profile.exe_sha256=string.rep('a',64);f.profile.instance_name=f.boss:GetFullName()
    f.lease={mode='two-player-online-research',isolated=true,issued_at=100,expires_at=200,
        session_id='research',role='host',exe_sha256=f.profile.exe_sha256,
        catalog_sha256=string.rep('b',64),upstream_commit=string.rep('c',40)}
    f.scope=Scope.new(function()return f.lease end,f.lease,function()return f.clock end)
    f.api.usable=function(o)return o:IsValid()end
    f.api.owned_temporary={boss=f.bridge.calls:reference(f.boss),ai=f.bridge.calls:reference(f.ai)}
    local peer={owned={},protocol={ready=true},closed=false}
    function peer:is_boss_class(path)return path=='/Fixture/Ahua.BP_Ahua_C'end
    function peer:resolve_local_action(path,id)
        if self:is_boss_class(path) and id=='attack' then return '/Fixture/Attack.GA_Attack_C' end
    end
    for key,kind in pairs({boss='local_body',ai='controller'})do
        local ref=f.api.owned_temporary[key]
        peer.owned[ref.address]={address=ref.address,name=ref.name,class=ref.class,world='W',kind=kind}
    end
    function peer:exclude(o,addr)
        local row=self.owned[addr]
        return row and row.name==o:GetFullName() and row.class==o:GetClass():GetFullName() or false
    end
    function peer:begin_local_transition(row)
        assert(row and row.kind=='local_body' and not self.local_transition)
        self.local_transition={};f.transitions=f.transitions+1;self.protocol.ready=false
        return self.local_transition
    end
    function peer:refresh_local_body()f.refreshes=f.refreshes+1;return not f.observation_failed end
    function peer:finish_local_transition(token)
        assert(self.local_transition==token);self.local_transition=nil
        return self:refresh_local_body()
    end
    local host={on_game_thread=function(fn)f.queue[#f.queue+1]=fn end,
        bind_key=function(key,fn)f.keys[key]=fn end,every_frame=function(fn)f.frame=fn;return 1 end,
        cancel_frame=function()f.cancelled=true end,release_keys=function()f.keys={}end,
        read_input=function()return {allowed=false}end,log=function()end}
    local config={expected_exe_sha256=f.profile.exe_sha256,controls={enter='F6',exit='F10'},
        skills={slot1={id='attack',key='F1',verified=true}}}
    f.peer=peer;f.control=Control.new(f.api,f.profile,config,f.scope,peer,host,dependencies)
    f.config,f.host=config,host
    f.session,f.bridge=f.control.session,f.control.bridge
    return f
end
check('private dependency loader ignores poisoned global require cache',function()
    local old=package.loaded.control_bridge;package.loaded.control_bridge={new=function()error('poisoned')end}
    local isolated=dofile(directory..'bwb_local_dependencies.lua')(directory)
    assert(isolated.Bridge~=package.loaded.control_bridge and isolated.Bridge==isolated.require('control_bridge'))
    assert(not pcall(isolated.require,'../outside'));package.loaded.control_bridge=old
end)
check('online context and native possession use no offline attestation',function()
    local f=env();local context=f.bridge:context()
    assert(context.mode=='two-player-online-research' and context.offline==nil and f.api.attest().offline==nil)
    assert(f.session:enter() and f.pc.Pawn==f.boss and not f.brain.running)
    assert(f.transitions==1 and f.refreshes==1 and not f.peer.local_transition)
    f.peer.protocol.ready=true
    assert(f.session:restore('F10') and f.pc.Pawn==f.player and f.ai.Pawn==f.boss and f.brain.running)
end)
check('missing peer handshake or owned actor registration refuses before native mutation',function()
    local f=env();f.peer.protocol.ready=false;assert(not f.session:enter() and #f.mutations==0)
    f=env();f.peer.owned[f.boss:GetAddress()]=nil;assert(not f.session:enter() and #f.mutations==0)
end)
check('skill stays gated during body acknowledgement without granting another ability',function()
    local f=env();assert(f.session:enter());assert(not f.session:skill('slot1') and not f.activation_calls)
    f.peer.protocol.ready=true;assert(f.session:skill('slot1') and f.activation_calls==1)
    assert(f.control:revoke('disconnect') and f.spec.ActiveCount==0 and f.pc.Pawn==f.player)
end)
check('expiry permits only restoration of the existing native receipt within cleanup grace',function()
    local f=env();assert(f.session:enter());f.clock=201
    assert(f.control:revoke('expired') and f.session.state=='OFF' and f.pc.Pawn==f.player)
    assert(not f.control.runtime.running and not f.session:enter())
    assert(f.lease.expires_at==200 and f.lease.offline==nil)
end)
check('partial Possess failure restores native ownership and clears transition state',function()
    local f=env();f.fail_takeover=true;assert(not f.session:enter())
    assert(f.session.state=='OFF' and f.pc.Pawn==f.player and f.ai.Pawn==f.boss and not f.peer.local_transition)
end)
check('post-possession snapshot failure restores but is not reported as verified online readiness',function()
    local f=env();f.observation_failed=true;assert(not f.session:enter())
    assert(f.pc.Pawn==f.player and f.ai.Pawn==f.boss and not f.peer.local_transition)
    assert(not f.bridge.online_restoring)
end)
check('cleanup deadline or lease identity mutation keeps a failed receipt visible',function()
    local f=env();assert(f.session:enter());f.clock=216
    assert(not f.control:revoke('too late') and f.session.state=='FAULTED' and f.session.receipt)
    assert(not f.bridge.online_restoring)
    f=env();assert(f.session:enter());f.lease.role='guest'
    assert(not f.control:revoke('identity changed') and f.session.receipt and f.pc.Pawn==f.boss)
end)
check('runtime dispatch stops queued skills after the online scope is revoked',function()
    local f=env();assert(f.control:start());f.keys.F6();f.queue[1]();f.peer.protocol.ready=true
    f.keys.F1();assert(f.control:revoke('shutdown'));f.queue[2]()
    assert(not f.activation_calls and f.pc.Pawn==f.player and f.session.state=='OFF' and f.cancelled)
end)
check('class and action profiles cannot expand the pinned online whitelist',function()
    local f=env();f.profile.class_path='/Arbitrary/Boss.Boss_C'
    assert(not pcall(Control.new,f.api,f.profile,f.config,f.scope,f.peer,f.host,dependencies) and #f.mutations==0)
    f=env();f.profile.skills.attack.class_path='/Arbitrary/Attack.Attack_C'
    assert(not pcall(Control.new,f.api,f.profile,f.config,f.scope,f.peer,f.host,dependencies) and #f.mutations==0)
end)
check('scope and profile build mismatch is rejected before registering runtime controls',function()
    local f=env();f.profile.exe_sha256=string.rep('f',64);f.config.expected_exe_sha256=f.profile.exe_sha256
    assert(not pcall(Control.new,f.api,f.profile,f.config,f.scope,f.peer,f.host,dependencies))
    assert(#f.mutations==0 and next(f.keys)==nil)
end)
local function remote_env()
    local f=env();local remote={}
    function remote:capture()return {}end
    function remote:apply(t)t.active=true end
    function remote:verify(t)return t.active and f.pc.Pawn==f.player and f.ai.Pawn==f.boss end
    function remote:brain_suspended()return not f.brain.running end
    function remote:restore(t)t.active=false;t.restored=true end
    f.bridge.api.remote=remote
    return f
end
check('retained AI control publishes Boss body without possessing the player Pawn',function()
    local f=remote_env();assert(f.control:observed_body()==nil)
    assert(f.session:enter() and f.pc.Pawn==f.player and f.ai.Pawn==f.boss)
    local row=f.control:observed_body()
    assert(row.verified and row.body==f.boss and row.controller==f.ai and row.player==f.player and row.player_controller==f.pc)
    assert(f.session:restore('F10') and f.control:observed_body()==nil)
    for _,event in ipairs(f.mutations)do assert(not event:find('possess:',1,true))end
end)
check('remote observation refuses a broken control receipt or expired action scope',function()
    local f=remote_env();assert(f.session:enter());f.ai.Pawn=f.player
    assert(not pcall(f.control.observed_body,f.control))
    f.ai.Pawn=f.boss;f.clock=201;assert(not pcall(f.control.observed_body,f.control))
    assert(f.control:revoke('expired') and f.control:observed_body()==nil)
end)
check('possession mode remains observable through native Pawn and requires no override',function()
    local f=env();assert(f.session:enter() and f.pc.Pawn==f.boss)
    assert(f.control:observed_body()==nil and f.session:restore('F10'))
end)
check('failed restore observation blocks takeover until an explicit successful recovery',function()
    local f=env();assert(f.session:enter());f.observation_failed=true
    assert(not f.session:restore('F10') and f.pc.Pawn==f.player and not f.session.receipt)
    assert(f.session.state=='FAULTED' and f.session.online_restore_pending)
    f.peer.protocol.ready=true;local count=#f.mutations
    assert(not f.session:enter() and #f.mutations==count)
    f.observation_failed=false;local refreshes=f.refreshes
    assert(f.session:restore('retry observation') and f.refreshes==refreshes+1)
    assert(f.session.state=='OFF' and not f.session.online_restore_pending)
    f.peer.protocol.ready=true;assert(f.session:enter())
end)
check('retired or recovering peer rejects takeover and skills even with a stale ready flag',function()
    for _,key in ipairs({'closed','revoking','revoked_reason','restore_pending','world_transition'})do
        local f=env();f.peer[key]=true
        assert(not f.session:enter() and #f.mutations==0,key)
        f=env();assert(f.session:enter());f.peer.protocol.ready=true;f.peer[key]=true
        assert(not f.session:skill('slot1') and not f.activation_calls,key)
    end
end)
check('successful restoration publishes exactly one refreshed local body',function()
    local f=env();assert(f.session:enter());local refreshes=f.refreshes
    assert(f.session:restore('F10') and f.refreshes==refreshes+1)
end)
local function running_env()
    local f=env();assert(f.control:start());f.keys.F6();f.queue[1]();f.peer.protocol.ready=true
    f.keys.F1();f.host.workbench={shutdown=function()f.menu_cleanups=(f.menu_cleanups or 0)+1;return true end}
    return f
end
check('key release exception cannot skip frame menu or player restoration',function()
    local f=running_env();local release=f.host.release_keys
    f.host.release_keys=function()error('keys still registered')end
    assert(not f.control.runtime:stop('stop') and f.cancelled and f.menu_cleanups==1 and f.pc.Pawn==f.player)
    assert(f.control.runtime.online_stop_pending and not f.control.runtime.running)
    f.queue[2]();assert(not f.activation_calls)
    local count=#f.mutations;f.peer.protocol.ready=true
    assert(not f.session:enter() and not f.control:start() and #f.mutations==count)
    f.host.release_keys=release;assert(f.control.runtime:stop('retry') and next(f.keys)==nil)
    assert(not f.control.runtime.online_stop_pending)
end)
check('failed frame cancellation retains its handle while queued callbacks stay inert',function()
    local f=running_env();local cancel=f.host.cancel_frame
    f.host.cancel_frame=function()error('timer still owned')end
    assert(not f.control.runtime:stop('stop') and f.control.runtime.frame_handle==1)
    assert(f.menu_cleanups==1 and f.pc.Pawn==f.player)
    f.frame();f.queue[2]();assert(not f.activation_calls)
    f.host.cancel_frame=cancel;assert(f.control.runtime:stop('retry') and f.cancelled)
    assert(f.control.runtime.frame_handle==nil)
end)
check('menu rejection or exception still restores player and remains explicitly retryable',function()
    for _,throws in ipairs({false,true})do
        local f=running_env();local shutdown=f.host.workbench.shutdown
        f.host.workbench.shutdown=function()if throws then error('widget retained')end;return false,'widget retained'end
        assert(not f.control.runtime:stop('stop') and f.pc.Pawn==f.player and f.cancelled)
        assert(f.control.runtime.online_stop_pending)
        f.host.workbench.shutdown=shutdown;assert(f.control.runtime:stop('retry') and f.menu_cleanups==1)
    end
end)
check('logging failure does not interrupt cleanup or hide successful player restoration',function()
    local f=running_env();f.host.log=function()error('logger unavailable')end
    assert(f.control.runtime:stop('stop') and f.pc.Pawn==f.player and f.cancelled and f.menu_cleanups==1)
end)
check('native restore failure retains its receipt independently of successful resource cleanup',function()
    local f=running_env();local restore=f.bridge.restore
    f.bridge.restore=function()return false end
    assert(not f.control.runtime:stop('stop') and f.session.receipt and f.session.state=='FAULTED')
    assert(f.cancelled and f.menu_cleanups==1 and f.control.runtime.online_stop_pending)
    f.bridge.restore=restore;assert(f.control.runtime:stop('retry') and not f.session.receipt and f.pc.Pawn==f.player)
end)
check('completed shutdown cannot reactivate an owner with queued game-thread work',function()
    local f=running_env();assert(f.control.runtime:stop('stop'))
    local count=#f.mutations;f.peer.protocol.ready=true
    assert(not f.control:start() and not f.session:enter())
    f.queue[2]();f.frame();assert(not f.activation_calls and #f.mutations==count and not f.control.runtime.running)
end)
print('PASS '..checks..' online control groups; frozen native Lua with fake UObjects, no game/relay')
