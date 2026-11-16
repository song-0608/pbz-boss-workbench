-- Concrete UE4SS bindings for the online owned-Actor assembly. All reusable
-- modules come from the immutable accepted release's private dependency loader.
local M={}
local function clone(t)
    if type(t)~='table' then return t end
    local out={};for k,v in pairs(t)do out[k]=clone(v)end;return out
end
function M.new(api,scope,peer,observer,dependencies,Control,bindings,g)
    g=g or _G
    local req=dependencies.require
    for _,key in ipairs({'camera','combat','remote','barrier','protection','arena','visibility'})do
        assert(bindings[key] and bindings[key].binding_verified==true,'current online native binding required: '..key)
    end
    assert(bindings.combat.friendly==0 and bindings.combat.hostile==2
        and bindings.combat.ai_focus_bridge==true,'pinned faction enum/focus mismatch')
    assert(type(g.LoopInGameThreadWithDelay)=='function' and type(g.CancelDelayedAction)=='function')
    local lifecycle=req('object_lifecycle').new(g,bindings.camera)
    local function usable(o)return lifecycle:usable(o)end
    local local_api={now=os.time,find_exact=g.StaticFindObject,usable=usable}
    -- Only the index-zero local controller and the exact newly created Boss are
    -- visible to the native control bridge. No broad NPC search during frames.
    local_api.find_all=function(kind)
        if kind=='PBZPlayerController' then local pc=api.getPlayer1();return pc and {pc} or {} end
        -- The frozen World-boundary check reaches this path only when its exact
        -- old-world lookup is absent/ambiguous. Its reader bounds enumeration
        -- to 4096 and checks old address/name/class; normal frames resolve directly.
        if type(g.FindAllOf)=='function' then return g.FindAllOf(kind) end
        error('online bridge class enumeration unavailable: '..tostring(kind))
    end
    local calls=req('ue_calls').new(local_api)
    local combat_native=req('ue_combat').new(g,bindings.combat)
    local protection=req('player_protection').new(calls,bindings.protection)
    local statics=g.StaticFindObject('/Script/Engine.Default__GameplayStatics')
    local maths=g.StaticFindObject('/Script/Engine.Default__KismetMathLibrary')
    assert(usable(statics) and usable(maths),'native deferred-spawn libraries unavailable')
    local n={now=observer.now,log=observer.log}
    local function current(context,restoring)
        scope:attest(restoring==true)
        local pc=calls:resolve(context.pc)
        observer.identify(pc,context.world)
        local player=calls:resolve(context.player)
        assert(calls:same(pc:K2_GetPawn(),player) and calls:same(player:GetController(),pc),
            'original online player ownership changed')
        return pc,player
    end
    n.prepare=function(id)
        scope:attest(false)
        local catalog=req('boss_catalog')
        local profile=clone(catalog.profile(id));local grant=scope:attest(false)
        assert(profile.identity_verified and profile.exe_sha256==grant.exe_sha256
            and peer:is_boss_class(profile.class_path),'unregistered online Boss profile')
        local config=catalog.configure(id,profile)
        local pc,player=api.getPlayer1();local observed=observer.snapshot()
        assert(observed.native_player and not observed.remote_control,'restore native player before assembly')
        local class=g.LoadAsset(profile.class_path)
        assert(usable(class),'Boss class not loaded')
        local actor_config=class:GetCDO()['Actor Config']
        assert(usable(actor_config) and actor_config:GetFullName():match('^[^ ]+ (.+)$')==profile.config_path
            and actor_config:GetCharacterName():ToString()==profile.display_name,'Boss Actor Config identity changed')
        local ai_class=g.LoadAsset('/PBZCombatAsset/Prototypes/AI/BP_PBZAIController.BP_PBZAIController_C')
        assert(usable(ai_class),'Boss AI controller class missing')
        local p,b=player.CapsuleComponent,class:GetCDO().CapsuleComponent
        local layout_module=id=='073_yanqiansui' and 'yanqiansui_clearance_core' or 'arena_layout'
        local layout,why=req(layout_module).choose(req('ue_arena_layout').new(g,bindings.arena,pc),
            player:K2_GetActorLocation(),player:GetActorForwardVector(),p.CapsuleHalfHeight,
            b.CapsuleHalfHeight,b.CapsuleRadius,1,{},b.CapsuleHalfHeight,b.CapsuleRadius)
        assert(layout,why)
        if id=='073_yanqiansui' then assert(layout.clearance_cm==900 and layout.clearance_samples==24)end
        return {world=observed.world,pc=calls:reference(pc),player=calls:reference(player),
            profile=profile,config=config,class=class,ai_class=ai_class,layout=layout,controllers={}}
    end
    n.protect=function(c)
        local _,player=current(c,false)
        c.protection=protection:capture(player);protection:apply(c.protection)
        c.isolation=req('owned_initialization').new(combat_native,bindings.combat.friendly)
    end
    n.spawn=function(c,remember)
        local pc,player=current(c,false)
        local transform=maths:MakeTransform(c.layout.boss,{Pitch=0,Yaw=c.layout.heading,Roll=0},{X=1,Y=1,Z=1})
        local body=statics:BeginDeferredActorSpawnFromClass(pc,c.class,transform,3,nil,0)
        assert(usable(body),'collision/engine rejected online Boss spawn')
        local record={reference=calls:reference(body),kind='local_body'};remember(record)
        c.body_reference=record.reference
        peer:register(observer.identify(body,c.world),'local_body')
        body.AIControllerClass=c.ai_class
        local finished=statics:FinishSpawningActor(body,transform,0)
        assert(usable(finished) and calls:same(body,finished),'online Boss construction failed or changed identity')
        c.isolation:hold(body,player)
        return record
    end
    n.resolve=function(record,c)
        current(c,false)
        local body=calls:resolve(record.reference);observer.identify(body,c.world)
        return body
    end
    n.register_controller=function(body,c,remember)
        current(c,false)
        local ai=body:GetController()
        if not usable(ai) then return end
        local reference=calls:reference(ai)
        assert(calls:same(ai:K2_GetPawn(),body),'spawned AI belongs to a different body')
        if c.ai then assert(c.ai.address==reference.address and c.ai.name==reference.name
            and c.ai.class==reference.class,'owned AI replaced during initialization');return end
        c.ai=reference;remember({reference=reference,kind='controller'})
        peer:register(observer.identify(ai,c.world),'controller')
    end
    n.readiness=function(body,c,poll)
        local _,player=current(c,false)
        assert(protection:verify(c.protection) and c.isolation:verify(),'initialization player/faction isolation changed')
        local ai=body:GetController()
        if body:HasAuthority()~=true then return nil end
        if not usable(ai) then
            if poll%4==0 then body:SpawnDefaultController() end
            return nil
        end
        if not (usable(ai.BrainComponent) and usable(ai.SGameAIComponent) and ai.SGameAIComponent.bInitialized==true
            and usable(body.AbilitySystemComponent)) then return nil end
        local items=body.AbilitySystemComponent.ActivatableAbilities.Items
        local count=items:GetArrayNum();assert(type(count)=='number' and count>=0 and count<=512,'online ASC bound')
        if count==0 then return nil end
        local found={}
        for index=1,count do
            local spec=items[index]
            if usable(spec.Ability) then
                local path=spec.Ability:GetClass():GetFullName():match('^[^ ]+ (.+)$')
                found[path]=(found[path] or 0)+1
            end
        end
        for _,definition in pairs(c.config.skills)do
            assert(peer:resolve_local_action(c.profile.class_path,definition.id)==c.profile.skills[definition.id].class_path)
            if found[c.profile.skills[definition.id].class_path]~=1 then return nil end
        end
        return tostring(count)..'|'..ai:GetFullName()
    end
    n.suspend=function(body,c)
        current(c,false)
        local ai=calls:resolve(assert(c.ai,'owned AI was never registered'))
        ai.SGameAIComponent:StopAI();ai.BrainComponent:StopLogic('online owned Boss ready')
        ai.BrainComponent:SetComponentTickEnabled(false);ai:SetActorTickEnabled(false)
        assert(ai.SGameAIComponent.bAIStarted==false and ai.BrainComponent:IsRunning()==false and not ai.BrainComponent:IsComponentTickEnabled()
            and not ai:IsActorTickEnabled(),'online Boss AI suspension not acknowledged')
    end
    n.release_initialization=function(c)current(c,false);c.isolation:release()end
    n.restore_player=function(c)
        if not c.protection or c.protection.restored then return true end
        current(c,true);return protection:restore(c.protection)
    end
    n.create_control=function(body,c)
        current(c,false)
        local profile=c.profile;profile.instance_name=body:GetFullName()
        local a={};for k,v in pairs(local_api)do a[k]=v end
        a.find_all=function(kind)
            if kind=='PBZCharacter_NPC' then return {body} end
            return local_api.find_all(kind)
        end
        a.read_health=function(pawn)calls:reference(pawn.AttributeSetBase);return pawn.AttributeSetBase.Health.CurrentValue end
        a.cancel_skill=function(spec,binding)return calls:cancel(spec,binding)end
        a.owned_temporary={boss=calls:reference(body),ai=c.ai}
        a.player_protection=protection
        local remote_binding=clone(bindings.remote);remote_binding.scheduler_trial=true;remote_binding.now=a.now
        a.remote=req('remote_control').new(calls,req('ue_remote').new(bindings.remote),remote_binding)
        a.combat=req('combat_identity').new(calls,combat_native,bindings.combat)
        a.camera=req('camera_rig').new(calls,req('ue_camera').new(g,profile.camera),profile.camera)
        a.input_barrier=req('input_barrier').new(calls,req('ue_input_barrier').new(bindings.barrier),bindings.barrier)
        a.combo_scheduler=req('combo_scheduler').new(calls,a.remote,a.cancel_skill,function(key,value)n.log(key..'='..tostring(value))end)
        a.face_target=function(b,t)
            local p,q=b:K2_GetActorLocation(),t:K2_GetActorLocation()
            local x,y=q.X-p.X,q.Y-p.Y;assert(x*x+y*y>1,'online target overlaps Boss')
            local rotation={Pitch=0,Yaw=math.deg(math.atan(y,x)),Roll=0}
            b.RootComponent:K2_SetWorldRotation(rotation,false,{},true);b:GetController():SetControlRotation(rotation)
            local f=b:GetActorForwardVector()
            assert((f.X*x+f.Y*y)/math.sqrt(x*x+y*y)>0.98,'online Boss attack facing unverified')
        end
        a.target_selector=req('target_selector').new(calls,{
            candidates=function()local actors=api.game.listEnemies();return actors end,
            health=a.read_health,usable=usable,position=function(p)return p:K2_GetActorLocation()end,
            relation=combat_native.relation,
            visible=function(b,t)return b:GetController():LineOfSightTo(t,{X=0,Y=0,Z=0},false)==true end,
        },{hostile=bindings.combat.hostile,radius=3000,limit=256,require_visibility=true})
        local runtime_host={}
        for _,key in ipairs({'on_game_thread','bind_key','every_frame','cancel_frame','read_input','log'})do
            runtime_host[key]=function()error('online runtime host not assembled')end
        end
        local control=Control.new(a,profile,c.config,scope,peer,runtime_host,dependencies)
        for k,v in pairs(req('ue_host').new(control.bridge,profile.input,g))do runtime_host[k]=v end
        if n.mount_workbench then
            local pc=calls:resolve(c.pc)
            local camera=req('ue_camera').new(g,profile.camera)
            local layer=req('workbench_input').new(calls,a.input_barrier,{
                create=function()return camera.spawn_camera(pc,body,profile.camera)end,
                finish=function(owner)
                    local transform=maths:MakeTransform(body:K2_GetActorLocation(),
                        {Pitch=0,Yaw=0,Roll=0},{X=1,Y=1,Z=1})
                    local finished=statics:FinishSpawningActor(owner,transform,profile.camera.spawn_scale)
                    return usable(finished)and calls:same(owner,finished)
                end,
                destroy=camera.destroy_camera,
            })
            n.mount_workbench(control,runtime_host,layer,pc,profile.id)
        end
        return control
    end
    n.destroy=function(record,c)
        scope:attest(true)
        local object=calls:optional(record.reference)
        if not object then return true end
        observer.identify(object,c.world)
        if record.kind=='controller' then
            local pawn=object:K2_GetPawn()
            assert(not usable(pawn) or (calls:same(pawn,calls:optional(assert(c.body_reference)))),
                'owned AI acquired another Pawn; disposal refused')
        end
        local leftover
        if record.kind=='local_body' then
            -- FinishSpawningActor may create an AI and then fail. Recover that
            -- controller even when initialization never reached the next poll.
            local ai=object:GetController()
            if usable(ai) then
                assert(not calls:same(ai,calls:resolve(c.pc)) and calls:same(ai:K2_GetPawn(),object),
                    'unrecognized owner of the temporary Boss')
                observer.identify(ai,c.world);leftover=calls:reference(ai)
                if not peer.closed then peer:register(observer.identify(ai,c.world),'controller') end
            end
        end
        object:K2_DestroyActor()
        assert(not calls:optional(record.reference),'owned online Actor destruction not acknowledged')
        if leftover then
            local ai=calls:optional(leftover)
            if ai then
                local pawn=ai:K2_GetPawn()
                assert(not usable(pawn),'leftover AI acquired a living Pawn')
                ai:K2_DestroyActor();assert(not calls:optional(leftover),'leftover online AI destruction unverified')
            end
        end
        return true
    end
    n.schedule=function(ms,callback)
        assert(ms==250);local active,handle=true,nil
        handle=g.LoopInGameThreadWithDelay(ms,function()if active then callback()end end)
        assert(handle~=nil,'online assembly timer missing handle')
        return function()if active then active=false;g.CancelDelayedAction(handle)end end
    end
    return n
end
return M
