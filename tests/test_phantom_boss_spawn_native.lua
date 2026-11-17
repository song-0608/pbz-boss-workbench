-- Concrete spawn/readiness/disposal bindings with fake Unreal objects. Private
-- ue_calls is the real pinned module; no game, save, policy or relay is touched.
local root,candidate=assert(arg[1]),assert(arg[2])
local directory=candidate..'/PBZCoop/Scripts/'
local deps=dofile(directory..'bwb_local_dependencies.lua')(directory)
local Native=dofile(directory..'bwb_spawn_native.lua')
local Adapter=dofile(directory..'bwb_adapter.lua')
local Protocol=dofile(directory..'bwb_protocol.lua')
local EnemyFence=dofile(directory..'bwb_enemy_fence.lua')
local checks=0
local function check(name,fn)fn();checks=checks+1;print('PASS '..name)end
local function fixture(real_adapter)
    local f={registry={},events={},clock=0,remembered={},registered={},retired={},grants=1,protected=false}
    local next_address=10
    local function obj(name,class)
        next_address=next_address+1
        local o={alive=true,name=name,class=class or '/Fixture.Object',address=next_address}
        function o:IsValid()return self.alive end
        function o:GetAddress()return self.address end
        function o:GetFullName()return 'Object '..self.name end
        function o:GetClass()return {IsValid=function()return true end,GetFullName=function()return 'Class '..self.class end}end
        function o:GetWorld()return f.world end
        function o:K2_DestroyActor()
            f.events[#f.events+1]='destroy:'..self.name
            self.destroy_attempts=(self.destroy_attempts or 0)+1
            if self.destroy_error then error('native Actor destruction failed')end
            if self.refuse_destroy then return false end
            self.alive=false
            if self.Controller then self.Controller.Pawn=nil end
            if self.Pawn then self.Pawn.Controller=nil end
        end
        f.registry[name]=o;return o
    end
    f.object=obj
    f.world=obj('/Fixture/W.W','/Script/Engine.World')
    f.pc=obj('/Fixture/W.W:PersistentLevel.PC');f.player=obj('/Fixture/W.W:PersistentLevel.Player','/Player/Hun.Hun_C')
    function f.pc:K2_GetPawn()return self.Pawn end
    f.pc.Pawn=f.player;f.player.Controller=f.pc
    function f.player:GetController()return self.Controller end
    function f.player:K2_GetActorLocation()return {X=0,Y=0,Z=100}end
    function f.player:GetActorForwardVector()return {X=1,Y=0,Z=0}end
    f.player.CapsuleComponent={CapsuleHalfHeight=100}
    local actor_config=obj('/Boss/Config.Config')
    function actor_config:GetCharacterName()return {ToString=function()return 'Boss' end}end
    f.class=obj('/Boss/A.A_C')
    function f.class:GetCDO()return {['Actor Config']=actor_config,CapsuleComponent={CapsuleHalfHeight=110,CapsuleRadius=80}}end
    f.ai_class=obj('/AI/AI.AI_C')
    f.profile={id='boss',exe_sha256=string.rep('a',64),identity_verified=true,class_path='/Boss/A.A_C',
        config_path='/Boss/Config.Config',display_name='Boss',camera={},input={},skills={cut={class_path='/Skill/Cut.Cut_C'}}}
    f.config={expected_exe_sha256=f.profile.exe_sha256,skills={slot1={id='cut',verified=true}},controls={enter='F6',exit='F10'}}
    local mods={ue_calls=deps.require('ue_calls')}
    mods.object_lifecycle={new=function()return {usable=function(_,o)return o and o:IsValid() or false end}end}
    mods.boss_catalog={profile=function(id)assert(id=='boss');return f.profile end,configure=function()return f.config end}
    mods.player_protection={new=function()
        return {capture=function()return {}end,apply=function()f.protected=true end,verify=function()return f.protected end,
            restore=function(_,t)f.protected=false;t.restored=true;return true end}
    end}
    mods.owned_initialization={new=function()
        return {hold=function(_,body,player)assert(body==f.body and player==f.player);f.held=true end,
            verify=function()return f.held end,release=function()f.held=false end}
    end}
    mods.ue_combat={new=function()return {}end}
    mods.ue_host={new=function(bridge,input)
        assert(input and bridge.player_controller);f.recovery_pc=bridge.player_controller;return {menu_only=true}
    end}
    mods.ue_camera={new=function()return {spawn_camera=function(pc,anchor)
        assert(pc==f.pc and anchor==f.player);f.menu_spawned=true;return f.object('/Fixture/Menu')
    end,destroy_camera=function()return true end}end}
    mods.ue_input_barrier={new=function()return {}end}
    mods.input_barrier={new=function()return {}end}
    mods.workbench_input=deps.require('workbench_input')
    mods.ue_arena_layout={new=function()return function()end end}
    mods.arena_layout={choose=function()return {boss={X=450,Y=0,Z=112},heading=0}end}
    local g={LoadAsset=function(path)
        if path==f.profile.class_path then return f.class end
        assert(path=='/PBZCombatAsset/Prototypes/AI/BP_PBZAIController.BP_PBZAIController_C');return f.ai_class
    end,StaticFindObject=function(path)return f.registry[path]end,
        LoopInGameThreadWithDelay=function(ms,fn)assert(ms==250);f.timer=fn;return 77 end,
        CancelDelayedAction=function(handle)
            assert(handle==77);f.cancelled=(f.cancelled or 0)+1
            if f.cancel_failure then error('native cancellation failed')end
        end}
    local maths=obj('/Script/Engine.Default__KismetMathLibrary')
    function maths:MakeTransform(location,rotation,scale)return {location=location,rotation=rotation,scale=scale}end
    local statics=obj('/Script/Engine.Default__GameplayStatics')
    function statics:BeginDeferredActorSpawnFromClass(pc,class,transform,collision,owner,scale)
        assert(pc==f.pc and class==f.class and collision==3 and owner==nil and scale==0)
        assert(f.protected and transform.location.X==450)
        if f.reject_spawn then return nil end
        f.body=obj('/Fixture/W.W:PersistentLevel.Boss','/Boss/A.A_C')
        function f.body:GetController()return self.Controller end
        function f.body:HasAuthority()return f.authority~=false end
        function f.body:SpawnDefaultController()
            f.events[#f.events+1]='spawn_ai'
            f.ai=obj('/Fixture/W.W:PersistentLevel.AI');self.Controller=f.ai;f.ai.Pawn=self
            function f.ai:K2_GetPawn()return self.Pawn end
            f.ai.BrainComponent={running=true,tick=true,IsValid=function()return true end,
                StopLogic=function(self)self.running=false end,IsRunning=function(self)return self.running end,
                SetComponentTickEnabled=function(self,on)self.tick=on end,IsComponentTickEnabled=function(self)return self.tick end}
            f.ai.SGameAIComponent={bInitialized=true,bAIStarted=true,IsValid=function()return true end,
                StopAI=function(self)self.bAIStarted=false end}
            function f.ai:SetActorTickEnabled(on)self.tick=on end
            function f.ai:IsActorTickEnabled()return self.tick end
            f.ai.tick=true
        end
        local ability=obj('/Skill/Cut.Default__Cut','/Skill/Cut.Cut_C')
        f.spec={Ability=ability,ActiveCount=0}
        local asc=obj('/Fixture/W.W:PersistentLevel.Boss.ASC')
        asc.ActivatableAbilities={Items=setmetatable({GetArrayNum=function()return f.grants end},
            {__index=function(_,i)assert(i>=1 and i<=f.grants);return f.spec end})}
        f.body.AbilitySystemComponent=asc
        f.events[#f.events+1]='deferred';return f.body
    end
    function statics:FinishSpawningActor(body,transform,scale)
        assert(body==f.body and body.AIControllerClass==f.ai_class and scale==0)
        assert((f.peer.owned or f.registered)[body.address] and #f.remembered==1,
            'must register deferred body before Finish')
        f.events[#f.events+1]='finish'
        if f.auto_ai then body:SpawnDefaultController()end
        if f.fail_finish then error('partial native Finish failure')end
        return body
    end
    local scope={attest=function(_,restore)assert(restore or not f.revoked);return {exe_sha256=f.profile.exe_sha256}end}
    local peer={world='W',is_boss_class=function(_,path)return path=='/Boss/A.A_C'end,
        resolve_local_action=function(_,path,id)assert(path=='/Boss/A.A_C' and id=='cut');return '/Skill/Cut.Cut_C'end,
        register=function(_,row,kind)
            assert(not f.registration_refused,'registration rejected')
            f.registered[row.address]={row=row,kind=kind};f.events[#f.events+1]='register:'..kind
        end,
        retire_owned=function(_,row,kind,probe)
            assert(probe()==true and not f.retirement_refused and f.retirement_refused_address~=row.address,
                'native retirement not acknowledged')
            local old=f.registered[row.address]
            if old then
                assert(old.kind==kind and old.row.name==row.name and old.row.class==row.class and old.row.world==row.world)
                f.registered[row.address]=nil;f.retired[row.address]=old
            end
            return true
        end}
    local observer={now=function()return f.clock end,log=function()end,
        identify=function(o,world)
            assert(o and o:IsValid() and (world==nil or world=='W') and o:GetWorld()==f.world)
            return {address=o:GetAddress(),name=o:GetFullName(),class=o:GetClass():GetFullName():match('^[^ ]+ (.+)$'),world='W'}
        end,snapshot=function()return {world=f.snapshot_world or 'W',native_player=f.native_player~=false,
            remote_control=f.remote_control}end}
    local bindings={combat={binding_verified=true,friendly=0,hostile=2,ai_focus_bridge=true}}
    for _,key in ipairs({'camera','remote','barrier','protection','arena','visibility'})do bindings[key]={binding_verified=true}end
    f.api={getPlayer1=function()return f.pc,f.player end}
    if real_adapter then
        local net={role='host',enabled=true}
        for _,key in ipairs({'enemyNumbers','announced','matchSticky','enemyNames','heldAlive','deadBodies','aside'})do
            net[key]={}
        end
        local cache={net=net,names={},seen={},reach={list={},addrs={},at=1,near={}},
            round={queue={},at=1},handover={seen={},since={},retryAt={}}}
        f.api.version='1.7.3'
        f.api.game={listEnemies=function()return {},{}end,enemiesSoFar=function()return {},{}end}
        f.api.coop={net=net,handlers={},workbenchEnemyState=function()return cache end,
            sendEvent=function()end,linked=function()return f.linked~=false end,isHost=function()return true end,
            retireWorkbenchGhosts=function()end}
        local host={now=observer.now,identify=observer.identify,log=observer.log,
            snapshot=function()
                local snapshot=observer.snapshot();snapshot.body=observer.identify(f.player,snapshot.world)
                return snapshot
            end,
            schedule=function(ms,fn)assert(ms==100);f.peer_timer=fn;return function()end end,
            on_revoke=function(why)
                f.revoked=true;f.revoke_while_open=not f.peer.closed
                if f.on_revoke then return f.on_revoke(why)end
                return true
            end}
        peer=Adapter.attach(f.api,{role='host',session='spawn_cleanup',
            catalog_sha256=string.rep('b',64),exe_sha256=f.profile.exe_sha256,
            runtime_acceptance_current=false,bosses={boss={class_path=f.profile.class_path,
                actions={cut=f.profile.skills.cut.class_path}}}},host,Protocol,EnemyFence)
        f.peer_timer();assert(peer.world=='W'and not peer.revoked_reason)
        local partner=Protocol.new{role='guest',session='spawn_cleanup',catalog=string.rep('b',64),
            build=f.profile.exe_sha256,bosses={boss={class_path=f.profile.class_path,
                actions={cut=f.profile.skills.cut.class_path}}},
            send=function(kind,line)assert(f.api.coop.handlers[kind](line,nil))end}
        partner:set_link(true,0);partner:tick(0)
        assert(peer.protocol.remote,'disconnect cleanup requires an observed partner identity')
    end
    f.scope,f.peer,f.bindings,f.g,f.dependencies=scope,peer,bindings,g,{require=function(name)return assert(mods[name],name)end}
    f.native=Native.new(f.api,scope,peer,observer,f.dependencies,{},bindings,g)
    function f:remember(record)self.remembered[#self.remembered+1]=record end
    function f:start()
        self.context=self.native.prepare('boss');self.native.protect(self.context)
        self.record=self.native.spawn(self.context,function(record)self:remember(record)end)
        return self.body,self.context
    end
    function f:partial()
        self.auto_ai=true;self.fail_finish=true
        self.context=self.native.prepare('boss');self.native.protect(self.context)
        assert(not pcall(self.native.spawn,self.context,function(record)self:remember(record)end))
        assert(#self.remembered==1 and self.ai);self.record=self.remembered[1]
        return self.record,self.context
    end
    return f
end
check('concrete deferred spawn registers ownership before construction and isolates initialization',function()
    local f=fixture();local body,c=f:start()
    assert(body==f.body and c.body_reference.name==body:GetFullName() and f.held)
    assert(table.concat(f.events,',')=='deferred,register:local_body,finish')
    assert(f.profile.instance_name==nil,'catalog profile must remain immutable')
end)
check('collision rejection never creates or registers an Actor',function()
    local f=fixture();f.reject_spawn=true;local c=f.native.prepare('boss');f.native.protect(c)
    assert(not pcall(f.native.spawn,c,function(r)f:remember(r)end) and #f.remembered==0)
    assert(f.native.restore_player(c) and not f.protected)
end)
check('readiness requests a missing default AI only at the bounded cadence',function()
    local f=fixture();local body,c=f:start()
    assert(f.native.readiness(body,c,1)==nil and not f.ai)
    assert(f.native.readiness(body,c,4)==nil and f.ai)
    f.native.register_controller(body,c,function(r)f:remember(r)end)
    assert(#f.remembered==2 and f.registered[f.ai.address].kind=='controller')
    assert(f.native.readiness(body,c,5) and f.native.readiness(body,c,6))
end)
check('uninitialized AI, no authority and duplicate granted actions never become ready',function()
    local f=fixture();local body,c=f:start();body:SpawnDefaultController()
    f.authority=false;assert(f.native.readiness(body,c,1)==nil);f.authority=true
    f.ai.SGameAIComponent.bInitialized=false;assert(f.native.readiness(body,c,1)==nil)
    f.ai.SGameAIComponent.bInitialized=true;f.grants=2;assert(f.native.readiness(body,c,1)==nil)
    f.grants=513;assert(not pcall(f.native.readiness,body,c,1))
end)
check('AI replacement or reciprocal ownership mismatch is rejected before registration',function()
    local f=fixture();local body,c=f:start();body:SpawnDefaultController()
    f.native.register_controller(body,c,function(r)f:remember(r)end)
    body:SpawnDefaultController();assert(not pcall(f.native.register_controller,body,c,function()error('unreachable')end))
    f=fixture();body,c=f:start();body:SpawnDefaultController();f.ai.Pawn=f.player
    assert(not pcall(f.native.register_controller,body,c,function()error('unreachable')end))
end)
check('AI suspension reads back the stopped Brain and both tick switches',function()
    local f=fixture();local body,c=f:start();body:SpawnDefaultController()
    f.native.register_controller(body,c,function(r)f:remember(r)end);f.native.suspend(body,c)
    assert(not f.ai.BrainComponent.running and not f.ai.BrainComponent.tick and not f.ai.tick and not f.ai.SGameAIComponent.bAIStarted)
    f.native.release_initialization(c);f.native.restore_player(c);assert(not f.held and not f.protected)
end)
check('partial Finish failure recovers an auto-created AI before any readiness poll',function()
    local f=fixture();f.auto_ai=true;f.fail_finish=true
    local c=f.native.prepare('boss');f.native.protect(c)
    assert(not pcall(f.native.spawn,c,function(r)f:remember(r)end) and #f.remembered==1 and f.ai)
    assert(f.native.destroy(f.remembered[1],c) and not f.ai.alive and not f.body.alive)
    assert(not f.registered[f.ai.address]and f.retired[f.ai.address].kind=='controller')
end)
check('partial cleanup retries the remembered AI after its body has already gone',function()
    for _,failure in ipairs({'refuse_destroy','destroy_error'})do
        local f=fixture();local record,c=f:partial();f.ai[failure]=true
        assert(not pcall(f.native.destroy,record,c)and not f.body.alive and f.ai.alive)
        assert(record.leftover and record.leftover.address==f.ai.address,'AI recovery reference was lost')
        f.ai[failure]=false
        assert(f.native.destroy(record,c)and not f.ai.alive and not record.leftover)
        assert(f.body.destroy_attempts==1 and f.ai.destroy_attempts==2 and next(f.registered)==nil)
    end
end)
check('AI retirement retry does not repeat acknowledged native destruction',function()
    local f=fixture();local record,c=f:partial();f.retirement_refused_address=f.ai.address
    assert(not pcall(f.native.destroy,record,c)and not f.body.alive and not f.ai.alive)
    assert(record.leftover and f.registered[f.ai.address])
    f.retirement_refused_address=nil
    assert(f.native.destroy(record,c)and not record.leftover and next(f.registered)==nil)
    assert(f.body.destroy_attempts==1 and f.ai.destroy_attempts==1)
end)
check('body destruction failure retains the discovered AI for later cleanup',function()
    local f=fixture();local record,c=f:partial();f.body.refuse_destroy=true
    assert(not pcall(f.native.destroy,record,c)and f.body.alive and f.ai.alive)
    assert(record.leftover and record.leftover.address==f.ai.address and not f.ai.destroy_attempts)
    f.body.refuse_destroy=false
    assert(f.native.destroy(record,c)and not f.body.alive and not f.ai.alive and not record.leftover)
end)
check('body registry retirement failure cannot lose a partially initialized AI',function()
    local f=fixture();local record,c=f:partial();f.retirement_refused_address=f.body.address
    assert(not pcall(f.native.destroy,record,c)and not f.body.alive and f.ai.alive)
    assert(record.leftover and not f.ai.destroy_attempts)
    f.retirement_refused_address=nil
    assert(f.native.destroy(record,c)and not f.ai.alive and next(f.registered)==nil)
    assert(f.body.destroy_attempts==1)
end)
check('remembered AI acquiring another Pawn is refused without dropping its recovery reference',function()
    local f=fixture();local record,c=f:partial();f.ai.refuse_destroy=true
    assert(not pcall(f.native.destroy,record,c)and not f.body.alive)
    f.ai.refuse_destroy=false;f.ai.Pawn=f.player
    assert(not pcall(f.native.destroy,record,c)and f.ai.alive and f.player.alive)
    assert(record.leftover and f.ai.destroy_attempts==1)
    f.ai.Pawn=nil;assert(f.native.destroy(record,c)and not f.ai.alive and not record.leftover)
end)
check('same-name AI address reuse is refused during a delayed cleanup retry',function()
    local f=fixture();local record,c=f:partial();f.ai.refuse_destroy=true
    assert(not pcall(f.native.destroy,record,c))
    local original=f.ai;local replacement=f.object(original.name,original.class)
    assert(not pcall(f.native.destroy,record,c)and replacement.alive and not replacement.destroy_attempts)
    assert(record.leftover.address==original.address and original.alive)
    f.registry[original.name]=original;original.refuse_destroy=false
    assert(f.native.destroy(record,c)and not original.alive and replacement.alive)
end)
check('failed AI registration retains exact ownership before either Actor is destroyed',function()
    local f=fixture();local record,c=f:partial();f.registration_refused=true
    assert(not pcall(f.native.destroy,record,c)and f.body.alive and f.ai.alive)
    assert(record.leftover and record.leftover.address==f.ai.address)
    f.registration_refused=false;assert(f.native.destroy(record,c)and next(f.registered)==nil)
end)
check('a replaced controller cannot overwrite the AI retained by a failed body cleanup',function()
    local f=fixture();local record,c=f:partial();f.body.refuse_destroy=true
    assert(not pcall(f.native.destroy,record,c))
    local original=f.ai;f.body:SpawnDefaultController();local replacement=f.ai
    assert(not pcall(f.native.destroy,record,c)and f.body.destroy_attempts==1)
    assert(record.leftover.address==original.address and original.alive and replacement.alive)
    f.registry[original.name]=original;f.body.Controller=original;f.body.refuse_destroy=false
    assert(f.native.destroy(record,c)and not original.alive and replacement.alive)
end)
check('real retired adapter permits partial AI disposal before close without a new registration',function()
    local f=fixture(true);local record,c=f:partial()
    assert(not f.peer.owned[f.ai.address])
    f.on_revoke=function()
        assert(f.peer.revoked_reason)
        return f.native.destroy(record,c)
    end
    f.clock=0.2;f.linked=false;f.peer_timer()
    assert(f.revoke_while_open and not f.peer.control_restore_pending and not f.peer.closed)
    assert(not f.body.alive and not f.ai.alive and not record.leftover)
    assert(f.peer.owned_count==1 and f.peer.owned[f.player.address])
    assert(not pcall(f.peer.register,f.peer,{address=999,name='Actor_999',class='/AI/AI.AI_C',world='W'},'controller'))
    assert(f.peer:close()and f.player.alive and f.pc.alive)
end)
check('real retired adapter preserves failed AI disposal until an explicit close retries it',function()
    local f=fixture(true);local record,c=f:partial();f.ai.refuse_destroy=true
    f.on_revoke=function()return f.native.destroy(record,c)end
    f.clock=0.2;f.linked=false;f.peer_timer()
    assert(f.peer.control_restore_pending and not f.peer.closed and not f.body.alive and f.ai.alive)
    assert(record.leftover and not f.peer.owned[f.ai.address])
    assert(not f.peer:close()and f.peer.control_restore_pending and record.leftover)
    f.ai.refuse_destroy=false
    assert(f.peer:close()and not f.ai.alive and not record.leftover and f.peer.owned_count==0)
    assert(f.body.destroy_attempts==1 and f.ai.destroy_attempts==3 and f.player.alive and f.pc.alive)
end)
check('cleanup after lease revocation only destroys exact owned identities',function()
    local f=fixture();local body,c=f:start();body:SpawnDefaultController()
    f.native.register_controller(body,c,function(r)f:remember(r)end);f.revoked=true
    assert(not pcall(f.native.resolve,f.record,c))
    assert(f.native.destroy(f.remembered[2],c));assert(f.native.destroy(f.record,c));assert(f.native.restore_player(c))
    assert(f.player.alive and f.pc.alive and not f.body.alive and not f.ai.alive and not f.protected)
end)
check('same-name address reuse and a controller acquired by another Pawn refuse deletion',function()
    local f=fixture();local body,c=f:start();local name=body.name
    local replacement=f.object(name,'/Boss/A.A_C')
    assert(not pcall(f.native.destroy,f.record,c) and replacement.alive)
    f=fixture();body,c=f:start();body:SpawnDefaultController()
    f.native.register_controller(body,c,function(r)f:remember(r)end);f.ai.Pawn=f.player
    assert(not pcall(f.native.destroy,f.remembered[2],c) and f.ai.alive and f.player.alive)
end)
check('actor-config mismatch and missing native declaration refuse before protection',function()
    local f=fixture();f.profile.config_path='/Other/Config.Config'
    assert(not pcall(f.native.prepare,'boss') and not f.protected and #f.events==0)
    f=fixture();f.bindings.combat.ai_focus_bridge=false
    assert(not pcall(Native.new,f.api,f.scope,f.peer,{},f.dependencies,{},f.bindings,f.g))
end)
check('cancelled native scheduler ignores stale callbacks and cancels exactly once',function()
    local f=fixture();local calls=0
    local cancel=f.native.schedule(250,function()calls=calls+1 end)
    f.timer();cancel();cancel();f.timer();assert(calls==1 and f.cancelled==1)
end)
check('recovery host resolves the original player without loading or spawning another Boss',function()
    local f=fixture();local host,layer,pc,guard=f.native.recovery_menu('boss')
    assert(host.menu_only and pc==f.pc and guard()and f.recovery_pc()==pc)
    assert(not f.protected and not f.body and not f.menu_spawned and #f.events==0 and not layer.ticket)
end)
check('recovery menu refuses a controlled Boss or a changed World before input attachment',function()
    for _,field in ipairs({'native_player','remote_control','snapshot_world'})do
        local f=fixture()
        if field=='native_player'then f[field]=false elseif field=='remote_control'then f[field]=true else f[field]='other'end
        assert(not pcall(f.native.recovery_menu,'boss')and not f.menu_spawned and not f.body)
    end
end)
check('recovery guard rejects a new Pawn and cannot follow a reused controller',function()
    local f=fixture();local _,_,_,guard=f.native.recovery_menu('boss')
    f.pc.Pawn=f.object('/Fixture/Replacement');assert(not pcall(guard))
    f=fixture();local _,_,_,guard=f.native.recovery_menu('boss')
    f.object(f.pc.name);assert(not pcall(guard))
end)
check('recovery guard rejects expiry without protecting or spawning the native player',function()
    local f=fixture();local _,_,_,guard=f.native.recovery_menu('boss');f.revoked=true
    assert(not pcall(guard)and not f.protected and not f.menu_spawned and not f.body)
end)
check('confirmed Boss and AI destruction releases only their owned registrations',function()
    local f=fixture();local body,c=f:start();body:SpawnDefaultController()
    f.native.register_controller(body,c,function(r)f:remember(r)end)
    for i=#f.remembered,1,-1 do assert(f.native.destroy(f.remembered[i],c))end
    assert(next(f.registered)==nil and f.retired[body.address]and f.retired[f.ai.address])
    for i=#f.remembered,1,-1 do assert(f.native.destroy(f.remembered[i],c))end
    assert(f.player.alive and f.pc.alive and next(f.registered)==nil)
end)
check('failed registration retirement retains recovery responsibility for a later cleanup',function()
    local f=fixture();local body,c=f:start();f.retirement_refused=true
    assert(not pcall(f.native.destroy,f.record,c)and not body.alive and f.registered[body.address])
    f.retirement_refused=false;assert(f.native.destroy(f.record,c)and not f.registered[body.address])
    assert(f.retired[body.address]and f.player.alive)
end)
check('failed native cancellation disables queued callbacks and retains a retryable handle',function()
    local f=fixture();local calls=0
    local cancel=f.native.schedule(250,function()calls=calls+1 end)
    f.timer();f.cancel_failure=true;assert(not pcall(cancel));f.timer();assert(calls==1)
    f.cancel_failure=false;cancel();cancel();f.timer();assert(calls==1 and f.cancelled==2)
end)
print('PASS '..checks..' spawn native groups; concrete bindings with fake Unreal objects, no game/relay')
