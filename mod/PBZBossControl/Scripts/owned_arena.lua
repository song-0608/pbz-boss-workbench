local Arena={}
function Arena.start(options)
assert(type(options)=="table","arena options required")
local experiment_player_entry=options.player_entry==true
local experiment_boss_id=options.boss_id
local experiment_boss_candidate=options.boss_candidate
assert(not experiment_boss_candidate or(not experiment_player_entry and options.practice and options.interactive
    and options.camera_binding and options.combat_binding and options.remote_binding and options.barrier_binding
    and options.protection_binding and options.arena_binding and options.player_ui_binding
    and not options.skill_lab and not options.extra_skills and not options.death_trial and not options.player_key_trial),
    'candidate requires an independent complete protected developer assembly')
local player_ui
local workbench
local transition_trial_used=false
local map_travel_guard_installed=false
local experiment_active_skill_death_trial=options.active_skill_death_trial
local experiment_attest=options.attest
local experiment_barrier_binding=options.barrier_binding
local experiment_batch_skills=options.batch_skills
local experiment_camera_binding=options.camera_binding
local experiment_combat_binding=options.combat_binding
local experiment_death_trial=options.death_trial
local experiment_extra_skills=options.extra_skills
local experiment_interactive=options.interactive
local experiment_keymap=options.keymap
local experiment_native_death_reason=options.native_death_reason
local experiment_player_key_trial=options.player_key_trial
local experiment_practice=options.practice
local experiment_protection_binding=options.protection_binding
local experiment_remote_binding=options.remote_binding
local experiment_skill_lab=options.skill_lab
local experiment_combo_scheduler_trial=options.combo_scheduler_trial==true
assert(not experiment_combo_scheduler_trial or(experiment_skill_lab and experiment_practice and not experiment_player_entry),
    'combo scheduler requires explicit protected developer lab')
local experiment_target_cycle=options.target_cycle
-- 用途：独立研究副本中的临时阿花实验；普通测试60秒，受保护训练最多10分钟。
-- 实验监督器须在本文件前注入本轮短时签发凭据；默认主入口不会执行本实验。
assert(type(experiment_attest)=="function","external experiment grant required")
local function log(key,value)print("PBZ_CONTROL_LIFECYCLE:"..key.."="..tostring(value).."\n")end
local lifecycle=experiment_camera_binding and require('object_lifecycle').new(_G,experiment_camera_binding)
local function valid(value)return value and value:IsValid()and(not lifecycle or lifecycle:usable(value))end
local actor, ai, session, frame_handle, runtime, target_actor, target_ai
local extra_targets={}
local setup_protection,setup_ticket
local begin_experiment,wait_for_player,recover_initialization
local gate_started,stationary_polls=0,0
local readiness_player,readiness_health,health_stable_polls
local spawn_attempts=0
local rejected_layouts={}
local current_layout_key
local initialization_deadline
local assembly_generation=0
local initialized_owned={}
local function spawn_state(label,pawn)
    -- 用途：对本轮自建对象记录生成前后状态，区分默认角色、构造失败和异步初始化；不改Role。
    local ok,why=pcall(function()
        local root=pawn.RootComponent
        log('SPAWN_STATE',label..'|object='..pawn:GetFullName()..'|address='..tostring(pawn:GetAddress())
            ..'|role='..tostring(pawn.Role)..'|authority='..tostring(pawn:HasAuthority())
            ..'|engine_usable='..tostring(not lifecycle or lifecycle:usable(pawn))
            ..'|destroying='..tostring(pawn:IsActorBeingDestroyed())..'|root='..tostring(valid(root)))
    end)
    if not ok then log('SPAWN_STATE_UNAVAILABLE',label..'|'..tostring(why))end
end
local function guard()
    local grant=experiment_attest()
    assert(grant and grant.offline and grant.isolated and grant.expires_at>os.time(),"experiment grant expired")
    return grant
end
local function cleanup()
    guard()
    if workbench then assert(workbench:shutdown(),'workbench cleanup failed')end
    if runtime then runtime:stop("bounded interactive timeout");runtime=nil end
    if player_ui then player_ui.close()end
    if frame_handle then CancelDelayedAction(frame_handle);frame_handle=nil end
    if session and session.receipt then
        local ok,why=session:restore("bounded lifecycle cleanup")
        log("RESTORE",tostring(ok).."|"..tostring(why))
    end
    -- 用途：只清理本实验新建的角色和控制器；不会删除关卡原有Boss。
    if session and session.receipt then log("DESTROY_SKIPPED","restoration unverified; supervisor will end isolated process");return false end
    if valid(actor)then ai=ai or actor:GetController()end
    if valid(target_actor)then target_ai=target_ai or target_actor:GetController()end
    local function destroy_owned(object,label)
        if valid(object)then object:K2_DestroyActor()end
        -- 用途：销毁后不再调用原生方法；确认引擎不可用不等于宣称已完成GC。
        assert(not valid(object),'owned cleanup not acknowledged: '..label)
        log('OWNED_DESTROY_VERIFIED',label..'|engine_unusable=true')
    end
    destroy_owned(actor,'boss');log('DESTROY_REQUESTED',true)
    destroy_owned(ai,'boss_controller')
    destroy_owned(target_actor,'target');log('TRAINING_TARGET_DESTROY_REQUESTED',true)
    destroy_owned(target_ai,'target_controller')
    for _,entry in ipairs(extra_targets)do
        if valid(entry.actor)then entry.ai=entry.ai or entry.actor:GetController()end
        destroy_owned(entry.actor,'extra_target');destroy_owned(entry.ai,'extra_target_controller')
    end
    extra_targets={}
    initialized_owned={}
    if setup_ticket and not setup_ticket.restored then setup_protection:restore(setup_ticket)end
    return true
end
recover_initialization=function(why)
    log('INITIALIZATION_ATTEMPT_REJECTED',why)
    if current_layout_key and not rejected_layouts[current_layout_key]then
        rejected_layouts[current_layout_key]=true
        log('NAVIGATION_LAYOUT_REJECTED',current_layout_key..'|stage=initialization')
    end
    local clean,result=pcall(cleanup)
    if clean and result==true and setup_ticket and setup_ticket.restored then
        -- 用途：仅在主角恢复和所有自建对象销毁均已回读后有限重试；任何清理失败都不能继续生成。
        actor,ai,target_actor,target_ai,session,setup_protection,setup_ticket=nil,nil,nil,nil,nil,nil,nil
        if spawn_attempts<3 and (not initialization_deadline or os.time()<initialization_deadline-5)then
            log('INITIALIZATION_RETRY',spawn_attempts)
            gate_started,stationary_polls=0,0
            ExecuteInGameThreadWithDelay(1000,wait_for_player)
        else
            log('PREREQUISITE_NOT_READY','temporary boss initialization did not become ready in three cleaned attempts')
            log('PREREQUISITE_RETRY_SAFE',true)
            log('END','initialization rejected before takeover; original player restoration verified')
        end
    else log('ISSUE_CLEANUP',clean and 'cleanup restoration not verified' or result)end
