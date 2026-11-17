local root=assert(arg[1]); package.path=root..'/tools/?.lua;'..package.path
local adapter=require('phantom_boss_adapter'); local protocol=require('phantom_boss_protocol')
local fence=require('phantom_boss_enemy_fence')
local checks=0
local function check(name,fn) fn();checks=checks+1;print('PASS '..name) end
local function actor(address,class,world)
    return {address=address,name='Actor_'..address,class=class or '/Boss/Ahua.Ahua_C',world=world or 'world_1',
        GetAddress=function(self)return self.address end}
end
local function env(role)
    local e={now=0, queue={}, snapshot={body=actor(1),world='world_1'}, enemies={}, addrs={}, revokes={},
        identify_count=0,snapshot_count=0,scheduled=nil,cancelled=false,linked=true,retired=0}
    local api={version='1.7.3',game={},coop={net={role=role=='host' and 'host' or 'client',enabled=true},handlers={}}}
    for _,key in ipairs({'enemyNumbers','announced','matchSticky','enemyNames','heldAlive','deadBodies','aside'}) do
        api.coop.net[key]={}
    end
    local cache={net=api.coop.net,names={},seen={},reach={list={},addrs={},at=1,near={}},
        round={queue={},at=1},handover={seen={},since={},retryAt={}}}
    api.coop.workbenchEnemyState=function()return cache end
    api.coop.sendEvent=function(kind,line)e.queue[#e.queue+1]={kind,line}end
    api.coop.linked=function()return e.linked end
    api.coop.isHost=function()return api.coop.net.role~='client'end
    api.coop.retireWorkbenchGhosts=function()
        e.retired=e.retired+1;if e.ghost_error then error('ghost retirement failed')end
    end
    api.game.listEnemies=function()return e.enemies,e.addrs end
    api.game.enemiesSoFar=api.game.listEnemies
    e.original_list=api.game.listEnemies
    local host={now=function()return e.now end,
        snapshot=function()e.snapshot_count=e.snapshot_count+1;return e.snapshot end,
        identify=function(a)e.identify_count=e.identify_count+1;return a end,
        log=function()end,on_revoke=function(why)e.revokes[#e.revokes+1]=why;return true end,
        schedule=function(ms,fn)assert(ms==100);e.scheduled=fn;return function()
            e.cancel_attempts=(e.cancel_attempts or 0)+1
            if e.cancel_error then error('observer cancellation failed')end;e.cancelled=true
        end end}
    local config={role=role,session='research_1',catalog_sha256=string.rep('a',64),exe_sha256=string.rep('b',64),
        runtime_acceptance_current=false,bosses={ahua={class_path='/Boss/Ahua.Ahua_C',actions={cut='/Ability/Cut.Cut_C'}},
        youlong={class_path='/Boss/YouLong.YouLong_C',actions={dodge='/Ability/Dodge.Dodge_C'}}}}
    e.api,e.host,e.config=api,host,config
    e.bridge=adapter.attach(api,config,host,protocol,fence)
    return e
end
local function pair(native)
    local h,g=env('host'),env('guest')
    g.snapshot.body.class='/Boss/YouLong.YouLong_C'
    if native then
        for _,e in ipairs({h,g}) do e.snapshot.body.class='/Player/Hun.Hun_C';e.snapshot.native_player=true end
    end
    local function step(now)
        h.now,g.now=now,now;h.scheduled();g.scheduled()
        while #h.queue>0 do local m=table.remove(h.queue,1);g.api.coop.handlers[m[1]](m[2],nil) end
        while #g.queue>0 do local m=table.remove(g.queue,1);h.api.coop.handlers[m[1]](m[2],nil) end
    end
    step(0);step(0.55);assert(h.bridge.protocol.ready and g.bridge.protocol.ready)
    return h,g,step
end
check('real coop handler/sendEvent extension and remote Boss identity',function()
    local h,g=pair();local path,why=h.bridge:remote_body_request()
    assert(path=='/Boss/YouLong.YouLong_C' and why:find('pending'))
    assert(not h.bridge:allow_legacy_ghost() and not g.bridge:allow_legacy_ghost())
end)
check('native-to-native legacy ghost requires mutual identity',function()
    local h,g=pair(true);assert(h.bridge:allow_legacy_ghost() and g.bridge:allow_legacy_ghost())
    h.linked=false;h.now=0.7;h.scheduled();assert(not h.bridge:allow_legacy_ghost())
end)
check('fresh and cached enemy arrays exclude identities without mutating upstream cache',function()
    local h=env('host');h.scheduled()
    h.enemies={h.snapshot.body,actor(2),actor(3)};h.addrs={1,2,3}
    for _,name in ipairs({'listEnemies','enemiesSoFar'}) do
        local actors,addresses=h.api.game[name](true)
        assert(#actors==2 and addresses[1]==2 and addresses[2]==3 and #h.enemies==3)
    end
    assert(h.identify_count==2)
end)
check('same address different name/class/world is not excluded',function()
    local h=env('host');h.scheduled()
    for _,field in ipairs({'name','class','world'}) do
        local reused=actor(1);reused[field]='different'
        h.enemies,h.addrs={reused},{1};assert(#h.api.game.listEnemies()==1)
    end
end)
check('owned targets, ghosts and retired local bodies remain excluded in same world',function()
    local h=env('host');h.scheduled()
    local target,ghost,old=actor(2),actor(3),h.snapshot.body
    h.bridge:register(target,'training_target');h.bridge:register(ghost,'remote_ghost')
    h.snapshot.body=actor(4);h.now=0.2;h.scheduled()
    h.enemies,h.addrs={old,target,ghost,h.snapshot.body,actor(5)},{1,2,3,4,5}
    local actors,addresses=h.api.game.listEnemies();assert(#actors==1 and addresses[1]==5)
end)
check('same Boss re-possession advances generation',function()
    local h,g,step=pair();local before=h.bridge.protocol.generation
    h.snapshot.body=actor(7);step(0.7)
    assert(h.bridge.protocol.generation>before and not g.bridge.protocol.ready)
end)
check('world switch retires old control before any new-World registration or handshake',function()
    local h,g,step=pair();h.bridge:register(actor(2),'training_target')
    local before=h.bridge.owned_count
    h.snapshot={world='world_2',body=actor(1,nil,'world_2')};step(0.7)
    assert(h.bridge.owned_count==before and h.bridge.owned[2]and h.retired>0)
    assert(h.bridge.world=='world_1'and h.bridge.world_transition.observed=='world_2')
    assert(not h.bridge.protocol.ready and not h.bridge.protocol.connected and not h.api.coop.net.enabled)
    assert(#h.revokes==1 and h.revokes[1]=='world changed'and not h.bridge:network_body())
end)
check('world crossing and oversized ownership cannot be registered',function()
    local h=env('host');h.scheduled()
    assert(not pcall(h.bridge.register,h.bridge,actor(2,nil,'other'),'training_target'))
    for i=2,32 do h.bridge:register(actor(i),'training_target') end
    assert(not pcall(h.bridge.register,h.bridge,actor(33),'training_target'))
end)
check('unknown local Pawn stays rejected on repeated polls',function()
    local h=env('host');h.snapshot.body.class='/Unreviewed/Other.Other_C'
    for i=0,5 do h.now=i*0.2;h.scheduled();assert(not h.bridge.protocol.connected) end
    assert(#h.revokes==1 and #h.queue==0)
end)
check('local split screen, PvP, party and role changes are rejected',function()
    for _,change in ipairs({{'party',4},{'pvp',true},{'role','local'},{'role','client'}}) do
        local h=env('host');h.api.coop.net[change[1]]=change[2];h.scheduled()
        assert(not h.bridge.protocol.connected and #h.queue==0)
    end
end)
check('foreign slot, disabled relay and disconnect packets are rejected',function()
    local h,g=pair();h.now=1.1;h.scheduled();local msg=h.queue[1]
    assert(not g.api.coop.handlers.BWB1(msg[2],3))
    g.api.coop.net.enabled=false;assert(not g.api.coop.handlers.BWB1(msg[2],nil))
    g.api.coop.net.enabled=true;g.linked=false;assert(not g.api.coop.handlers.BWB1(msg[2],nil))
end)
check('snapshot failure and expiry revoke once without polling searches each frame',function()
    local h=env('host');h.host.snapshot=function()error('expired')end;h.scheduled()
    for i=1,1000 do h.now=i/1000;h.scheduled() end
    assert(#h.revokes==1 and not h.bridge.protocol.connected)
end)
check('idle 10000 scheduler calls sample no more than 10 times per second',function()
    local h=env('host')
    for i=0,10000 do h.now=i/10000;h.scheduled() end
    assert(h.snapshot_count<=11 and h.identify_count==0 and #h.queue<=3)
end)
check('observer exceptions revoke prior handshake',function()
    local h,g,step=pair();h.bridge.register=function()error('broken identity')end
    h.snapshot.body=actor(8);step(0.7);assert(not h.bridge.protocol.ready)
end)
check('close restores own wrappers, removes handler and cancels callback',function()
    local h=env('host');h.scheduled();h.bridge:close();h.bridge:close()
    assert(h.cancelled and h.api.coop.handlers.BWB1==nil and h.api.game.listEnemies==h.original_list)
    assert(h.bridge.owned_count==0 and h.scheduled())
end)
check('close preserves another extension installed after ours',function()
    local h=env('host');local replacement=function()end
    h.api.coop.handlers.BWB1=replacement;h.api.game.listEnemies=replacement;h.bridge:close()
    assert(h.api.coop.handlers.BWB1==replacement and h.api.game.listEnemies==replacement)
end)
check('duplicate attachment rejected before overwriting owner',function()
    local h=env('host');local handler=h.api.coop.handlers.BWB1
    assert(not pcall(adapter.attach,h.api,h.config,h.host,protocol,fence));assert(h.api.coop.handlers.BWB1==handler)
end)
check('scheduler failure rolls back handler and both wrappers',function()
    local h=env('host');h.bridge:close();h.host.schedule=function()error('no timer')end
    assert(not pcall(adapter.attach,h.api,h.config,h.host,protocol,fence))
    assert(h.api.coop.handlers.BWB1==nil and h.api.game.listEnemies==h.original_list)
end)
check('intentional Boss selection invalidates the remote ghost without undoing local control',function()
    local h,g,step=pair();local before=h.retired
    h.snapshot.body=actor(9,'/Boss/YouLong.YouLong_C');step(0.7)
    assert(h.retired>before and #h.revokes==0 and #g.revokes==0)
    step(1.3);assert(h.bridge.protocol.ready and g.bridge.protocol.ready)
end)
check('loss of transport still revokes possession on both body choices',function()
    local h,g,step=pair();h.linked=false;h.now=0.8;h.scheduled()
    assert(#h.revokes==1 and h.revokes[1]=='transport disconnected')
end)
check('restore exception cannot strand handlers, wrappers or the observer during shutdown',function()
    local h=env('host');h.scheduled();h.host.on_revoke=function()error('restore failed')end
    assert(h.bridge:close()==false and h.bridge:close()==false)
    assert(h.bridge.restore_pending and not h.api.coop.net.enabled and h.cancelled)
    assert(h.api.coop.handlers.BWB1==nil and h.api.game.listEnemies==h.original_list)
end)
check('unacknowledged restore stays visibly pending and synchronization is disabled',function()
    local h,g=pair();h.host.on_revoke=function()return false end
    h.linked=false;h.now=0.8;h.scheduled()
    assert(h.bridge.restore_pending and not h.api.coop.net.enabled and not h.bridge.protocol.ready)
end)
check('ownership transition blocks legacy ghosts and forces an immediate new body snapshot',function()
    local h,g,step=pair(true);local boss=actor(77)
    h.bridge:register(boss,'local_body');local before=h.snapshot_count
    local token=h.bridge:begin_local_transition(h.bridge.owned[77])
    assert(not h.bridge:allow_legacy_ghost() and not h.bridge.protocol.ready)
    h.snapshot.body=boss;h.snapshot.native_player=false
    assert(h.bridge:finish_local_transition(token) and h.snapshot_count==before+1)
    assert(h.bridge.protocol.boss=='ahua' and not h.bridge.local_transition)
    assert(not pcall(h.bridge.finish_local_transition,h.bridge,token))
end)
check('unknown classes cannot begin possession and action whitelist is copied',function()
    local h=env('host');h.scheduled();local unknown=actor(8,'/Unreviewed/Boss.Boss_C')
    h.bridge:register(unknown,'local_body')
    assert(not pcall(h.bridge.begin_local_transition,h.bridge,h.bridge.owned[8]))
    h.config.bosses.ahua.actions.cut='/Injected/Attack.Attack_C'
    assert(h.bridge:resolve_local_action('/Boss/Ahua.Ahua_C','cut')=='/Ability/Cut.Cut_C')
end)
check('restoration callback cannot recursively poll a protocol clear in progress',function()
    local h,g=pair();local before=h.snapshot_count
    h.host.on_revoke=function()
        assert(h.bridge.revoking and h.bridge:refresh_local_body());return true
    end
    h.linked=false;h.now=0.8;h.scheduled()
    assert(h.snapshot_count==before+1 and not h.bridge.refresh_pending and not h.bridge.restore_pending)
    h.now=1;h.scheduled();assert(h.snapshot_count==before+1 and not h.bridge.protocol.connected)
end)
check('network state uses only the observed acknowledged body and blocks during transition',function()
    local h,g,step=pair();h.snapshot.body_actor=actor(1);step(0.7)
    local body,address=h.bridge:network_body();assert(body==h.snapshot.body_actor and address==1)
    h.snapshot.body_actor.name='reused';assert(h.bridge:network_body()==nil)
    h.snapshot.body_actor.name='Actor_1';local token=h.bridge:begin_local_transition(h.bridge.owned[1])
    assert(h.bridge:network_body()==nil);assert(h.bridge:finish_local_transition(token))
    assert(h.bridge:network_body()==nil);step(1.3);step(1.9);assert(h.bridge:network_body())
end)
check('failed observer and disconnect cannot reuse a previously cached network body',function()
    local h,g,step=pair();h.snapshot.body_actor=actor(1);step(0.7);assert(h.bridge:network_body())
    h.snapshot=nil;h.now=0.9;h.scheduled();assert(h.bridge:network_body()==nil)
    h,g,step=pair();h.snapshot.body_actor=actor(1);step(0.7);h.bridge:close()
    assert(h.bridge:network_body()==nil)
end)
check('combat bridge refuses inventory loot currency appearance rest and story packets',function()
    local e=env('host')
    for _,kind in ipairs({'BAG','I','O','OF','T','OC','KS','MF','C','LOOK','FX','HEAL','SIT','R','RH','unknown'})do
        assert(not e.bridge:allow_enemy_event(kind,'normal'))
    end
    for _,kind in ipairs({'BWB1','BWV1','Y','LOAD','BYE','N','NQ','D','K','GK','LR','RUN','A','HX'})do
        assert(e.bridge:allow_enemy_event(kind,'normal'))
    end
    e.bridge:close()
end)
check('one thousand clean Boss changes reclaim registrations without raising the live bound',function()
    local h=env('host');h.snapshot.body.class='/Player/Hun.Hun_C';h.snapshot.native_player=true;h.scheduled()
    for i=1,1000 do
        local body,ai=actor(2*i),actor(2*i+1,'/AI/Controller.Controller_C')
        h.bridge:register(body,'local_body');h.bridge:register(ai,'controller')
        assert(h.bridge.owned_count==3)
        assert(h.bridge:retire_owned(ai,'controller',function()return true end))
        assert(h.bridge:retire_owned(body,'local_body',function()return true end))
        assert(h.bridge.owned_count==1)
    end
    assert(h.bridge.owned[1]and h.snapshot_count==1)
end)
check('live unreadable or non-boolean retirement proof never frees a slot',function()
    local h=env('host');h.scheduled();local row=actor(2);h.bridge:register(row,'training_target')
    for _,probe in ipairs({function()return false end,function()return 1 end,function()error('unreadable')end})do
        assert(not pcall(h.bridge.retire_owned,h.bridge,row,'training_target',probe))
        assert(h.bridge.owned_count==2 and h.bridge.owned[2])
    end
end)
check('replaced identities and kinds cannot retire a live registration',function()
    local h=env('host');h.scheduled();local row=actor(2);h.bridge:register(row,'training_target')
    for _,key in ipairs({'name','class','world'})do
        local wrong=actor(2);wrong[key]='changed'
        assert(not pcall(h.bridge.retire_owned,h.bridge,wrong,'training_target',function()error('not reached')end))
    end
    assert(not pcall(h.bridge.retire_owned,h.bridge,row,'controller',function()error('not reached')end))
    assert(h.bridge.owned_count==2 and h.bridge.owned[2])
end)
check('pending ownership transitions cannot drop their Boss registration',function()
    local h=env('host');h.scheduled();local row=h.bridge.owned[1]
    local token=h.bridge:begin_local_transition(row)
    assert(not pcall(h.bridge.retire_owned,h.bridge,row,'local_body',function()error('not reached')end))
    assert(h.bridge.local_transition==token and h.bridge.owned[1]and h.bridge.owned_count==1)
end)
check('retired cached local body clears protocol readiness before it can be sent again',function()
    local h,g=pair();local row=h.snapshot.body;local generation=h.bridge.protocol.generation
    assert(h.bridge:retire_owned(row,'local_body',function()return true end))
    assert(not h.bridge.protocol.ready and h.bridge.protocol.generation>generation)
    assert(not h.bridge.local_body and not h.bridge.snapshot_current and h.bridge.owned_count==0)
    assert(h.bridge:network_body()==nil and not h.bridge.closed)
end)
check('retirement is idempotent after close and cannot underflow the registry',function()
    local h=env('host');h.scheduled();local row=h.snapshot.body;assert(h.bridge:close())
    for _=1,5 do assert(h.bridge:retire_owned(row,'local_body',function()return true end))end
    assert(h.bridge.owned_count==0 and next(h.bridge.owned)==nil)
end)
check('registry changes during native readback cannot drop a replacement',function()
    local h=env('host');h.scheduled();local row=actor(2);h.bridge:register(row,'training_target')
    local replacement=actor(2);replacement.name='replacement'
    assert(not pcall(h.bridge.retire_owned,h.bridge,row,'training_target',function()
        h.bridge:register(replacement,'training_target');return true
    end))
    assert(h.bridge.owned_count==2 and h.bridge.owned[2].name=='replacement')
end)
check('retired Actors keep old enemy aliases quarantined against late packets',function()
    local h=env('host');h.scheduled();local row=actor(2)
    local cache=h.api.coop.workbenchEnemyState();cache.names.owned_boss=row
    h.bridge:register(row,'local_body');assert(not h.bridge:allow_enemy_name('owned_boss'))
    assert(h.bridge:retire_owned(row,'local_body',function()return true end))
    assert(h.bridge.owned_count==1 and not h.bridge:allow_enemy_name('owned_boss'))
    assert(not h.bridge:allow_enemy_event('D','owned_boss')and h.bridge:allow_enemy_name('normal_enemy'))
end)
check('failed close retains ownership and retries local restoration instead of permanently returning failure',function()
    local h=env('host');h.scheduled();local clean=false
    h.host.on_revoke=function(why)h.revokes[#h.revokes+1]=why;return clean end
    assert(not h.bridge:close()and h.bridge.restore_pending and h.bridge.owned[1])
    assert(h.api.coop.handlers.BWB1==nil and h.api.game.listEnemies==h.original_list and h.cancelled)
    clean=true;assert(h.bridge:close()and not h.bridge.restore_pending and h.bridge.owned_count==0)
    assert(#h.revokes==2);assert(h.bridge:close()and #h.revokes==2)
end)
check('observer cancellation failure cannot strand wrappers and can retry without restoring twice',function()
    local h=env('host');h.scheduled();h.cancel_error=true
    local ok,clean=pcall(h.bridge.close,h.bridge);assert(ok and not clean and h.bridge.restore_pending)
    assert(h.api.coop.handlers.BWB1==nil and h.api.game.listEnemies==h.original_list and #h.revokes==1)
    local snapshots=h.snapshot_count;assert(h.scheduled()and h.snapshot_count==snapshots)
    h.cancel_error=false;assert(h.bridge:close()and h.cancel_attempts==2 and #h.revokes==1)
    assert(h.bridge:close()and h.cancel_attempts==2 and h.bridge.owned_count==0)
end)
check('ghost retirement exceptions cannot skip local recovery or erase its retry responsibility',function()
    local h=env('host');h.scheduled();h.ghost_error=true
    local ok,clean=pcall(h.bridge.close,h.bridge);assert(ok and not clean and #h.revokes==1)
    assert(h.bridge.closed and h.bridge.restore_pending and h.bridge.owned[1]and h.cancelled)
    assert(h.api.coop.handlers.BWB1==nil and not h.api.coop.net.enabled)
    h.ghost_error=false;assert(h.bridge:close()and #h.revokes==1 and h.bridge.owned_count==0)
end)
check('disconnect with a broken legacy ghost still revokes local control once without polling retries',function()
    local h,g=pair();h.ghost_error=true;h.linked=false;h.now=.8
    assert(pcall(h.scheduled)and #h.revokes==1 and not h.api.coop.net.enabled and not h.bridge.protocol.ready)
    local retired=h.retired
    for i=1,10 do h.now=.8+i*.2;assert(pcall(h.scheduled))end
    assert(#h.revokes==1 and h.retired==retired and h.bridge.restore_pending)
    h.ghost_error=false;assert(h.bridge:close())
end)
check('recovery retries preserve replacement handlers and enemy-list extensions',function()
    local h=env('host');h.scheduled();h.host.on_revoke=function()return false end
    assert(not h.bridge:close());local replacement=function()end
    h.api.coop.handlers.BWB1=replacement;h.api.game.listEnemies=replacement;h.api.game.enemiesSoFar=replacement
    h.host.on_revoke=function()return true end;assert(h.bridge:close())
    assert(h.api.coop.handlers.BWB1==replacement and h.api.game.listEnemies==replacement
        and h.api.game.enemiesSoFar==replacement)
end)
check('combined close failures remain pending until each independent owner acknowledges cleanup',function()
    local h=env('host');h.scheduled();local restored=false
    h.host.on_revoke=function(why)h.revokes[#h.revokes+1]=why;return restored end
    h.ghost_error=true;h.cancel_error=true
    assert(not h.bridge:close()and h.bridge.owned[1]and #h.revokes==1)
    restored=true;assert(not h.bridge:close()and h.bridge.owned[1]and #h.revokes==2)
    h.ghost_error=false;assert(not h.bridge:close()and h.bridge.owned[1]and #h.revokes==2)
    h.cancel_error=false;assert(h.bridge:close()and not h.bridge.restore_pending and #h.revokes==2)
    assert(h.bridge.owned_count==0 and h.bridge.local_body==nil and h.bridge.body_actor==nil)
end)
check('initial gameplay World does not revoke an assembly or stop its normal handshake',function()
    local h,g=pair();assert(not h.bridge.world_transition and #h.revokes==0 and h.bridge.protocol.ready)
    assert(not g.bridge.world_transition and #g.revokes==0 and g.bridge.protocol.ready)
end)
check('World recovery observes the old registrations and never adopts a replacement player',function()
    local h=env('host');h.scheduled();local old=h.bridge.owned[1]
    h.host.on_revoke=function(why)
        assert(why=='world changed'and h.bridge.owned[1]==old and h.bridge.world=='world_1')
        assert(h.bridge.world_transition.previous=='world_1'and h.bridge.world_transition.observed=='world_2')
        h.revokes[#h.revokes+1]=why;return false
    end
    h.snapshot={world='world_2',body=actor(7,nil,'world_2')};h.now=.2;h.scheduled()
    assert(h.bridge.restore_pending and h.bridge.owned[1]==old and not h.bridge.owned[7]and #h.revokes==1)
end)
check('retired World polling does not repeat recovery searches or advance generations',function()
    local h,g=pair();h.snapshot={world='world_2',body=actor(7,nil,'world_2')};h.now=.8;h.scheduled()
    local snapshots,generation,retired=h.snapshot_count,h.bridge.protocol.generation,h.retired
    for i=1,1000 do h.now=.8+i*.1;h.scheduled()end
    assert(h.snapshot_count==snapshots and h.bridge.protocol.generation==generation and h.retired==retired)
    assert(#h.revokes==1 and not h.bridge.protocol.ready)
end)
check('World retirement blocks late packets even if a caller tries to re-enable the old relay',function()
    local h,g=pair();g.now=1.1;g.scheduled();local late=assert(g.queue[1])
    h.snapshot={world='world_2',body=actor(7,nil,'world_2')};h.now=1.2;h.scheduled()
    h.api.coop.net.enabled=true;h.linked=true
    assert(not h.api.coop.handlers.BWB1(late[2],nil)and not h.bridge.protocol.ready)
    assert(not h.bridge:network_body()and not h.bridge:allow_legacy_ghost())
    assert(not h.bridge:allow_enemy_event('D','normal_enemy'))
    assert(not pcall(h.bridge.begin_local_transition,h.bridge,h.bridge.owned[1]))
end)
check('explicit close can retry failed World recovery without resetting the old identity early',function()
    local h=env('host');h.scheduled();local old=h.bridge.owned[1];local clean=false
    h.host.on_revoke=function(why)h.revokes[#h.revokes+1]=why;return clean end
    h.snapshot={world='world_2',body=actor(7,nil,'world_2')};h.now=.2;h.scheduled()
    assert(h.bridge.restore_pending and h.bridge.owned[1]==old)
    assert(not h.bridge:close()and h.bridge.owned[1]==old)
    clean=true;assert(h.bridge:close()and h.bridge.owned_count==0 and not h.bridge.restore_pending)
end)
check('disconnect retirement stops repeated snapshots and cannot be revived by relay flags',function()
    local h,g,step=pair();h.snapshot.body_actor=h.snapshot.body
    h.linked=false;step(.8);assert(h.bridge.revoked_reason and #h.revokes==1)
    local snapshots,generation=h.snapshot_count,h.bridge.protocol.generation
    h.linked=true;h.api.coop.net.enabled=true
    for i=1,20 do step(.8+i*.05)end
    assert(h.snapshot_count==snapshots and h.bridge.protocol.generation==generation and not h.bridge.protocol.ready)
    assert(h.bridge.revoked_reason and not h.bridge:network_body()and not h.bridge:allow_legacy_ghost())
    assert(not h.bridge:refresh_local_body()and h.snapshot_count==snapshots)
end)
check('late control and enemy messages cannot pass a retired activation',function()
    local h,g=pair();g.now=1.1;g.scheduled();local late=assert(g.queue[1])
    h.linked=false;h.now=1.2;h.scheduled();h.linked=true;h.api.coop.net.enabled=true
    assert(not h.api.coop.handlers.BWB1(late[2],nil))
    for _,kind in ipairs({'BWB1','BWV1','Y','N','D','K','A'})do
        assert(not h.bridge:allow_enemy_event(kind,'normal_enemy'))
    end
    assert(not h.bridge:allow_enemy_name('normal_enemy')and not h.bridge:allow_enemy_actor(actor(99)))
    assert(not h.bridge:allow_enemy_actor(nil))
end)
check('a rejected initial body cannot later establish gameplay under the same activation',function()
    local h=env('host');h.snapshot=nil;assert(h.scheduled())
    local snapshots=h.snapshot_count
    h.snapshot={world='world_1',body=actor(7),native_player=false};h.api.coop.net.enabled=true
    h.now=1;assert(h.scheduled()and h.snapshot_count==snapshots and not h.bridge.world)
    assert(not h.bridge:refresh_local_body()and not h.bridge.owned[7])
end)
check('retired ownership rejects new registration and transitions but keeps native cleanup available',function()
    local h,g=pair();local row=h.bridge.owned[1]
    h.linked=false;h.now=.8;assert(h.scheduled())
    local generation=h.bridge.protocol.generation
    assert(not pcall(h.bridge.register,h.bridge,actor(99),'training_target'))
    assert(not pcall(h.bridge.begin_local_transition,h.bridge,row))
    assert(h.bridge:retire_owned(row,'local_body',function()return true end))
    assert(h.bridge.owned_count==0 and h.bridge.protocol.generation==generation and h.bridge:close())
end)
check('failed disconnect recovery remains explicitly retryable without repeating observer work',function()
    local h,g=pair();local clean=false
    h.host.on_revoke=function(why)h.revokes[#h.revokes+1]=why;return clean end
    h.linked=false;h.now=.8;assert(h.scheduled()and h.bridge.restore_pending)
    local snapshots,retired=h.snapshot_count,h.retired
    for i=1,1000 do h.now=.8+i*.1;assert(h.scheduled())end
    assert(h.snapshot_count==snapshots and h.retired==retired and #h.revokes==1 and h.bridge.owned[1])
    clean=true;assert(h.bridge:close()and not h.bridge.restore_pending and #h.revokes==2)
end)
print('PASS '..checks..' adapter groups; mocked upstream API, no native/game execution')
