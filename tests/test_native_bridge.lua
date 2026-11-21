-- 用途：用假UObject执行真实桥接代码，检查调用顺序/部分失败恢复；不冒充PBZ实机验收。
local root = assert(arg[1], "project directory required")
package.path = root .. "/mod/PBZBossControl/Scripts/?.lua;" .. package.path
local Bridge, Session = require("control_bridge"), require("session")
local total = 0
local function fixture()
    local registry, classes, next_address = {}, {}, 1000
    local f = { mutations = {}, clock = 100, activation_allowed = true, cancellation_allowed = true }
    local function cls(path)
        if not classes[path] then
            next_address = next_address + 8
            local address = next_address
            classes[path] = { IsValid = function() return true end,
                GetFullName = function() return "Class " .. path end, GetAddress = function() return address end }
        end
        return classes[path]
    end
    local function object(path, class)
        next_address = next_address + 8
        local address = next_address
        local item = { alive = true, path = path }
        function item:IsValid() return self.alive end
        function item:GetFullName() return "Object " .. self.path end
        function item:GetAddress() return address end
        function item:GetClass() return cls(class or "/Fixture.Object") end
        function item:GetWorld() return f.world end
        registry[path] = item
        return item
    end
    f.object = object
    f.world = object("/Fixture/Map.Map", "/Script/Engine.World")
    f.pc = object("/Fixture/Map.Map:PersistentLevel.PlayerController", "/Script/ProjectPBZ.PBZPlayerController")
    f.player = object("/Fixture/Map.Map:PersistentLevel.Hun", "/Fixture.Player")
    f.boss = object("/Fixture/Map.Map:PersistentLevel.Ahua", "/Fixture/Ahua.BP_Ahua_C")
    f.ai = object("/Fixture/Map.Map:PersistentLevel.AhuaAI", "/Fixture.AI")
    f.brain = object("/Fixture/Map.Map:PersistentLevel.AhuaAI.Brain", "/Script/AIModule.BrainComponent")
    f.brain.running = true
    function f.brain:IsRunning() return self.running end
    function f.brain:StopLogic(reason)
        assert(type(reason) == "string"); f.mutations[#f.mutations+1] = "stop"; self.running = false
    end
    function f.brain:StartLogic() f.mutations[#f.mutations+1] = "start"; self.running = true end
    f.ai.BrainComponent = f.brain
    for _, pawn in ipairs({f.player,f.boss}) do
        function pawn:GetController() return self.Controller end
        function pawn:AddMovementInput(direction, scale, force)
            assert(force == false); f.last_move = { direction = direction, scale = scale }
            f.mutations[#f.mutations+1] = "move"
        end
        function pawn:AddControllerYawInput(value) f.yaw = value end
        function pawn:AddControllerPitchInput(value) f.pitch = value end
    end
    for _, controller in ipairs({f.pc,f.ai}) do
        function controller:K2_GetPawn() return self.Pawn end
        function controller:Possess(pawn)
            f.mutations[#f.mutations+1] = "possess:" .. pawn.path
            if self.Pawn then self.Pawn.Controller = nil end
            if pawn.Controller then pawn.Controller.Pawn = nil end
            self.Pawn, pawn.Controller = pawn, self
            if self == f.pc and pawn == f.boss and f.fail_takeover then
                f.fail_takeover = false; error("injected partial Possess failure")
            end
        end
        function controller:GetViewTarget() return self.camera end
        function controller:SetViewTargetWithBlend(target, time, mode, exp, lock)
            assert(time == 0 and mode == 0 and exp == 0 and lock == false)
            if target == f.boss and f.fail_camera then error("injected camera failure") end
            self.camera = target; f.mutations[#f.mutations+1] = "view:" .. target.path
        end
    end
    f.pc.Pawn, f.player.Controller, f.pc.camera = f.player, f.pc, f.player
    f.ai.Pawn, f.boss.Controller = f.boss, f.ai
    f.boss.CharacterMovement = object("/Fixture/Map.Map:PersistentLevel.Ahua.Movement")
    f.ability = object("/Fixture/Attack.Default__Attack", "/Fixture/Attack.GA_Attack_C")
    f.spec = { Ability = f.ability, ActiveCount = 0 }
    f.asc = object("/Fixture/Map.Map:PersistentLevel.Ahua.ASC")
    f.asc.ActivatableAbilities = { Items = setmetatable({ GetArrayNum = function() return 1 end }, {
        __index = function(_, index) assert(index == 1,"out-of-bounds spec read"); return f.spec end }) }
    f.boss.AbilitySystemComponent = f.asc
    function f.asc:TryActivateAbilityByClass(ability_class, remote)
        assert(remote == false and ability_class == f.ability:GetClass())
        f.activation_calls = (f.activation_calls or 0) + 1
        if not f.activation_allowed then return false end
        f.spec.ActiveCount = 1; return true
    end
    f.lease = { isolated = true, offline = true, session_id = "fixture-session", expires_at = 1000, exe_sha256 = "fixture-build" }
    f.profile = { identity_verified = true, class_path = "/Fixture/Ahua.BP_Ahua_C", exe_sha256 = "fixture-build",
        skills = { attack = { binding_verified = true, class_path = "/Fixture/Attack.GA_Attack_C", active_count_field = "ActiveCount" } } }
    f.api = { now = function() return f.clock end, attest = function() return f.lease end,
        find_exact = function(path) return registry[path] end,
        find_all = function(kind)
            if kind == "PBZPlayerController" then return {f.pc} end
            if kind == "PBZCharacter_NPC" then return f.extra_boss and {f.boss,f.extra_boss} or {f.boss} end
            error("unexpected class lookup")
        end,
        cancel_skill = function(spec)
            if not f.cancellation_allowed then return false end
            spec.ActiveCount = 0; return true
        end }
    f.bridge = Bridge.new(f.api,f.profile)
    f.session = Session.new(f.bridge, { expected_exe_sha256 = "fixture-build", skills = { slot1 = { id = "attack", verified = true } } })
    return f
end
local function test(name, fn)
    local ok, why = pcall(fn)
    assert(ok, name .. ": " .. tostring(why)); total = total + 1; print("PASS " .. name)
end
test('zero and nonfinite health are rejected before mutation',function()
    for _,health in ipairs({0,-1,math.huge,0/0})do
        local f=fixture();f.api.read_health=function()return health end
        assert(not f.session:enter());assert(#f.mutations==0)
    end
end)
test('real bridge health read restores without rewriting the health value',function()
    local f=fixture();local hp=100
    f.api.read_health=function()return hp end
    assert(f.session:enter());hp=0
    assert(not f.session:poll());assert(f.session.state=='OFF'and hp==0 and f.pc.Pawn==f.player)
end)
test("native possession, camera, input, skill and restoration chain", function()
    local f = fixture(); assert(f.session:enter())
    assert(f.pc.Pawn == f.boss and f.boss.Controller == f.pc and f.ai.Pawn == nil)
    assert(f.pc.camera == f.boss and not f.brain.running)
    assert(f.bridge:move(f.session.receipt,1,0,1)); assert(f.last_move.direction.X == 1)
    assert(f.bridge:look(f.session.receipt,2,-1)); assert(f.yaw == 2 and f.pitch == -1)
    assert(f.session:skill("slot1")); assert(not f.session:skill("slot1")); assert(f.session:poll())
    f.spec.ActiveCount = 0; assert(f.session:poll()); assert(f.session.current_skill == nil)
    assert(f.session:restore("exit"))
    assert(f.pc.Pawn == f.player and f.pc.camera == f.player and f.ai.Pawn == f.boss and f.brain.running)
end)
test("unverified boss class cannot construct the bridge", function()
    local f = fixture(); f.profile.identity_verified = false
    assert(not pcall(Bridge.new,f.api,f.profile)); assert(#f.mutations == 0)
end)
test("absent confirmed boss does not mutate another NPC", function()
    local f = fixture(); f.profile.class_path = "/Fixture/Missing.Missing_C"
    assert(not f.session:enter()); assert(#f.mutations == 0)
end)
test("ambiguous boss selection performs no mutation", function()
    local f = fixture(); f.extra_boss = f.object("/Fixture/Map.Map:PersistentLevel.Ahua2",f.profile.class_path)
    assert(not f.session:enter()); assert(#f.mutations == 0)
end)
test("expired or online lease performs no mutation", function()
    local f = fixture(); f.clock = 1001; assert(not f.session:enter()); assert(#f.mutations == 0)
    f.clock = 100; f.lease.offline = false; assert(not f.session:enter()); assert(#f.mutations == 0)
end)
test("partial native Possess failure restores player and AI", function()
    local f = fixture(); f.fail_takeover = true; assert(not f.session:enter())
    assert(f.session.state == "OFF" and f.pc.Pawn == f.player and f.ai.Pawn == f.boss and f.brain.running)
end)
test("camera failure still restores possession", function()
    local f = fixture(); f.fail_camera = true; assert(not f.session:enter())
    assert(f.session.state == "OFF" and f.pc.Pawn == f.player and f.pc.camera == f.player and f.ai.Pawn == f.boss)
end)
test("originally stopped AI remains stopped after exit", function()
    local f = fixture(); f.brain.running = false; assert(f.session:enter()); assert(f.session:restore("exit"))
    assert(f.brain.running == false)
end)
test("game cooldown rejection retains possession", function()
    local f = fixture(); assert(f.session:enter()); f.activation_allowed = false
    assert(not f.session:skill("slot1")); assert(f.session.state == "ACTIVE" and f.pc.Pawn == f.boss)
    assert(f.session:restore("exit"))
end)
test('rejected activation closes pending scheduler before keeping control',function()
    local f=fixture();local pending=false;local closed=0
    f.api.combo_scheduler={begin=function()pending=true end,cancel_all=function()pending=false;closed=closed+1;return true end}
    assert(f.session:enter());f.activation_allowed=false;assert(not f.session:skill('slot1'))
    assert(not pending and closed==1 and f.session.state=='ACTIVE')
    assert(f.session:restore('exit'))
end)
test('activation exception retains scheduler receipt for restoration without a token',function()
    local f=fixture();local closed=0
    f.api.combo_scheduler={begin=function(_,receipt)receipt.combo_trial={};error('partial scheduler start')end,
        cancel_all=function(_,receipt)closed=closed+1;receipt.combo_trial=nil;return true end}
    assert(f.session:enter());assert(not f.session:skill('slot1'))
    assert(closed==1 and f.session.state=='OFF'and f.pc.Pawn==f.player)
end)
test('parent counter alone cannot retire a scheduler token',function()
    local f=fixture();local children_active=true
    f.api.combo_scheduler={begin=function(_,receipt)receipt.combo_trial={}end,changed=function()end,
        poll=function(_,receipt,active)if active==0 and not children_active then receipt.combo_trial=nil;return true end;return false end,
        cancel_all=function(_,receipt)receipt.combo_trial=nil;return true end}
    assert(f.session:enter());assert(f.session:skill('slot1'));f.spec.ActiveCount=0
    assert(f.session:poll()and f.session.current_skill);children_active=false
    assert(f.session:poll()and not f.session.current_skill);assert(f.session:restore('exit'))
end)
test('combo facing refresh occurs only between leaves after target verification',function()
    local f=fixture();assert(f.session:enter());local r=f.session.receipt;local count=0
    r.combo_trial={child_active=true};r.combat={selected_target=f.bridge.calls:reference(f.boss)}
    f.api.combat={verify=function()return true end,verify_target=function()return true end}
    f.api.face_target=function(boss,target)assert(boss==f.boss and target==f.boss);count=count+1 end
    assert(f.bridge:maintain_control(r)and count==0);r.combo_trial.child_active=false
    assert(f.bridge:maintain_control(r)and count==1)
    f.api.combat.verify_target=function()return false end
    assert(not pcall(f.bridge.maintain_control,f.bridge,r));assert(count==1)
end)
test("unverified skill never reaches native activation", function()
    local f = fixture(); assert(f.session:enter()); f.profile.skills.attack.binding_verified = false
    assert(not f.session:skill("slot1")); assert(not f.activation_calls)
end)
test("activity counter blocks overlapping skill without cancelling it", function()
    local f = fixture(); assert(f.session:enter()); f.spec.ActiveCount = 1
    assert(not f.session:skill("slot1")); assert(not f.activation_calls)
end)
test("exit cancels only the tracked Mod skill", function()
    local f = fixture(); assert(f.session:enter()); assert(f.session:skill("slot1"))
    assert(f.session:restore("exit")); assert(f.spec.ActiveCount == 0 and f.pc.Pawn == f.player)
end)
test("cancel failure still restores player and reports FAULTED", function()
    local f = fixture(); assert(f.session:enter()); assert(f.session:skill("slot1")); f.cancellation_allowed = false
    assert(not f.session:restore("exit")); assert(f.pc.Pawn == f.player and f.pc.camera == f.player)
    assert(f.session.state == "FAULTED")
end)
test("destroyed boss cannot prevent best effort player restoration", function()
    local f = fixture(); assert(f.session:enter()); f.boss.alive = false
    assert(not f.session:restore("exit")); assert(f.pc.Pawn == f.player and f.pc.camera == f.player)
end)
test("world change refuses stale movement and possession calls", function()
    local f = fixture(); assert(f.session:enter()); local before = #f.mutations
    f.world = f.object("/Fixture/NewMap.NewMap", "/Script/Engine.World")
    assert(not pcall(f.bridge.move,f.bridge,f.session.receipt,1,0,1)); assert(#f.mutations == before)
end)
test("unbounded movement cannot reach the native call", function()
    local f = fixture(); assert(f.session:enter()); local before = #f.mutations
    assert(not pcall(f.bridge.move,f.bridge,f.session.receipt,2,0,1)); assert(#f.mutations == before)
end)
test('stalled skill requests real cancellation and returns control',function()
    local f=fixture();assert(f.session:enter());assert(f.session:skill('slot1'))
    f.clock=f.clock+31
    assert(not f.session:poll());assert(f.session.state=='OFF' and f.pc.Pawn==f.player)
end)

test('failed camera destruction acknowledgement retains a faulted receipt',function()
    local f=fixture()
    local camera=f.object('/Fixture/Map.Map:PersistentLevel.ModCamera','/Script/Engine.CameraActor')
    local boom=f.object('/Fixture/Map.Map:PersistentLevel.Ahua.ModArm','/Script/Engine.SpringArmComponent')
    local native={spawn_camera=function()return camera end,attach_boom=function()return boom,camera end,
        rotate_boom=function()end,destroy_camera=function()return false end,destroy_boom=function()return true end}
    f.api.camera=require('camera_rig').new(f.bridge.calls,native,{binding_verified=true,distance=500})
    function f.pc:GetControlRotation()return{Yaw=0,Pitch=0}end
    assert(f.session:enter());local receipt=f.session.receipt
    assert(not f.session:restore('exit'));assert(f.pc.Pawn==f.player)
    assert(f.session.state=='FAULTED' and receipt.camera_rig.destroyed~=true)
end)

test("independent camera rig follows and restores without borrowing player components",function()
    local f=fixture()
    function f.pc:GetControlRotation()return {Yaw=390,Pitch=350,Roll=40}end
    local camera=f.object("/Fixture/Map.Map:PersistentLevel.ModCamera","/Script/Engine.CameraActor")
    local boom=f.object("/Fixture/Map.Map:PersistentLevel.ModCamera.SpringArm","/Script/Engine.SpringArmComponent")
    local component=f.object("/Fixture/Map.Map:PersistentLevel.ModCamera.Camera","/Script/Engine.CameraComponent")
    local native={spawn_camera=function()return camera end,
        attach_boom=function()return boom,component end,
        rotate_boom=function(_,rotation)f.camera_rotation=rotation end,
        destroy_camera=function(object)assert(object==camera);object.alive=false;f.camera_destroyed=true;return true end,
        destroy_boom=function(object,owner)assert(object==boom and owner==f.boss);object.alive=false;return true end}
    f.api.camera=require("camera_rig").new(f.bridge.calls,native,{binding_verified=true,distance=500,min_pitch=-60,max_pitch=20})
    assert(f.session:enter());assert(f.pc.camera==camera and f.player.Controller==nil)
    assert(f.bridge:update_camera(f.session.receipt));assert(f.camera_rotation.Yaw==30 and f.camera_rotation.Pitch==-10)
    assert(f.camera_rotation.Roll==0)
    assert(f.session:restore("exit"));assert(f.pc.camera==f.player and f.camera_destroyed)
end)
test("failed camera component setup cleans owned camera and restores player",function()
    local f=fixture()
    local camera=f.object("/Fixture/Map.Map:PersistentLevel.ModCamera","/Script/Engine.CameraActor")
    local native={spawn_camera=function()return camera end,
        attach_boom=function()error("injected spring arm attachment failure")end,
        rotate_boom=function()error("must not rotate incomplete rig")end,
        destroy_camera=function(object)assert(object==camera);object.alive=false;f.camera_destroyed=true;return true end,
        destroy_boom=function()end}
    f.api.camera=require("camera_rig").new(f.bridge.calls,native,{binding_verified=true,distance=500})
    assert(not f.session:enter());assert(f.session.state=="OFF")
    assert(f.pc.Pawn==f.player and f.pc.camera==f.player and f.ai.Pawn==f.boss and f.camera_destroyed)
end)
test("unverified camera contracts fail before a native creation call",function()
    local f=fixture();local native={spawn_camera=function()error("must not spawn")end,
        attach_boom=function()end,rotate_boom=function()end,destroy_camera=function()end,destroy_boom=function()end}
    assert(not pcall(require("camera_rig").new,f.bridge.calls,native,{binding_verified=false,distance=500}))
    assert(#f.mutations==0)
end)
test("camera setup failure after boom creation cleans both owned objects",function()
    local f=fixture()
    local camera=f.object("/Fixture/Map.Map:PersistentLevel.ModCamera","/Script/Engine.CameraActor")
    local boom=f.object("/Fixture/Map.Map:PersistentLevel.Ahua.ModArm","/Script/Engine.SpringArmComponent")
    local native={spawn_camera=function()return camera end,
        attach_boom=function(_,_,_,checkpoint)checkpoint(boom);error("injected camera attachment failure after arm creation")end,
        rotate_boom=function()error("incomplete rig must not rotate")end,
        destroy_camera=function(object)assert(object==camera);object.alive=false;return true end,
        destroy_boom=function(object,owner)assert(object==boom and owner==f.boss);object.alive=false;return true end}
    f.api.camera=require("camera_rig").new(f.bridge.calls,native,{binding_verified=true,distance=500})
    assert(not f.session:enter());assert(f.session.state=="OFF")
    assert(not camera.alive and not boom.alive and f.pc.Pawn==f.player and f.ai.Pawn==f.boss)
end)
test("combat restore failure still restores player AI and brain",function()
    local f=fixture()
    f.api.combat={capture=function()return{}end,apply=function()return true end,verify=function()return true end,
        restore=function()error('injected faction restoration failure')end}
    assert(f.session:enter());assert(not f.session:restore('injected recovery test'))
    assert(f.pc.Pawn==f.player and f.ai.Pawn==f.boss and f.brain.running)
    assert(f.session.receipt and not f.session.receipt.combat.restored)
end)
test('remote branch retains AI ownership and restores independent input state',function()
    local f=fixture();local move_ignored,look_ignored=false,false
    local rotation={Pitch=0,Yaw=0,Roll=0};local brain_tick,ai_tick,ai_started=true,true,true
    f.api.remote=require('remote_control').new(f.bridge.calls,{
        ai_started=function()return ai_started end,set_ai_started=function(_,on)ai_started=on end,
        ai_tick=function()return ai_tick end,set_ai_tick=function(_,on)ai_tick=on end,
        brain_tick=function()return brain_tick end,set_brain_tick=function(_,on)brain_tick=on end,
        snapshot=function()return{move_ignored=false,look_ignored=false,input_enabled=nil,rotation=rotation}end,
        block_move=function(_,v)move_ignored=v end,block_look=function(_,v)look_ignored=v end,
        disable_input=function()error('unknown input stack must not be changed')end,enable_input=function()error('unknown input stack must not be changed')end,
        input_enabled=function()return nil end,move_ignored=function()return move_ignored end,look_ignored=function()return look_ignored end,
        rotation=function()return rotation end,set_rotation=function(_,r)rotation=r end,
        move=function(b,x,y,scale)assert(b==f.boss);f.remote_moved=true end}, {binding_verified=true})
    assert(f.session:enter());assert(f.pc.Pawn==f.player and f.ai.Pawn==f.boss and f.pc.camera==f.boss)
    assert(f.bridge:move(f.session.receipt,1,0,1));assert(f.remote_moved)
    assert(f.session:skill('slot1'));f.spec.ActiveCount=0;f.session:poll()
    assert(f.session:restore('remote exit'));assert(not move_ignored and not look_ignored and f.brain.running and f.pc.camera==f.player)
end)
local function owned_fixture()
    local f=fixture();local calls=f.bridge.calls
    f.api.usable=function(o)return o and o.alive and o.engine_usable~=false or false end
    f.api.owned_temporary={boss=calls:reference(f.boss),ai=calls:reference(f.ai)}
    f.api.read_health=function(o)assert(f.api.usable(o),'health read on disposed object');return 100 end
    f.mod_camera=f.object('/Fixture/Map.Map:PersistentLevel.OwnedCamera')
    f.boom=f.object('/Fixture/Map.Map:PersistentLevel.Ahua.OwnedArm')
    function f.pc:GetControlRotation()return{Yaw=0,Pitch=0,Roll=0}end
    local camera_native={spawn_camera=function()return f.mod_camera end,attach_boom=function()return f.boom,f.mod_camera end,
        rotate_boom=function()end,destroy_camera=function(o)o.engine_usable=false;return true end,
        destroy_boom=function(o)assert(f.api.usable(o));o.engine_usable=false;return true end}
    f.api.camera=require('camera_rig').new(calls,camera_native,{binding_verified=true,distance=500})
    f.faction=f.object('/Fixture/Map.Map:PersistentLevel.Ahua.Faction');f.faction.value='enemy'
    f.player_faction=f.object('/Fixture/Map.Map:PersistentLevel.Hun.Faction');f.player_faction.value='player'
    f.targeting=f.object('/Fixture/Map.Map:PersistentLevel.Ahua.Targeting')
    local function usable(o)assert(f.api.usable(o),'native call on disposed object');return o end
    local combat_native={faction_component=function(o)return o==f.boss and f.faction or f.player_faction end,
        target_component=function()return f.targeting end,read_faction=function(o)return usable(o).value end,
        set_faction=function(o,v)usable(o).value=v end,relation=function()return 0 end,
        read_target=function(o)usable(o);return nil,'None',nil end,clear_target=function(o)usable(o)end,
        set_target=function()error('unexpected target set')end,target_actor=function()end}
    f.api.combat=require('combat_identity').new(calls,combat_native,{binding_verified=true,friendly=0,hostile=2})
    f.move_block,f.look_block=false,false
    f.ai.started,f.ai.tick,f.ai.brain_tick=true,true,true
    local rotation={Yaw=0,Pitch=0,Roll=0}
    local remote_native={ai_started=function(o)return usable(o).started end,set_ai_started=function(o,v)usable(o).started=v end,
        ai_tick=function(o)return usable(o).tick end,set_ai_tick=function(o,v)usable(o).tick=v end,
        brain_tick=function(o)return usable(o).brain_tick end,set_brain_tick=function(o,v)usable(o).brain_tick=v end,
        snapshot=function()return{move_ignored=false,look_ignored=false,input_enabled=nil,rotation=rotation}end,
        block_move=function(_,v)if f.fail_input_restore and not v then error('injected input restore failure')end;f.move_block=v end,
        block_look=function(_,v)f.look_block=v end,disable_input=function()error('unexpected input stack write')end,
        enable_input=function()error('unexpected input stack write')end,input_enabled=function()return nil end,
        move_ignored=function()return f.move_block end,look_ignored=function()return f.look_block end,
        rotation=function()return rotation end,set_rotation=function(_,v)rotation=v end,move=function()end}
    f.api.remote=require('remote_control').new(calls,remote_native,{binding_verified=true})
    function f.ai:K2_DestroyActor()
        f.controller_destroy_calls=(f.controller_destroy_calls or 0)+1
        if not f.fail_controller_destroy then self.engine_usable=false;f.brain.engine_usable=false end
    end
    function f.dispose()
        for _,o in ipairs({f.boss,f.asc,f.boom,f.faction,f.targeting})do o.engine_usable=false end
    end
    return f
end
test('owned native disposal restores actual remote input camera and combat modules',function()
    for _,weak_destroyed in ipairs({false,true})do
        local f=owned_fixture();assert(f.session:enter());local receipt=f.session.receipt
        assert(f.move_block and f.look_block);f.dispose();if weak_destroyed then f.boss.alive=false end
        assert(not f.session:poll());assert(f.session.state=='OFF'and not f.session.receipt)
        assert(f.session.last_restore_reason=='owned boss disposed')
        assert(f.pc.Pawn==f.player and f.pc.camera==f.player and not f.move_block and not f.look_block)
        assert(receipt.owned_disposal_verified and receipt.combat.owner_disposed and receipt.remote_control.restored)
        assert(receipt.camera_rig.destroyed and f.controller_destroy_calls==1 and not f.api.usable(f.ai))
    end
end)
test('owned live exit keeps ordinary AI restoration and does not destroy its controller',function()
    local f=owned_fixture();assert(f.session:enter());assert(f.session:restore('normal exit'))
    assert(not f.controller_destroy_calls and f.api.usable(f.ai)and f.brain.running and f.ai.started and f.ai.tick)
    assert(f.faction.value=='enemy'and not f.move_block and not f.look_block)
end)
test('disposed ability owner clears only its tracked skill without calling dead instances',function()
    local f=owned_fixture();assert(f.session:enter());assert(f.session:skill('slot1'))
    f.api.cancel_skill=function()error('must not call disposed ability')end
    f.dispose();assert(not f.session:poll());assert(f.session.state=='OFF'and next(f.bridge.tokens)==nil)
end)
test('surviving active ability still needs verified cancellation after owner disposal',function()
    local f=owned_fixture();assert(f.session:enter());assert(f.session:skill('slot1'));f.dispose();f.asc.engine_usable=true
    f.cancellation_allowed=false;assert(not f.session:restore('death'))
    assert(f.session.state=='FAULTED'and next(f.bridge.tokens)~=nil and f.spec.ActiveCount==1)
    assert(not f.move_block and not f.look_block and f.pc.camera==f.player and not f.controller_destroy_calls)
end)
test('unowned disposal does not receive owned-death exemptions',function()
    local f=owned_fixture();f.api.owned_temporary=nil;assert(f.session:enter());f.dispose()
    assert(not f.session:restore('death'));assert(f.session.state=='FAULTED'and not f.controller_destroy_calls)
    assert(not f.move_block and not f.look_block and f.pc.camera==f.player)
end)
test('name reuse cannot be hidden by engine invalidity',function()
    local f=owned_fixture();assert(f.session:enter());f.dispose()
    local replacement=f.object(f.boss.path,f.profile.class_path);replacement.engine_usable=false
    assert(not f.session:restore('death'));assert(f.session.state=='FAULTED'and not f.controller_destroy_calls)
end)
test('failed main input restore remains faulted despite successful owned disposal',function()
    local f=owned_fixture();assert(f.session:enter());f.dispose();f.fail_input_restore=true
    assert(not f.session:restore('death'));assert(f.session.state=='FAULTED'and f.move_block)
end)
test('surviving boss components and failed controller destruction are not called restored',function()
    for _,kind in ipairs({'faction','controller'})do
        local f=owned_fixture();assert(f.session:enter());f.dispose()
        if kind=='faction'then f.faction.engine_usable=true else f.fail_controller_destroy=true end
        assert(not f.session:restore('death'));assert(f.session.state=='FAULTED')
        assert(not f.move_block and not f.look_block and f.pc.camera==f.player)
    end
end)
test('repurposed owned controller must not be destroyed',function()
    local f=owned_fixture();assert(f.session:enter());f.dispose();f.ai.Pawn=f.player
    assert(not f.session:restore('death'));assert(f.session.state=='FAULTED'and not f.controller_destroy_calls)
end)
print("Native bridge fixture tests: " .. total .. " passed; no PBZ runtime integration claimed.")