end
local function when_ready(fn)
    -- 用途：以真实Controller/Brain/授予能力为就绪条件；固定多等几秒不能修复未初始化实例。
    local last_reason,attempts,stable_count,last_counts,last_state=nil,0,0,nil,nil
    local function poll()
        local ok,why=pcall(function()
            local grant=guard();assert(grant.expires_at-os.time()>15,'initialization exhausted cleanup margin')
            assert(not initialization_deadline or os.time()<initialization_deadline,'bounded initialization budget exhausted')
            assert(valid(actor),'temporary actor expired during initialization')
            attempts=attempts+1
            assert(attempts<=64,'actor/controller initialization did not settle within 64 readiness polls')
            local all=true;local counts={};local states={}
            local owned=target_actor and{actor,target_actor}or{actor}
            for _,entry in ipairs(extra_targets)do owned[#owned+1]=entry.actor end
            for _,pawn in ipairs(owned)do
                assert(valid(pawn),'owned training actor expired')
                local authority=pawn:HasAuthority()==true
                local controller=pawn:GetController()
                if authority and not valid(controller)and attempts%4==0 and valid(pawn.AIControllerClass)then pawn:SpawnDefaultController();controller=pawn:GetController()end
                local asc=pawn.AbilitySystemComponent
                -- 用途：初始化尚未完成时不StopAI，避免中断角色的异步能力授予/初始化链；主角由setup保护隔离。
                states[#states+1]=(pawn==actor and'boss'or'target')..':authority='..tostring(authority)..',controller='..tostring(valid(controller))
                    ..',class='..tostring(valid(pawn.AIControllerClass))..',brain='..tostring(valid(controller)and valid(controller.BrainComponent))
                    ..',abilities='..tostring(valid(asc)and asc.ActivatableAbilities.Items:GetArrayNum()or-1)
                local ai_ready=initialized_owned[pawn:GetAddress()]or(valid(controller)and valid(controller.SGameAIComponent)and controller.SGameAIComponent.bInitialized==true)
                if not(authority and valid(controller)and valid(controller.BrainComponent)and ai_ready and valid(asc)and asc.ActivatableAbilities.Items:GetArrayNum()>0)then all=false
                else counts[#counts+1]=tostring(asc.ActivatableAbilities.Items:GetArrayNum())end
            end
            local signature=table.concat(counts,',')
            local state=table.concat(states,';');if state~=last_state then log('INITIALIZATION_STATE',state);last_state=state end
            if all and signature==last_counts then stable_count=stable_count+1 else stable_count=0 end
            last_counts=signature
            -- 用途：授予列表连续三秒稳定后才停止AI，避免角色异步初始化重启Brain。
            if all and stable_count>=12 then
                -- 用途：只在所有角色的授予列表稳定后暂停AI，再交给下一阶段；不提前打断初始化。
                for _,pawn in ipairs(owned)do
                    local controller=pawn:GetController()
                    if not initialized_owned[pawn:GetAddress()]then
                        if valid(controller.SGameAIComponent)then controller.SGameAIComponent:StopAI()end
                        controller.BrainComponent:StopLogic('initialized owned character waiting for player input')
                        if experiment_remote_binding then
                            -- Owned training characters stay dormant between takeovers. A delayed
                            -- AI restart must not attack the restored player or start a skill.
                            controller.BrainComponent:SetComponentTickEnabled(false)
                            controller:SetActorTickEnabled(false)
                            assert(controller.SGameAIComponent.bAIStarted==false
                                and not controller.BrainComponent:IsComponentTickEnabled()
                                and not controller:IsActorTickEnabled(),'owned idle AI suspension not verified')
                            log('OWNED_IDLE_AI_SUSPENDED',pawn:GetFullName())
                        end
                        initialized_owned[pawn:GetAddress()]=true
                    end
                end
                log('INITIALIZATION_READY_POLLS',attempts);fn();return
            end
            local reason='waiting for AI and granted abilities'
            if last_reason~=reason then log('INITIALIZATION_WAIT',reason);last_reason=reason end
            ExecuteInGameThreadWithDelay(250,poll)
        end)
        if not ok then
            recover_initialization(why)
        end
    end
    ExecuteInGameThreadWithDelay(250,poll)
end
begin_experiment=function()
ExecuteInGameThread(function()
    local construction_rejected=false
    local ok,why=pcall(function()
        local grant=guard()
        current_layout_key=nil
        if options.player_ui_binding then player_ui=require('ue_player_ui').new(_G,options.player_ui_binding,options.attest)end
        assembly_generation=assembly_generation+1
        spawn_attempts=spawn_attempts+1
        initialization_deadline=initialization_deadline or os.time()+80
        log('SPAWN_ATTEMPT',spawn_attempts)
        local pc
        for _,candidate in ipairs(FindAllOf("PBZPlayerController") or {})do
            if valid(candidate) and valid(candidate.Pawn) and candidate:GetFullName():find(":PersistentLevel.",1,true)then
                assert(not pc,"ambiguous player controller");pc=candidate
            end
        end
        assert(pc,"local gameplay player missing")
        local player=pc.Pawn
        log('SETUP_PLAYER_BASELINE',player:GetFullName()..'|health='..tostring(player.AttributeSetBase.Health.CurrentValue))
        if experiment_protection_binding then
            local setup_calls=require('ue_calls').new({find_exact=StaticFindObject})
            setup_protection=require('player_protection').new(setup_calls,experiment_protection_binding)
            setup_ticket=setup_protection:capture(player);setup_protection:apply(setup_ticket)
        end
        local initialization_isolation
        local function isolate_initialization(pawn)
            if not(options.arena_binding and options.player_ui_binding and experiment_combat_binding)then return end
            initialization_isolation=initialization_isolation or require('owned_initialization').new(
                require('ue_combat').new(_G,experiment_combat_binding),experiment_combat_binding.friendly)
            initialization_isolation:hold(pawn,player)
            log('OWNED_INITIALIZATION_ISOLATED',pawn:GetFullName())
        end
        local assembly_profile
        if experiment_boss_candidate then
            assembly_profile=require('boss_candidate').prepare(experiment_boss_candidate,grant,LoadAsset,log)
        else assembly_profile=experiment_player_entry and require('boss_catalog').profile(experiment_boss_id)or require('profiles.ahua')end
        assert(assembly_profile.identity_verified==true and assembly_profile.exe_sha256==grant.exe_sha256,'independent Boss identity required')
        local class=LoadAsset(assembly_profile.class_path)
        assert(valid(class),"verified Boss class missing")
        local actor_config=class:GetCDO()["Actor Config"]
        assert(actor_config:GetFullName():match('^[^ ]+ (.+)$')==assembly_profile.config_path,'Boss config reference changed')
        assert(actor_config:GetCharacterName():ToString()==assembly_profile.display_name,"identity changed")
        local target_class=class
        if assembly_profile.training_target_profile then
            local target_profile=require(assembly_profile.training_target_profile)
            assert(target_profile.identity_verified==true and target_profile.exe_sha256==grant.exe_sha256,
                'independent training target identity required')
            target_class=LoadAsset(target_profile.class_path)
            assert(valid(target_class),'verified training target class missing')
            local target_config=target_class:GetCDO()['Actor Config']
            assert(target_config:GetFullName():match('^[^ ]+ (.+)$')==target_profile.config_path
                and target_config:GetCharacterName():ToString()==target_profile.display_name,'training target identity changed')
            log('TRAINING_TARGET_PROFILE',target_profile.id..'|'..target_profile.class_path..'|'..target_profile.config_path)
        end
        -- 用途：自建实例不经过游戏NPC生成器，显式加载该Boss实机使用的控制器类并只配置本实验实例。
        local controller_class=LoadAsset('/PBZCombatAsset/Prototypes/AI/BP_PBZAIController.BP_PBZAIController_C')
        assert(valid(controller_class),'confirmed AI controller class unavailable')
        local location,forward=player:K2_GetActorLocation(),player:GetActorForwardVector()
        local capsule_ok,capsule_why=pcall(function()
            -- 用途：核对玩家与Boss碰撞胶囊的中心高度差；先记录，不用模型外观猜碰撞体。
            local p=player.CapsuleComponent;local b=class:GetCDO().CapsuleComponent
            log('SPAWN_CAPSULES','player_half='..tostring(p.CapsuleHalfHeight)..'|player_radius='..tostring(p.CapsuleRadius)
                ..'|boss_half='..tostring(b.CapsuleHalfHeight)..'|boss_radius='..tostring(b.CapsuleRadius)
                ..'|player_z='..tostring(location.Z))
        end)
        if not capsule_ok then log('SPAWN_CAPSULES_UNAVAILABLE',capsule_why)end
        local heading=math.deg(math.atan(forward.Y,forward.X))
        local layout
        if options.arena_binding then
            local projected=require('ue_arena_layout').new(_G,options.arena_binding,pc)
            local p,b,t=player.CapsuleComponent,class:GetCDO().CapsuleComponent,target_class:GetCDO().CapsuleComponent
            local reason
            layout,reason=require('arena_layout').choose(projected,location,forward,
                p.CapsuleHalfHeight,b.CapsuleHalfHeight,b.CapsuleRadius,spawn_attempts,rejected_layouts,
                t.CapsuleHalfHeight,t.CapsuleRadius)
            if not layout then construction_rejected=true;error(reason)end
            current_layout_key=layout.key
            heading=layout.heading
            log('NAVIGATION_LAYOUT_VERIFIED',string.format('boss=%.3f,%.3f,%.3f|targets=%d',
                layout.boss.X,layout.boss.Y,layout.boss.Z,#layout.targets))
        end
        local maths=StaticFindObject("/Script/Engine.Default__KismetMathLibrary")
        local statics=StaticFindObject("/Script/Engine.Default__GameplayStatics")
        assert(valid(maths) and valid(statics),"native libraries missing")
        -- 用途：沿同一局部训练区域生成；远离主角脚边的交互设施，仍由引擎碰撞规则决定是否接受。
        local spawn_side=spawn_attempts==2 and 180 or spawn_attempts==3 and -180 or 0
        log('SPAWN_LOCAL_OFFSET','forward=450|side='..spawn_side)
        local transform=maths:MakeTransform(layout and layout.boss or {X=location.X+forward.X*450-forward.Y*spawn_side,Y=location.Y+forward.Y*450+forward.X*spawn_side,Z=location.Z},
            {Pitch=0,Yaw=heading,Roll=0},{X=1,Y=1,Z=1})
        -- 用途：显式提供本机核对的Scale参数；3表示不能消除碰撞时拒绝生成，0表示覆盖根缩放。
        actor=statics:BeginDeferredActorSpawnFromClass(pc,class,transform,3,nil,0)
        if not valid(actor)then construction_rejected=true;error('deferred spawn rejected by collision or engine')end
        log("DEFERRED_ACTOR",actor:GetFullName())
        spawn_state('class_default',class:GetCDO())
        spawn_state('before_finish',actor)
        actor.AIControllerClass=controller_class
        local finished=statics:FinishSpawningActor(actor,transform,0)
        log('FINISH_SPAWN_STATE','actor_usable='..tostring(valid(actor)==true)..'|returned_usable='..tostring(valid(finished)==true))
        if not valid(finished)or not valid(actor)then
            construction_rejected=true;error('FinishSpawningActor rejected construction; no takeover attempted')
        end
        assert(finished:GetAddress()==actor:GetAddress(),'FinishSpawningActor identity mismatch')
        isolate_initialization(actor)
        log("SPAWNED",actor:GetFullName())
        log('SPAWN_AUTHORITY',actor:HasAuthority())
        spawn_state('after_finish',actor)
        -- 用途：生成同一帧的角色可能未就绪；权限进入有界就绪门槛，始终不修改Role或绕过检查。
        local function spawn_training_target(index)
            -- 用途：先等可控Boss完全就绪，再生成训练敌人，避免同帧并行初始化同类战斗角色。
            -- 用途：首选本构建已成功实测的位置；清理后的有限重试才换相邻布局，不反复尝试同一坏位置。
            local side=spawn_side+(index==2 and(spawn_attempts==2 and 250 or 350)or 0)
            local along=650
            if index==2 and spawn_attempts>=3 then side=0;along=950 end
            local target_transform=maths:MakeTransform(layout and layout.targets[index or 1] or {X=location.X+forward.X*along-forward.Y*side,Y=location.Y+forward.Y*along+forward.X*side,Z=location.Z},
                {Pitch=0,Yaw=heading+180,Roll=0},{X=1,Y=1,Z=1})
            local pawn=statics:BeginDeferredActorSpawnFromClass(pc,target_class,target_transform,3,nil,0)
            assert(valid(pawn),'owned training target spawn rejected')
            if index==2 then extra_targets[#extra_targets+1]={actor=pawn}else target_actor=pawn end
            pawn.AIControllerClass=controller_class
            spawn_state('target_before_finish_'..tostring(index or 1),pawn)
            local target_finished=statics:FinishSpawningActor(pawn,target_transform,0)
            log('TARGET_FINISH_SPAWN_STATE',tostring(index or 1)..'|actor_usable='..tostring(valid(pawn)==true)
                ..'|returned_usable='..tostring(valid(target_finished)==true)..'|side='..side..'|along='..along)
            assert(valid(pawn)and valid(target_finished),'training target construction rejected before native actor queries')
            assert(target_finished:GetAddress()==pawn:GetAddress(),'training target finish identity mismatch')
            isolate_initialization(pawn)
            spawn_state('target_after_finish_'..tostring(index or 1),pawn)
            log('TRAINING_TARGET_AUTHORITY_'..tostring(index or 1),pawn:HasAuthority())
            if pawn:HasAuthority()==true and not valid(pawn:GetController())then pawn:SpawnDefaultController()end
            log('TRAINING_TARGET_'..tostring(index or 1),pawn:GetFullName())
            local p=pawn:K2_GetActorLocation();log('TRAINING_TARGET_POSITION_'..tostring(index or 1),string.format('%.3f,%.3f,%.3f',p.X,p.Y,p.Z))
        end
        -- 用途：运行时生成的Pawn未必自动创建AIController；调用已核对的引擎无参接口。
        if actor:HasAuthority()==true and not valid(actor:GetController()) then actor:SpawnDefaultController();log("DEFAULT_CONTROLLER_REQUESTED",true)end
        -- 用途：给异步战斗资源留出初始化时间；不能把刚生成的空ASC误判为角色没有技能。
        local function install_controls(settled)
            if options.arena_binding and not settled then
                local readiness=require('owned_readiness').new(location,{layout.boss,layout.targets[1],layout.targets[2]})
                local polls=0
                local function settle()
                    local ok,why=pcall(function()
                        local grant=guard();polls=polls+1
                        assert(polls<=24 and grant.expires_at-os.time()>15
                            and os.time()<initialization_deadline,'owned layout did not settle within bounded initialization')
                        assert(not setup_ticket or setup_protection:verify(setup_ticket),'protected player changed during owned settling')
                        assert(not initialization_isolation or initialization_isolation:verify(),'owned initialization isolation changed')
                        local owned={actor,target_actor,extra_targets[1]and extra_targets[1].actor}
                        assert(#owned==3,'exact owned layout required before exposure')
                        local rows={}
                        for index,pawn in ipairs(owned)do
                            assert(valid(pawn)and valid(pawn.AttributeSetBase),'owned settling participant unavailable: '..index)
                            rows[index]={health=pawn.AttributeSetBase.Health.CurrentValue,
                                position=pawn:K2_GetActorLocation(),velocity=pawn:GetVelocity()}
                            if polls==1 then
                                local p,v=rows[index].position,rows[index].velocity
                                log('OWNED_LAYOUT_SAMPLE',string.format('index=%d|health=%.6f|position=%.3f,%.3f,%.3f|velocity=%.3f,%.3f,%.3f|expected=%.3f,%.3f,%.3f',
                                    index,rows[index].health,p.X,p.Y,p.Z,v.X,v.Y,v.Z,
                                    readiness.expected[index].X,readiness.expected[index].Y,readiness.expected[index].Z))
                            end
                        end
                        if readiness:poll(rows)then
                            log('OWNED_LAYOUT_SETTLED','polls='..polls..'|boss_health='..rows[1].health
                                ..'|target_health='..rows[2].health..','..rows[3].health)
                            install_controls(true)
                        else ExecuteInGameThreadWithDelay(250,settle)end
                    end)
                    if not ok then recover_initialization(why)end
                end
                ExecuteInGameThreadWithDelay(250,settle);return
            end
            if options.arena_binding then
                local targets={target_actor}
                for _,entry in ipairs(extra_targets)do targets[#targets+1]=entry.actor end
                local visible,reason=require('arena_layout').visible(player_ui and player_ui.visible,actor,targets)
                if not visible then
                    rejected_layouts[layout.key]=true
                    log('NAVIGATION_LAYOUT_REJECTED',layout.key)
                    recover_initialization(reason);return
                end
                log('NAVIGATION_TARGET_VISIBILITY_VERIFIED',#targets)
            end
            if initialization_isolation then initialization_isolation:release(log);initialization_isolation=nil end
            local deferred=false
            local ready,error=pcall(function()
                guard();assert(valid(actor),"temporary actor expired")
                ai=actor:GetController()
                log("AI_CONTROLLER",valid(ai) and ai:GetFullName() or "not ready")
                local asc=actor.AbilitySystemComponent
                assert(valid(asc),"temporary ASC missing")
                local items=asc.ActivatableAbilities.Items
                local count=items:GetArrayNum();assert(count>=0 and count<=512,"ability bound")
                log("GRANTED_COUNT",count)
                for i=1,count do
                    local spec=items[i]
                    if valid(spec.Ability)then log("GRANTED_ABILITY",spec.Ability:GetClass():GetFullName())end
                end
                if experiment_death_trial then
                    -- 开发只读：本进程已核对EffectsLibrary的GameplayTag→GameplayEffectContainer声明。
                    -- 只记录已授予技能的容器和包装器引用，不创建效果、不调用CDO战斗逻辑。
                    local inspected,problem=pcall(function()
                        for i=1,count do
                            local ability=items[i].Ability
                            if valid(ability)and ability:IsA('/Script/ProjectPBZ.PBZGameplayAbility')then
                                local entries=0
                                ability.EffectsLibrary:ForEach(function(key,value)
                                    entries=entries+1;assert(entries<=32,'bounded effect containers required')
                                    local tag,container=key:get().TagName:ToString(),value:get()
                                    log('ABILITY_EFFECT_CONTAINER',ability:GetClass():GetFullName()..'|tag='..tag)
                                    for _,field in ipairs({'EffectWrappers','LegacyEffects'})do
                                        local array=container[field];local n=array:GetArrayNum()
                                        assert(n>=0 and n<=32,'bounded effect references required')
                                        for j=1,n do
                                            local object=array[j]
                                            log('ABILITY_EFFECT_REFERENCE',tag..'|'..field..'|'..(valid(object)and object:GetFullName()or'None'))
                                        end
                                    end
                                end)
                            end
                        end
                    end)
                    if not inspected then log('ABILITY_EFFECT_INSPECTION_UNAVAILABLE',problem)end
                end
                assert(valid(ai) and valid(ai.BrainComponent),"default AI not initialized")
                ai.SGameAIComponent:StopAI();ai.BrainComponent:StopLogic('ready for owned offline controls')
                -- Each assembly gets independent state; never mutate cached profile evidence across switches.
                local function clone(value)
                    if type(value)~='table'then return value end
                    local copy={};for key,item in pairs(value)do copy[key]=clone(item)end;return copy
                end
                local profile=clone(assembly_profile);profile.instance_name=actor:GetFullName()
                local native_combo=profile.skills.attack_01
                local native_combo_enabled=experiment_combo_scheduler_trial or(native_combo and native_combo.scheduler_runtime_verified==true
                    and (experiment_player_key_trial or(experiment_player_entry and native_combo.player_key_verified==true)))
                -- 用途：本次活体已授予列表和声明作为实验绑定；不改正式配置中的可玩验收标记。
                if experiment_boss_candidate then
                    require('boss_candidate').bind_granted(profile,items,valid,log)
                elseif not experiment_player_entry then
                    profile.skills.skill_01.binding_verified=true
                    profile.skills.skill_01.cancel_binding_verified=true
                end
                local sequence={'slot1'}
                if experiment_batch_skills and not experiment_boss_candidate then
                    -- 用途：只加入本次确证已授予的完整类名，不能把被动、子技能当作独立按键。
                    local selected={heavy_01='GA_AHua_Heavy_01',skill_02='GA_AHua_Skill_02',dash='GA_AHua_SpecialMove_Dash'}
                    if experiment_extra_skills then
                        selected.heavy_02='GA_AHua_Heavy_02';selected.special_03='GA_AHua_Special_03'
                    end
                    for id,name in pairs(selected)do
                        for index=1,count do
                            local ability=items[index].Ability
                            if valid(ability)then
                                local path=ability:GetClass():GetFullName():match('^[^ ]+ (.+)$')
                                if path:match('%.([^%.]+)_C$')==name then
                                    if experiment_player_entry then
                                        assert(profile.skills[id]and profile.skills[id].class_path==path,'player skill class changed: '..id)
                                    else
                                        profile.skills[id]={name=name,class_path=path,binding_verified=true,active_count_field='ActiveCount',
                                            cancel_binding_verified=true,cancel_function='K2_CancelAbility',requires_target=true}
                                    end
                                end
                            end
                        end
                    end
                end
                local api={now=os.time,attest=experiment_attest,find_all=FindAllOf,find_exact=StaticFindObject}
                local calls=require("ue_calls").new(api)
                local incoming_health
                api.read_health=function(pawn)
                    -- 用途：Health路径已用于实机训练敌人采样；先验证属性集仍可用，再读取，绝不写回。
                    local attrs=pawn.AttributeSetBase
                    calls:reference(attrs)
                    local value=attrs.Health.CurrentValue
                    if options.incoming_combat_trial and calls:same(pawn,actor)and value~=incoming_health then
                        log('OWNED_COMBAT_HEALTH','before='..tostring(incoming_health)..'|after='..tostring(value))
                        incoming_health=value
                    end
                    return value
                end
                if setup_ticket then setup_protection:restore(setup_ticket);log('SETUP_PLAYER_PROTECTION_RESTORED',true)end
                if experiment_protection_binding then api.player_protection=require('player_protection').new(calls,experiment_protection_binding)end
                if experiment_remote_binding then
                    local binding={binding_verified=experiment_remote_binding.binding_verified,scheduler_trial=native_combo_enabled==true,now=api.now}
                    api.remote=require('remote_control').new(calls,require('ue_remote').new(experiment_remote_binding),binding)
                end
                if experiment_barrier_binding then
                    api.input_barrier=require('input_barrier').new(calls,require('ue_input_barrier').new(experiment_barrier_binding),experiment_barrier_binding)
                end
                if experiment_combat_binding then
                    target_ai=target_actor:GetController()
                    assert(valid(target_ai)and valid(target_ai.BrainComponent),'training target AI missing')
                    target_ai.BrainComponent:StopLogic('owned offline training target')
                    if experiment_remote_binding then target_ai.SGameAIComponent:StopAI();target_ai.BrainComponent:SetComponentTickEnabled(false);target_ai:SetActorTickEnabled(false)end
                    api.combat=require('combat_identity').new(calls,require('ue_combat').new(_G,experiment_combat_binding),experiment_combat_binding)
                    for _,entry in ipairs(extra_targets)do
                        entry.ai=entry.actor:GetController();assert(valid(entry.ai)and valid(entry.ai.BrainComponent),'second target AI missing')
                        entry.ai.BrainComponent:StopLogic('owned offline alternate target')
                        entry.ai.SGameAIComponent:StopAI();entry.ai.BrainComponent:SetComponentTickEnabled(false);entry.ai:SetActorTickEnabled(false)
                    end
                    if experiment_target_cycle then
                        api.target_selector=require('target_selector').new(calls,{
                            candidates=function()return FindAllOf('PBZCharacter_NPC')or{}end,
                            health=function(pawn)return pawn.AttributeSetBase.Health.CurrentValue end,
                            usable=function(pawn)return not pawn:IsActorBeingDestroyed()end,
                            position=function(pawn)return pawn:K2_GetActorLocation()end,
                            relation=api.combat.native.relation,
                            visible=player_ui and player_ui.visible,
                        },{hostile=experiment_combat_binding.hostile,radius=3000,limit=256,require_visibility=experiment_player_entry or options.arena_binding~=nil})
                        api.face_target=function(boss,target)
                            -- 用途：外层AI停止后由玩家出招动作朝向所选目标；只旋转本轮临时Boss，不改位置。
                            local p,q=boss:K2_GetActorLocation(),target:K2_GetActorLocation()
                            local x,y=q.X-p.X,q.Y-p.Y
                            assert(x*x+y*y>1,'target overlaps controlled actor')
                            local rotation={Pitch=0,Yaw=math.deg(math.atan(y,x)),Roll=0}
                            boss.RootComponent:K2_SetWorldRotation(rotation,false,{},true)
                            boss:GetController():SetControlRotation(rotation)
                            local f=boss:GetActorForwardVector()
                            assert((f.X*x+f.Y*y)/math.sqrt(x*x+y*y)>0.98,'attack facing did not verify')
                        end
                    end
                    profile.skills.skill_01.requires_target=true
                end
                api.cancel_trace=function(row)
                    log('CANCEL_TRACE',row.reason..'|class='..row.ability_class..'|active='..tostring(row.active)
                        ..'|matched='..row.matched..'|invoked='..row.invoked..'|instance='..row.instance)
                end
                api.cancel_skill=function(spec,binding)
                    log("CANCEL_ACTIVE_BEFORE",spec.ActiveCount)
                    local cancelled=calls:cancel(spec,binding)
                    log("CANCEL_RESULT",tostring(cancelled).."|active="..tostring(spec.ActiveCount))
                    return cancelled
                end
                if experiment_camera_binding then
                    for key,value in pairs(experiment_camera_binding)do profile.camera[key]=value end
                    api.camera=require("camera_rig").new(calls,require("ue_camera").new(_G,profile.camera),profile.camera)
                end
                local bridge=require("control_bridge").new(api,profile)
                if native_combo_enabled then
                    api.combo_scheduler=require('combo_scheduler').new(calls,api.remote,api.cancel_skill,log)
                end
                if lifecycle then api.usable=function(object)return lifecycle:usable(object)end end
                if lifecycle then api.owned_temporary={boss=calls:reference(actor),ai=calls:reference(actor:GetController())}end
                local config=clone(require("config"));config.skills.slot1.verified=true
                if experiment_boss_candidate then
                    config.boss_id=profile.id;config.boss_display_name=profile.display_name
                    config.profile='boss_candidate';config.skills={slot1={id='skill_01',key='F1',name=profile.skills.skill_01.name,verified=true}}
                end
                if experiment_batch_skills then
                    for index,id in ipairs({'heavy_01','skill_02','dash'})do
                        if profile.skills[id]then config.skills[id]={id=id,key='F'..tostring(index+1),verified=true};sequence[#sequence+1]=id end
                    end
                end
                if experiment_target_cycle then config.controls.cycle_target='F7'end
                if profile.skills.skill_01.gameplay_verified and
                    (profile.input.primary_attack_key_verified==true or experiment_player_key_trial==true)then
                    -- 用途：左键明确复用已验证的技能01作为主攻击；不伪装成尚未修好的Attack_01原生连段。
                    bridge:spec({asc=calls:reference(asc)},profile.skills.skill_01)
                    config.skills.primary_attack={id='skill_01',key='LEFT_MOUSE_BUTTON',verified=true}
                end
                if profile.skills.skill_06 and profile.skills.skill_06.gameplay_verified then
                    -- 用途：F5只绑定已有伤害证据的技能06；装配时仍核对本次活体唯一授予和真实活动字段。
                    bridge:spec({asc=calls:reference(asc)},profile.skills.skill_06)
                    config.skills.skill_06={id='skill_06',key='F5',verified=true}
                end
                if experiment_extra_skills then
                    for id,key in pairs({heavy_02='F8',special_03='F9'})do
                        if profile.skills[id]then config.skills[id]={id=id,key=key,verified=true}end
                    end
                end
                if not experiment_extra_skills and not experiment_skill_lab and profile.skills.skill_08
                    and profile.skills.skill_08.gameplay_verified
                    and (profile.skills.skill_08.player_key_verified==true or experiment_player_key_trial==true) then
                    -- 用途：默认玩家版F8绑定已实测的子树叶招式；开发试验台保留F8，不重复注册。
                    bridge:spec({asc=calls:reference(asc)},profile.skills.skill_08)
                    config.skills.skill_08={id='skill_08',key='F8',verified=true}
                end
                if experiment_skill_lab then
                    local granted,blocked={},{}
                    for index=1,count do
                        local ability=items[index].Ability
                        if valid(ability)then
                            local path=ability:GetClass():GetFullName():match('^[^ ]+ (.+)$')
                            granted[#granted+1]=path
                            -- 用途：连招子树需要独立的AI调度适配，不能把它当作已可执行的一招。
                            local known_subtree=path==require('combo_scheduler').class
                            for _,contract in pairs(require('subtree_contracts'))do if path==contract.class then known_subtree=true end end
                            if ability:IsA('/Script/SGameAI.RunSubtreeAbility')and not(experiment_combo_scheduler_trial and known_subtree)then
                                blocked[path]=true;log('LAB_SCHEDULER_QUARANTINED',path)
                            end
                        end
                    end
                    local slots=require('skill_lab').configure(profile,config,granted,blocked,experiment_combo_scheduler_trial)
                    for _,slot in ipairs(slots)do log('LAB_CANDIDATE_AVAILABLE',config.skills[slot].id)end
                end
                if experiment_interactive then
                    if experiment_practice and not experiment_skill_lab and not experiment_extra_skills then
                        for id,key in pairs({skill_07='F9',teleport_left='Q',teleport_right='E'})do
                            local definition=profile.skills[id]
                            if definition and(definition.gameplay_verified or definition.movement_runtime_verified)
                                and(definition.player_key_verified or experiment_player_key_trial)then
                                bridge:spec({asc=calls:reference(asc)},definition)
                                config.skills[id]={id=id,key=key,verified=true}
                            end
                        end
                        if experiment_player_key_trial and native_combo_enabled then
                            bridge:spec({asc=calls:reference(asc)},native_combo)
                            config.skills.native_combo={id='attack_01',key='INS',verified=true,name=native_combo.name}
                        end
                        if experiment_keymap then require('keymap').apply(config,experiment_keymap)end
                    end
                    if experiment_player_entry then config=require('boss_catalog').configure(experiment_boss_id,profile,experiment_keymap)end
                    for slot,definition in pairs(config.skills)do
                        if definition.verified and not definition.lab_only then log('PLAYER_BINDING',slot..'|'..definition.id..'|'..definition.key)end
                    end
                    -- 用途：只在本轮限时实验装配真实键位与输入；不改变正式角色配置的验收标记。
                    profile.input.input_verified=true
                    local host=require("ue_host").new(bridge,profile.input)
                    local host_log=host.log
                    if player_ui then
                        player_ui.player_controller=function()return bridge:player_controller()end
                        local hud=require('player_hud').new(calls,player_ui,config)
                        local hud_failed=false
                        host.status=function(current,force)
                            if hud_failed then return end
                            local ok,shown,text=pcall(hud.update,hud,current,force)
                            if not ok then hud_failed=true;log('HUD_UNAVAILABLE',shown)
                            elseif shown and force then log('HUD_RENDER_REQUEST',text)end
                        end
                    end
                    local last_camera_ticket
                    local reassembly_requested=false
                    local function schedule_reassembly(reason)
                        if not experiment_player_entry or reassembly_requested then return end
                        reassembly_requested=true
                        local old_runtime=runtime
                        ExecuteInGameThreadWithDelay(250,function()
                            local restarted,problem=pcall(function()
                                guard();assert(old_runtime:stop(reason),'old runtime restoration failed')
                                assert(cleanup(),'old world cleanup not verified')
                                actor,ai,target_actor,target_ai,session,runtime,setup_protection,setup_ticket=nil,nil,nil,nil,nil,nil,nil,nil
                                extra_targets={};initialized_owned={};spawn_attempts=0;initialization_deadline=nil;rejected_layouts={}
                                gate_started,stationary_polls=0,0
                                log('WORLD_REASSEMBLY_WAIT',true);wait_for_player()
                            end)
                            if not restarted then log('ISSUE_WORLD_REASSEMBLY',problem)end
                        end)
                    end
                    local player_baseline,player_new_active={},{};local player_position,boss_position
                    local skill_samples={}
                    api.before_skill=function(receipt,id)
                        local target=receipt.combat and receipt.combat.selected_target and calls:resolve(receipt.combat.selected_target)
                        local p=actor:K2_GetActorLocation()
                        local sample={target=target,health=valid(target)and target.AttributeSetBase.Health.CurrentValue,
                            origin={X=p.X,Y=p.Y,Z=p.Z},others={}}
                        local owned={target_actor};for _,entry in ipairs(extra_targets)do owned[#owned+1]=entry.actor end
                        for _,other in ipairs(owned)do if valid(other)then sample.others[#sample.others+1]={actor=other,health=other.AttributeSetBase.Health.CurrentValue}end end
                        skill_samples[id]=sample
                        if valid(target)then local q=target:K2_GetActorLocation();log('SKILL_GEOMETRY',id..'|distance='..math.sqrt((p.X-q.X)^2+(p.Y-q.Y)^2+(p.Z-q.Z)^2))end
                    end
                    local function player_active()
                        local found={};local specs=player.AbilitySystemComponent.ActivatableAbilities.Items
                        local size=specs:GetArrayNum();assert(size<=512,'player ability bound')
                        for i=1,size do local s=specs[i];if valid(s.Ability)and s.ActiveCount>0 then found[s.Ability:GetClass():GetFullName()]=true end end
                        return found
                    end
                    host.log=function(message)
                        if message:find('world_retired success=true',1,true)then
                            host_log(message)
                            log('WORLD_RETIRED',session.retired_world_id)
                            schedule_reassembly('old world retired')
                            return
                        end
                        host_log(message)
                        local slot=message:match('^([%w_]+) success=true')
                        if slot=='lab_cast'and runtime and runtime.lab then slot=runtime.lab:selected()end
                        if slot and config.skills[slot]then
                            -- 用途：逐招记录真实ActiveCount、目标身份、掉血和位移；按键成功不等于造成伤害。
                            local id=config.skills[slot].id
                            local definition=bridge:definition(id)
                            local spec,active=bridge:spec(session.receipt,definition)
                            local observed_boss_reference=session.receipt.boss
                            local observed_asc_reference=session.receipt.asc
                            local combat=session.receipt.combat
                            local sample=assert(skill_samples[id],'pre-activation sample missing')
                            local target,before,origin=sample.target,sample.health,sample.origin
                            local peak,steps,ended_at=active,0,nil
                            local observation_scope=require('observation_scope').capture(session)
                            log('KEY_SKILL_BEGIN',id..'|target='..(target and target:GetFullName()or'None')..'|health='..tostring(before)..'|active='..active)
                            -- 用途：只读已核对的GAS实例字段，区分“可激活”和“当前允许中断”。
                            for _,field in ipairs({'NonReplicatedInstances','ReplicatedInstances'})do
                                local instances=spec[field];local size=instances:GetArrayNum();assert(size>=0 and size<=64,'ability instance observation bound')
                                for index=1,size do local instance=instances[index]
                                    if valid(instance)then log('SKILL_INSTANCE',id..'|active='..tostring(instance.bIsActive)..'|cancelable='..tostring(instance.bIsCancelable)..'|object='..instance:GetFullName())end
                                end
                            end
                            local function observe_skill()
                                -- 用途：退出/换会话后不再访问旧Spec或旧角色；取消是否成功由真实取消回读单独验收。
                                if not observation_scope:current()then log('SKILL_OBSERVATION_STOPPED',id..'|session ended');return end
                                local observed,problem=pcall(function()
                                    guard()
                                    if not calls:optional(observed_boss_reference)or not calls:optional(observed_asc_reference)then
                                        log('SKILL_OBSERVATION_STOPPED',id..'|owned Actor/ASC engine-unusable; no Spec read');return
                                    end
                                    steps=steps+1
                                    local current=spec.ActiveCount;peak=math.max(peak,current)
                                    -- 用途：结束后继续15次延迟采样；低帧率下可能超过名义1.5秒，不冒称全部命中。
                                    if current==0 and not ended_at then ended_at=steps end
                                    if current>0 then ended_at=nil end
                                    if (ended_at and steps-ended_at>=15)or steps>=200 then
                                        local after=valid(target)and target.AttributeSetBase.Health.CurrentValue or nil
                                        local p=actor:K2_GetActorLocation()
                                        log('KEY_SKILL_END',id..'|peak='..peak..'|active='..current..'|natural='..tostring(peak>0 and current==0 and session.state=='ACTIVE')
                                            ..'|health_before='..tostring(before)..'|health_after='..tostring(after)..'|distance='..math.sqrt((p.X-origin.X)^2+(p.Y-origin.Y)^2+(p.Z-origin.Z)^2)..'|sample_ticks='..steps..'|tail_ticks=15')
                                        for _,row in ipairs(sample.others)do if valid(row.actor)then log('SKILL_TARGET_HEALTH',id..'|target='..row.actor:GetFullName()..'|before='..row.health..'|after='..row.actor.AttributeSetBase.Health.CurrentValue)end end
                                        return
                                    end
                                    ExecuteInGameThreadWithDelay(100,observe_skill)
                                end)
                                if not observed then log('SKILL_OBSERVATION_REJECTED',problem)end
                            end
                            ExecuteInGameThreadWithDelay(100,observe_skill)
                        end
                        if message:find("enter success=true",1,true) and experiment_camera_binding then
                            -- 用途：切图前后按已捕获的完整World/主角身份比对，不能把重载成功截图当作重新接管证据。
                            log('CONTROL_WORLD_ID',session.receipt.world_id)
                            for _,key in ipairs({'player_controller','player','boss'})do
                                local reference=session.receipt[key]
                                log('CONTROL_PARTICIPANT',key..'|'..reference.name..'|address='..reference.address..'|class='..reference.class)
                            end
                            player_baseline=player_active();player_new_active={}
                            local p,b=player:K2_GetActorLocation(),actor:K2_GetActorLocation()
                            player_position={X=p.X,Y=p.Y,Z=p.Z};boss_position={X=b.X,Y=b.Y,Z=b.Z}
                            if experiment_combat_binding then
                                api.combat:request_target(session.receipt.combat,target_actor,'None')
                                log('INTERACTIVE_TARGET',target_actor:GetFullName())
                            end
                            if session.receipt.input_barrier then log('INPUT_BARRIER_CONSTRUCTED',api.input_barrier:verify(session.receipt.input_barrier))end
                            last_camera_ticket=session.receipt.camera_rig
                            local observation_scope=require('observation_scope').capture(session)
                            local function observe_camera()
                                -- 用途：正常F10会释放receipt，旧延迟回调应结束，而非产生“camera receipt missing”故障。
                                if not observation_scope:current()then log('CAMERA_OBSERVATION_STOPPED','session ended');return end
                                local observed,problem=pcall(function()
                                    guard()
                                    local receipt=assert(session.receipt,"camera receipt missing")
                                    local ticket=assert(receipt.camera_rig,"independent camera missing")
                                    local component=calls:resolve(ticket.component)
                                    local boom=calls:resolve(ticket.boom)
                                    local boss_pos=actor:K2_GetActorLocation()
                                    local camera_pos=component:K2_GetComponentLocation()
                                    local rendered=pc.PlayerCameraManager:GetCameraLocation()
                                    local function vector(v)return string.format("%.3f,%.3f,%.3f",v.X,v.Y,v.Z)end
                                    log("CAMERA_BOSS_POSITION",vector(boss_pos))
                                    log("CAMERA_COMPONENT_POSITION",vector(camera_pos))
                                    log("CAMERA_RENDERED_POSITION",vector(rendered))
                                    log("CAMERA_DISTANCE",math.sqrt((camera_pos.X-boss_pos.X)^2+(camera_pos.Y-boss_pos.Y)^2+(camera_pos.Z-boss_pos.Z)^2))
                                    log("CAMERA_COLLISION_FIX",boom:IsCollisionFixApplied())
                                    local control=pc:GetControlRotation()
                                    local arm=boom:K2_GetComponentRotation()
                                    log("CAMERA_CONTROL_YAW",control.Yaw)
                                    log("CAMERA_ARM_YAW",arm.Yaw)
                                end)
                                if not observed then log("ISSUE_CAMERA_OBSERVATION",problem)end
                            end
                            for _,delay in ipairs({500,4000,7500})do ExecuteInGameThreadWithDelay(delay,observe_camera)end
                        elseif message:find("exit success=true",1,true) and last_camera_ticket then
                            local function distance(p,q)return math.sqrt((p.X-q.X)^2+(p.Y-q.Y)^2+(p.Z-q.Z)^2)end
                            log('ORIGINAL_PLAYER_POSITION_DELTA',distance(player:K2_GetActorLocation(),player_position))
                            if lifecycle:usable(actor)then
                                log('CONTROLLED_BOSS_POSITION_DELTA',distance(actor:K2_GetActorLocation(),boss_position))
                            else log('CONTROLLED_BOSS_DISPOSED',true)end
                            local unseen=0;for _ in pairs(player_new_active)do unseen=unseen+1 end
                            log('ORIGINAL_PLAYER_NEW_ACTIVE_COUNT',unseen)
                            local ticket=last_camera_ticket
                            -- 用途：恢复后玩家可正常走动；重复F10不得再次与这次已结束控制的起点比较。
                            last_camera_ticket=nil
                            local function verify_camera_cleanup()
                                local checked,problem=pcall(function()
                                    guard()
                                    local function lookup(reference)
                                        local path=reference.name:match("^[^ ]+ (.+)$")
                                        local object=StaticFindObject(path)
                                        if object and object:IsValid()and object:GetAddress()==reference.address then return object end
                                    end
                                    local camera=lookup(ticket.camera)
                                    local boom=ticket.boom and lookup(ticket.boom)
                                    log("CAMERA_ACTOR_UOBJECT_RESOLVABLE",camera~=nil)
                                    log("CAMERA_BOOM_UOBJECT_RESOLVABLE",boom~=nil)
                                    -- 用途：区分已销毁但尚未GC的UObject与仍在运行的镜头组件。
                                    local camera_usable=lifecycle:usable(camera)
                                    local boom_usable=lifecycle:usable(boom)
                                    log('CAMERA_ACTOR_ENGINE_USABLE',camera_usable)
                                    log('CAMERA_BOOM_ENGINE_USABLE',boom_usable)
                                    log('CAMERA_CLEANUP_ENGINE_VERIFIED',ticket.destroyed==true and not camera_usable and not boom_usable)
                                    log("CAMERA_CLEANUP_RECORDED",ticket.destroyed==true)
                                end)
                                if not checked then log("ISSUE_CAMERA_CLEANUP",problem)end
                            end
                            if message:find('reason=map travel',1,true)then verify_camera_cleanup()
                            else ExecuteInGameThreadWithDelay(500,verify_camera_cleanup)end
                        end
                    end
                    local read_input=host.read_input
                    local observed_forward=false
                    host.read_input=function(receipt)
                        local input=read_input(receipt)
                        if experiment_barrier_binding then
                            for name in pairs(player_active())do
                                if not player_baseline[name]and not player_new_active[name]then player_new_active[name]=true;log('ORIGINAL_PLAYER_NEW_ACTIVE',name)end
                            end
                        end
                        if input.forward and not observed_forward then log("W_KEY_OBSERVED",true);observed_forward=true end
                        return input
                    end
                    if experiment_player_entry then
                        local captured={world=calls:world(pc),player_controller=calls:reference(pc),
                            player=calls:reference(player),owned_world_objects={}}
                        local owned={actor,target_actor};for _,entry in ipairs(extra_targets)do owned[#owned+1]=entry.actor end
                        for _,pawn in ipairs(owned)do
                            local controller=pawn:GetController()
                            for _,object in ipairs({pawn,pawn.AbilitySystemComponent,controller,controller.BrainComponent,controller.SGameAIComponent})do
                                captured.owned_world_objects[#captured.owned_world_objects+1]=calls:reference(object)
                            end
                        end
                        local watch=require('idle_world_watch').new(calls,captured,os.time)
                        log('IDLE_WORLD_WATCH_READY',captured.world.name..'|address='..captured.world.address..'|owned='..#captured.owned_world_objects)
                        host.inspect_idle_world=function()
                            guard()
                            local status=watch:poll(session.state)
                            if status=='retired'and not reassembly_requested then
                                log('IDLE_WORLD_OBJECTS_RETIRED',captured.world.name..'|address='..captured.world.address)
                                schedule_reassembly('restored scene and owned objects retired')
                            end
                            return status=='same'
                        end
                    end
                    runtime=require("runtime").new(bridge,config,host)
                    session=runtime.session
                    if experiment_player_entry then
                        workbench=workbench or require('boss_workbench').new({
                            entries=require('workbench_catalog').list,selected=function()return experiment_boss_id end})
                        local workbench_camera=require('ue_camera').new(_G,profile.camera)
                        local menu_input=require('workbench_input').new(calls,api.input_barrier,{
                            create=function()return workbench_camera.spawn_camera(pc,actor,profile.camera)end,
                            finish=function(camera)
                                local transform=maths:MakeTransform(actor:K2_GetActorLocation(),{Pitch=0,Yaw=0,Roll=0},{X=1,Y=1,Z=1})
                                local finished=statics:FinishSpawningActor(camera,transform,profile.camera.spawn_scale)
                                return valid(finished)and calls:same(camera,finished)
                            end,
                            destroy=workbench_camera.destroy_camera,
                        })
                        workbench:set_adapter({
                            restore=function(reason)
                                guard();local restored,why=session:restore(reason)
                                if restored and session.state=='OFF'and not session.receipt then return true end
                                return false,why
                            end,
                            lock=function()
                                guard();assert(menu_input:lock(pc))
                                log('WORKBENCH_INPUT_LOCKED',menu_input.ticket.owner.name);return true
                            end,
                            unlock=function()
                                local had_owner=menu_input.ticket~=nil;assert(menu_input:unlock())
                                if had_owner then log('WORKBENCH_INPUT_RESTORED',true)end
                                return true
                            end,
                            select=function(id)
                                guard();assert(session.state=='OFF'and not session.receipt,'restore before Boss switching')
                                local selected=require('boss_catalog').profile(id)
                                require('boss_catalog').configure(id,selected,experiment_keymap)
                                assert(selected.exe_sha256==guard().exe_sha256,'selected Boss build differs')
                                experiment_boss_id=id;log('WORKBENCH_BOSS_SELECTED',id)
                                schedule_reassembly('player selected a different Boss');return true
                            end,
                        })
                        host.workbench=workbench
                        local status=host.status;local last_at,last_revision=-math.huge,-1
                        host.status=function(current,force)
                            if workbench:is_open()then
                                local now=os.time()
                                if force or workbench.revision~=last_revision or now-last_at>=1 then
                                    guard();player_ui.render(pc,workbench:text())
                                    last_at=now;last_revision=workbench.revision
                                end
                            elseif status then status(current,force)end
                        end
                    end
                    runtime:start();deferred=true
                    if experiment_player_entry then log('WORKBENCH_READY','v2|toggle=INS|up=UP_ARROW|down=DOWN_ARROW|confirm=RETURN|close=ESCAPE')end
                    if experiment_player_entry then log('PLAYER_ENTRY_READY',experiment_boss_id)end
                    if experiment_player_entry and not map_travel_guard_installed then
                        assert(type(RegisterLoadMapPreHook)=='function','current loader LoadMap pre-hook unavailable')
                        local travel=require('map_travel_guard').new({runtime=function()return runtime end,attest=guard,log=log,
                            same_world=function(world,reference)
                                return lifecycle:usable(world)and calls:same(world,calls:resolve(reference))
                            end})
                        RegisterLoadMapPreHook(function(_,world)
                            local ok,why=pcall(function()travel:before(world:Get())end)
                            if not ok then log('ISSUE_MAP_TRAVEL_GUARD',why)end
                            -- nil保留引擎原本的加载结果，不伪造成功，不替换地图参数。
                        end)
                        map_travel_guard_installed=true;log('MAP_TRAVEL_GUARD_READY',true)
                    end
                    if options.scene_transition_trial then
                        host.bind_key('F12',function()host.on_game_thread(function()
                            local ok,why=pcall(function()
                                local grant=guard();assert(grant.expires_at-os.time()>180,'transition cleanup margin required')
                                assert(not transition_trial_used and session.state=='ACTIVE'and session.receipt and not session.current_skill and not session.pending_target,
                                    'single idle active-receipt transition required')
                                local world=calls:world(pc)
                                assert(world.name==session.receipt.world.name and world.address==session.receipt.world.address,'captured current World required')
                                local package,asset=world.name:match('^World (/.+)%.([^%.]+)$')
                                assert(package and package:match('([^/]+)$')==asset,'unambiguous current map package required')
                                transition_trial_used=true;log('ACTIVE_WORLD_TRIAL_BEGIN',world.name..'|address='..world.address)
                                statics:OpenLevel(pc,FName(package),true,'')
                                log('ACTIVE_WORLD_TRIAL_REQUESTED',true)
                            end)
                            if not ok then log('TRANSITION_TRIAL_REJECTED',why)end
                        end)end)
                        log('TRANSITION_TRIAL_KEY','F12; reload exact captured current map once; isolated developer validation')
                    end
                    -- 用途：记录本轮自建对象的完整身份，死亡后也能清理遗留Controller，不依赖死去Pawn反查。
                    local retiring={actor,target_actor}
                    for _,entry in ipairs(extra_targets)do retiring[#retiring+1]=entry.actor end
                    for _,pawn in ipairs(retiring)do
                        for _,entry in ipairs({{kind='actor',object=pawn},{kind='controller',object=pawn:GetController()}})do
                            local object=entry.object
                            assert(valid(object),'owned retirement reference unavailable')
                            log('OWNED_RETIRE_REFERENCE',entry.kind..'|'..object:GetFullName()..'|address='..object:GetAddress()
                                ..'|class='..object:GetClass():GetFullName())
                        end
                    end
                    if options.incoming_combat_trial then
                        local sources={calls:reference(target_actor)}
                        for _,entry in ipairs(extra_targets)do sources[#sources+1]=calls:reference(entry.actor)end
                        local boss_reference=calls:reference(actor)
                        local original_player_reference=calls:reference(player)
                        local last_incoming_snapshot
                        local function observe_incoming(label)
                            local function activities(pawn)
                                local result={};local items=pawn.AbilitySystemComponent.ActivatableAbilities.Items
                                local count=items:GetArrayNum();assert(count<=512,'incoming snapshot ability bound')
                                for i=1,count do
                                    local spec=items[i]
                                    if spec.ActiveCount>0 and valid(spec.Ability)then
                                        result[#result+1]=spec.Ability:GetClass():GetFullName()..'='..spec.ActiveCount
                                    end
                                end
                                return table.concat(result,',')
                            end
                            local saved=calls:resolve(original_player_reference)
                            local p,v=saved:K2_GetActorLocation(),saved:GetVelocity()
                            local rows={string.format('player_health=%.6f|position=%.3f,%.3f,%.3f|velocity=%.3f,%.3f,%.3f',
                                saved.AttributeSetBase.Health.CurrentValue,p.X,p.Y,p.Z,v.X,v.Y,v.Z)..'|player_active='..activities(saved)}
                            for _,ref in ipairs(sources)do
                                local source=calls:resolve(ref);local controller=source:GetController()
                                rows[#rows+1]=source:GetFullName()..'|health='..source.AttributeSetBase.Health.CurrentValue
                                    ..'|ai_started='..tostring(controller.SGameAIComponent.bAIStarted)
                                    ..'|ai_tick='..tostring(controller:IsActorTickEnabled())
                                    ..'|brain_running='..tostring(controller.BrainComponent:IsRunning())
                                    ..'|brain_tick='..tostring(controller.BrainComponent:IsComponentTickEnabled())
                                    ..'|active='..activities(source)
                            end
                            local snapshot=table.concat(rows,';')
                            if snapshot~=last_incoming_snapshot or label~='after_restore'then
                                log('INCOMING_COMBAT_SNAPSHOT',label..'|'..snapshot);last_incoming_snapshot=snapshot
                            end
                        end
                        local function incoming_spec(reference)
                            local pawn=calls:resolve(reference)
                            local spec=bridge:spec({asc=calls:reference(pawn.AbilitySystemComponent)},profile.skills.skill_07)
                            return spec
                        end
                        local trial=require('incoming_combat_trial').new({
                            session=session,sources=sources,attest=guard,now=os.time,log=log,observe=observe_incoming,
                            name=function(ref)return ref.name end,
                            health=function()return api.read_health(calls:resolve(boss_reference))end,
                            spec=incoming_spec,
                            cancel=function(spec)return calls:cancel(spec,profile.skills.skill_07)end,
                            activate=function(spec,ref)
                                return calls:activate(calls:resolve(ref).AbilitySystemComponent,spec.Ability:GetClass())
                            end,
                            validate=function(ref)
                                local source,boss=calls:resolve(ref),calls:resolve(boss_reference)
                                assert(not calls:same(source,boss)and not calls:same(source,player),'owned incoming source required')
                                local world,other=calls:world(source),calls:world(boss)
                                assert(world.name==other.name and world.address==other.address,'same-world incoming combat required')
                                assert(api.combat.native.relation(source,boss)==experiment_combat_binding.hostile,'incoming source must be hostile')
                            end,
                            target=function(ref)
                                local source,boss=calls:resolve(ref),calls:resolve(boss_reference)
                                api.face_target(source,boss)
                                local controller=source:GetController()
                                controller:K2_SetFocus(boss)
                                assert(api.combat.native.set_target(source:GetTargetingComponent(),boss,'None',boss.RootComponent)==true,'incoming target lock rejected')
                                assert(calls:same(api.combat.native.target_actor(source),boss),'incoming ability target mismatch')
                            end,
                            clear=function(ref)
                                local source=calls:resolve(ref)
                                api.combat.native.clear_target(source:GetTargetingComponent());source:GetController():K2_ClearFocus()
                            end,
                            schedule=function(fn)ExecuteInGameThreadWithDelay(250,fn)end,
                        })
                        local restore=session.restore
                        session.restore=function(current,reason)
                            local ok,why=pcall(trial.stop,trial)
                            if not ok then log('ISSUE_INCOMING_COMBAT_STOP',why);return false,why end
                            local restored,problem=restore(current,reason)
                            if restored then trial:watch_restored()end
                            return restored,problem
                        end
                        host.bind_key('F12',function()host.on_game_thread(function()
                            local ok,why=pcall(trial.start,trial)
                            if not ok then log('INCOMING_COMBAT_START_REJECTED',why)end
                        end)end)
                        log('DEATH_TRIAL_KEY','F12; two exact owned sources use native skill07; no Kill or health writes')
                    elseif experiment_death_trial then
                        local damage_used=false
                        local owned_disposal_reference=calls:reference(actor)
                        local death_reasons=StaticFindObject('/Script/CharacterBasics.EPBZDieReason')
                        assert(valid(death_reasons),'native death reason enum missing')
                        death_reasons:ForEachName(function(name,value)
                            log('OWNED_DEATH_REASON_ENUM',name:ToString()..'|'..value)
                        end)
                        -- 用途：仅开发开关开放，一次性伤害/原生死亡请求限定于本轮自建Boss；不写生命值。
                        host.bind_key('F12',function()host.on_game_thread(function()
                            local tested,problem=pcall(function()
                                guard();assert(not damage_used,'owned damage trial already used')
                                local active_id,active_count=require('death_trial_guard').activity(session,bridge,experiment_active_skill_death_trial==true)
                                local boss=calls:resolve(session.receipt.boss)
                                assert(valid(actor)and calls:same(boss,actor)and not calls:same(boss,player),'only exact owned boss may receive trial damage')
                                local before=api.read_health(boss);assert(before>0 and before<1000000,'bounded living boss health required')
                                local damage_class=StaticFindObject('/Script/Engine.DamageType');assert(valid(damage_class),'native damage class missing')
                                damage_used=true
                                log('OWNED_DEATH_TRIAL_BEGIN',boss:GetFullName()..'|health='..before)
                                if active_id then log('OWNED_DEATH_TRIAL_ACTIVE_SKILL',active_id..'|active='..active_count)end
                                if options.active_skill_disposal_trial then
                                    log('OWNED_DEATH_TRIAL_METHOD','K2_DestroyActor; exact active skill08 instance; no post-disposal Spec reads')
                                    require('owned_disposal_trial').run(session,bridge,calls,owned_disposal_reference,lifecycle,log)
                                    local restored,why=session:restore('owned boss disposed')
                                    runtime:report('auto_exit',restored,'owned boss disposed')
                                    assert(restored,'synchronous owned disposal restoration failed: '..tostring(why))
                                elseif experiment_native_death_reason then
                                    log('OWNED_DEATH_TRIAL_METHOD','native Kill; exact owned actor; verified Damaged enum')
                                    boss:Kill(experiment_native_death_reason)
                                    log('OWNED_DEATH_TRIAL_KILL_REQUESTED',true)
                                else
                                    local applied=statics:ApplyDamage(boss,before+100,ai,target_actor,damage_class)
                                    log('OWNED_DEATH_TRIAL_APPLIED',applied)
                                end
                                if not options.active_skill_disposal_trial and valid(boss)then log('OWNED_DEATH_TRIAL_HEALTH_AFTER',api.read_health(boss))end
                            end)
                            if not tested then log('DEATH_TRIAL_REJECTED',problem)end
                        end)end)
                        log('DEATH_TRIAL_KEY','F12; exact owned actor only; single '..(experiment_native_death_reason and'native Kill'or'engine damage')..' request')
                    end
                    local duration=experiment_practice and math.min(600,guard().expires_at-os.time()-20) or 60
                    local generation=assembly_generation
                    assert(duration>=20,'insufficient practice cleanup margin')
                    log("INTERACTIVE_READY","F6 enter, WASD move, F1-F5 skills"..(config.skills.primary_attack and', LMB skill01'or'')..(experiment_target_cycle and', F7 target'or'')..(config.skills.skill_08 and', F8 skill08'or'')..(experiment_extra_skills and', F8/F9 experimental skills'or'')..(experiment_skill_lab and', F9 next candidate, F8 cast candidate'or'')..", F10 restore; cleanup in "..duration.." seconds")
                    ExecuteInGameThreadWithDelay(duration*1000,function()
                        if generation~=assembly_generation then return end
                        local clean,error=pcall(cleanup)
                        if not clean then log("ISSUE_CLEANUP",error)end
                        log("INTERACTIVE_END","bounded input probe complete")
                    end)
                    return
                end
                session=require("session").new(bridge,config)
                local controlled,reason=session:enter()
                log("TAKEOVER",tostring(controlled).."|"..tostring(reason))
                if controlled then
                    if experiment_combat_binding then
                        local ticket=session.receipt.combat
                        log('FACTION_SWITCH',ticket.original..'->'..ticket.desired)
                        log('FACTION_FRIENDLY_VERIFIED',api.combat:verify(ticket))
                        log('TARGET_REQUEST',api.combat:request_target(ticket,target_actor,'None'))
                    end
                    log("PLAYER_PAWN_AFTER",pc:K2_GetPawn():GetFullName())
                    assert(EngineTickAvailable,"frame scheduler unavailable")
                    local start=actor:K2_GetActorLocation()
                    local sx,sy,sz=start.X,start.Y,start.Z
                    local frames,settle_frames=0,0
                    deferred=true
                    frame_handle=LoopInGameThreadAfterFrames(1,function()
                        local moved,move_error=pcall(function()
                            guard()
                            if experiment_combat_binding and settle_frames<15 then
                                settle_frames=settle_frames+1
                                if settle_frames==15 then
                                    local verified=api.combat:verify_target(session.receipt.combat)
                                    log('TARGET_AFTER_SETTLE_VERIFIED',verified)
                                    assert(verified,'target still differs after 15 game frames; skill remains blocked')
                                end
                                return
                            end
                            frames=frames+1
                            if frames<=12 then
                                local length=math.sqrt(forward.X*forward.X+forward.Y*forward.Y)
                                assert(length>0,"invalid forward vector")
                                bridge:move(session.receipt,forward.X/length,forward.Y/length,1)
                            else
                                CancelDelayedAction(frame_handle);frame_handle=nil
                                local position=actor:K2_GetActorLocation()
                                local delta=math.sqrt((position.X-sx)^2+(position.Y-sy)^2)
                                log("MOVEMENT_DELTA_XY",delta)
                                log("MOVEMENT_DELTA_Z",position.Z-sz)
                                local sequence_index=1
                                local function begin_skill()
                                    local slot=sequence[sequence_index]
                                    log('BATCH_SKILL',config.skills[slot].id)
                                    if target_actor then log('HEALTH_BEFORE',target_actor.AttributeSetBase.Health.CurrentValue)end
                                    local started,reason=session:skill(slot)
                                    log('SKILL_START',tostring(started)..'|'..tostring(reason));return started
                                end
                                local started=begin_skill()
                                local steps=0;local next_skill_at
                                frame_handle=LoopInGameThreadWithDelay(100,function()
                                    local polled,poll_error=pcall(function()
                                        guard()
                                        if next_skill_at then
                                            if os.time()>=next_skill_at then next_skill_at=nil;steps=0;started=begin_skill()end
                                            return
                                        end
                                        steps=steps+1
                                        if session.current_skill then session:poll()end
                                        if not session.current_skill or steps>=80 then
                                            log("SKILL_FINISHED_NATURALLY",session.current_skill==nil and started)
                                            if valid(target_actor)then log('HEALTH_AFTER',target_actor.AttributeSetBase.Health.CurrentValue)end
                                            if session.current_skill==nil and sequence_index<#sequence and guard().expires_at-os.time()>15 then
                                                -- 用途：能力计数归零不代表共享冷却/收招标签立刻结束，下一招留独立窗口。
                                                sequence_index=sequence_index+1;next_skill_at=os.time()+4;return
                                            end
                                            cleanup()
                                            log("PLAYER_PAWN_RESTORED",pc:K2_GetPawn():GetFullName())
                                            log("END","movement and selected-skill bounded probe; inspect each activation and health pair")
                                        end
                                    end)
                                    if not polled then log("ISSUE_POLL",poll_error);pcall(cleanup)end
                                end)
                            end
                        end)
                        if not moved then
                            log("ISSUE_MOVE",move_error)
                            local cleaned,problem=pcall(cleanup)
                            if cleaned then log('END','target or movement rejected and restoration attempted')else log('ISSUE_CLEANUP',problem)end
                        end
                    end)
                end
            end)
            if not ready then log("ISSUE_READY",error)end
            if not deferred or not ready then
                local clean,cleanup_error=pcall(cleanup)
                if not clean then log("ISSUE_CLEANUP",cleanup_error)end
                log("END","bounded probe; continuous play and skills not verified")
            end
        end
        when_ready(function()
            if experiment_combat_binding then
                log('PRIMARY_READY_BEFORE_TARGET',true)
                spawn_training_target()
                when_ready(function()
                    if experiment_target_cycle then spawn_training_target(2);when_ready(install_controls)else install_controls()end
                end)
            else install_controls()end
        end)
    end)
    if not ok then
        if construction_rejected and not session and not runtime then recover_initialization(why)
        else log('ISSUE_START',why);pcall(cleanup)end
    end
end)
end

-- 用途：启用训练时先等待真实主角静止；这一阶段不生成角色、不改移动/碰撞/血量。
-- 用户尚在加载、走动或落地时可在同一游戏进程重试，不需要因此退出游戏。
wait_for_player=function()
    local no_gameplay_player=false
    local grant
    local ready,why=pcall(function()
        grant=guard()
        local player,count=nil,0
        for _,pc in ipairs(FindAllOf('PBZPlayerController')or{})do
            if valid(pc)and valid(pc.Pawn)and pc:GetFullName():find(':PersistentLevel.',1,true)then player=pc.Pawn;count=count+1 end
        end
        no_gameplay_player=count==0
        assert(count==1,'unique local gameplay player required')
        local identity=player:GetFullName()..'|'..tostring(player:GetAddress())
        local health=player.AttributeSetBase.Health.CurrentValue
        assert(type(health)=='number'and health>0,'living original player required')
        if readiness_player~=identity or readiness_health~=health then
            log('PLAYER_READY_HEALTH',identity..'|health='..health)
            readiness_player,readiness_health,health_stable_polls=identity,health,0
        else health_stable_polls=health_stable_polls+1 end
        local velocity=player:GetVelocity()
        local speed2=velocity.X^2+velocity.Y^2+velocity.Z^2
        if gate_started%20==0 then log('PLAYER_READY_VELOCITY',string.format('%.6f,%.6f,%.6f|speed2=%.6f',velocity.X,velocity.Y,velocity.Z,speed2))end
        assert(speed2<4,'release movement keys and wait for the player to stand still')
        assert(health_stable_polls>=50,'wait for gameplay health initialization to settle')
    end)
    gate_started=gate_started+1
    stationary_polls=ready and stationary_polls+1 or 0
    if stationary_polls>=12 then log('PLAYER_READY_STABLE',true);begin_experiment();return end
    if gate_started>=200 then
        if experiment_player_entry and no_gameplay_player and grant and grant.expires_at-os.time()>100 then
            -- 标题与正常加载阶段没有主角；继续只读等待，但不延长原租约或掩盖移动/重复控制器问题。
            gate_started=0
            log('WORLD_REASSEMBLY_AWAITING_GAMEPLAY',true)
            ExecuteInGameThreadWithDelay(500,wait_for_player)
            return
        end
        log('PREREQUISITE_NOT_READY',why or 'stationary interval not reached')
        log('PREREQUISITE_RETRY_SAFE',true)
        log('END','precondition not met before mutations; retry in the same game')
        return
    end
    ExecuteInGameThreadWithDelay(100,wait_for_player)
end
ExecuteWithDelay(1500,function()ExecuteInGameThread(wait_for_player)end)

end
return Arena
