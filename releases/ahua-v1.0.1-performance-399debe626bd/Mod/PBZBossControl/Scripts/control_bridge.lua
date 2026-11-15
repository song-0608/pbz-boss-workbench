-- 用途：把控制会话接到真实UE4SS对象与函数；没有目标绑定/离线租约时不会自行启用。
-- 注意：这份实现仍须在阿花上实机验收；模块测试不能证明镜头、运动和招式已适配。
local Calls = require("ue_calls")
local Bridge = {}
Bridge.__index = Bridge

local function valid(object) return object and object:IsValid() end
local function class_path(object) return object:GetClass():GetFullName():match("^[^ ]+ (.+)$") end
local function same_reference(a,b)
    return type(a)=='table'and type(b)=='table'and a.name==b.name and a.address==b.address and a.class==b.class
end

function Bridge.new(api, profile)
    assert(type(api) == "table" and type(api.attest) == "function" and type(api.now) == "function"
        and type(api.find_all) == "function" and type(api.find_exact) == "function", "runtime API incomplete")
    assert(type(profile) == "table" and profile.identity_verified == true
        and type(profile.class_path) == "string" and profile.class_path:sub(1, 1) == "/",
        "verified boss class binding required")
    return setmetatable({ api = api, calls = Calls.new(api), profile = profile, serial = 0,
        tokens = {}, active_receipt = nil, available = true }, Bridge)
end

function Bridge:environment() -- 用途：每次动作都读取本轮运行租约；不会把写死offline=true当作验证。
    local lease = self.api.attest()
    assert(type(lease) == "table" and lease.isolated == true and lease.offline == true
        and type(lease.expires_at) == "number" and lease.expires_at > self.api.now()
        and type(lease.session_id) == "string" and lease.session_id ~= "", "active offline research lease required")
    assert(lease.exe_sha256 == self.profile.exe_sha256, "game build mismatch")
    return lease
end

function Bridge:player_controller()
    local matches = {}
    for _, pc in ipairs(self.api.find_all("PBZPlayerController") or {}) do
        if valid(pc) and pc:GetFullName():find(":PersistentLevel.", 1, true) and valid(pc.Pawn) then
            assert(self.calls:same(pc:K2_GetPawn(), pc.Pawn), "controller query mismatch")
            assert(self.calls:same(pc.Pawn:GetController(), pc), "pawn controller mismatch")
            matches[#matches + 1] = pc
        end
    end
    assert(#matches == 1, "exactly one local gameplay controller required")
    return matches[1]
end

function Bridge:world_id(actor, lease)
    local world = self.calls:world(actor)
    return lease.session_id .. "|" .. world.name .. "|" .. tostring(world.address)
end

function Bridge:target(pc) -- 用途：只选择确证类的现有战斗Pawn；不凭显示名、特效或家具猜测。
    local matches, world = {}, self.calls:world(pc)
    for _, pawn in ipairs(self.api.find_all("PBZCharacter_NPC") or {}) do
        if valid(pawn) and class_path(pawn) == self.profile.class_path
            and pawn:GetFullName():find(":PersistentLevel.", 1, true) then
            local same_world = self.calls:world(pawn)
            if world.address == same_world.address and world.name == same_world.name
                and (not self.profile.instance_name or pawn:GetFullName() == self.profile.instance_name) then
                matches[#matches + 1] = pawn
            end
        end
    end
    if #matches == 0 then return nil end
    assert(#matches == 1, "boss selection is ambiguous")
    return matches[1]
end

function Bridge:context()
    local lease = self:environment()
    -- 用途：Boss销毁后Pawn可能无效；恢复必须仍能通过已保存的PlayerController找回主角。
    local pc = self.active_receipt and self.calls:resolve(self.active_receipt.player_controller) or self:player_controller()
    local boss_available
    if self.active_receipt then
        local ok, boss = pcall(self.calls.resolve, self.calls, self.active_receipt.boss)
        boss_available = ok and valid(boss) or false
    else
        boss_available = self:target(pc) ~= nil
    end
    return { isolated = true, offline = true, exe_sha256 = lease.exe_sha256,
        world_id = self:world_id(pc, lease), boss_available = boss_available }
end

function Bridge:check(receipt) -- 用途：恢复前也验证本轮租约与World，不跨图套用旧恢复凭据。
    assert(type(receipt) == "table", "receipt required")
    local lease = self:environment()
    local pc = self.calls:resolve(receipt.player_controller)
    assert(self:world_id(pc, lease) == receipt.world_id, "world or research session changed")
    return pc
end

function Bridge:capture() -- 用途：在第一次修改前保存玩家、Boss、AI、镜头和AI原运行状态。
    assert(self.active_receipt == nil, "another takeover receipt exists")
    local lease, pc = self:environment(), self:player_controller()
    local original, boss = self.calls:pawn(pc), assert(self:target(pc), "verified boss is not loaded")
    assert(not self.calls:same(original, boss), "already controlling selected boss")
    if self.api.read_health then
        for _,pawn in ipairs({original,boss})do
            local health=self.api.read_health(pawn)
            assert(type(health)=='number'and health==health and health>0 and health<math.huge,'living control participants required')
        end
    end
    local ai = self.calls:controller(boss)
    assert(not self.calls:same(ai, pc), "boss already has player controller")
    local brain = ai.BrainComponent
    assert(valid(brain) and valid(boss.CharacterMovement) and valid(boss.AbilitySystemComponent),
        "combat AI, movement and ability system must be ready")
    assert(self.calls:same(ai:K2_GetPawn(), boss), "AI does not own the selected boss")
    local running = brain:IsRunning(); assert(type(running) == "boolean", "AI state unreadable")
    local receipt = { world_id = self:world_id(pc, lease), world=self.calls:world(pc), player_controller = self.calls:reference(pc),
        player = self.calls:reference(original), boss = self.calls:reference(boss),
        ai = self.calls:reference(ai), brain = self.calls:reference(brain),
        asc = self.calls:reference(boss.AbilitySystemComponent),
        camera = self.calls:reference(self.calls:view_target(pc)), ai_was_running = running,
        mutations = {}, input_enabled = false }
    if self.api.owned_temporary then
        assert(type(self.api.usable)=='function','engine validity required for owned disposal')
        local owned=self.api.owned_temporary
        assert(same_reference(receipt.boss,owned.boss)and same_reference(receipt.ai,owned.ai),
            'temporary ownership does not match selected boss/controller')
        receipt.owned_temporary=true
    end
    if self.api.combat then receipt.combat=self.api.combat:capture(original,boss)end
    if self.api.remote then receipt.remote_control=self.api.remote:capture(pc,original,boss,ai)end
    if self.api.player_protection then receipt.player_protection=self.api.player_protection:capture(original)end
    self.active_receipt = receipt
    return receipt
end

function Bridge:world_boundary(receipt)
    self:environment()
    assert(self.active_receipt==receipt,'world boundary receipt mismatch')
    local now=self.api.now()
    if receipt.transition_checked_at and now==receipt.transition_checked_at and receipt.transition_pending then
        return 'pending',receipt.transition_pending,now
    end
    local ok,status,why=pcall(require('world_boundary').inspect,self.calls,receipt)
    if not ok then
        print('PBZ_CONTROL_WORLD:BOUNDARY_UNREADABLE='..tostring(status)..'\n');error(status)
    end
    if status=='pending'then receipt.transition_checked_at=now;receipt.transition_pending=why end
    if status=='retired'then
        -- 用途：只有引擎确认全部旧对象不可用才释放Lua令牌；有任何存活组件或身份复用就不能通过。
        for token,record in pairs(self.tokens)do if record.receipt==receipt then self.tokens[token]=nil end end
        receipt.input_enabled=false;receipt.world_retired=true;self.active_receipt=nil
        print('PBZ_CONTROL_WORLD:OLD_OBJECTS_DISPOSED=true\n')
    end
    return status,why,self.api.now()
end

function Bridge:owned_boss_disposed(receipt)
    -- 用途：只对本轮实验明确登记的自建Boss承认原生销毁，不能将普通Boss失联或地址复用当作死亡。
    return receipt.owned_temporary==true and self.calls:optional(receipt.boss)==nil
end

function Bridge:dispose_owned_controller(receipt)
    assert(self:owned_boss_disposed(receipt),'owned boss disposal required')
    assert(not self.calls:optional(receipt.asc),'disposed boss ability system remains engine-usable')
    -- 用途：死亡可能留下暂停的自建Controller；先核对原Brain身份，拒绝删除已接管其他活Pawn的控制器。
    self.calls:optional(receipt.brain)
    local ai=self.calls:optional(receipt.ai)
    if ai then
        local pawn=ai:K2_GetPawn()
        if valid(pawn)then
            assert(pawn:GetFullName()==receipt.boss.name and pawn:GetAddress()==receipt.boss.address
                and pawn:GetClass():GetFullName()==receipt.boss.class,
                'owned controller now belongs to a different pawn')
        end
        ai:K2_DestroyActor()
    end
    assert(not self.calls:optional(receipt.ai)and not self.calls:optional(receipt.brain),
        'owned dead controller/brain disposal not verified')
    receipt.owned_disposal_verified=true
    print('PBZ_CONTROL_RESTORE:OWNED_DISPOSAL_VERIFIED=true\n')
end

function Bridge:control_health(receipt)
    -- 用途：逐帧与出招前读取真实生命；不补血、不复活，也不把零生命角色继续当作可控Boss。
    self:check(receipt)
    if self:owned_boss_disposed(receipt)then return false,'owned boss disposed'end
    if not self.api.read_health then return true end
    local health=self.api.read_health(self.calls:resolve(receipt.boss))
    assert(type(health)=='number'and health==health and math.abs(health)<math.huge,'boss health unreadable')
    return health>0,'boss health depleted'
end

function Bridge:take_control(receipt)
    local pc = self:check(receipt)
    local boss = self.calls:resolve(receipt.boss)
    local brain = self.calls:resolve(receipt.brain)
    if receipt.player_protection then
        receipt.mutations.player_protection=true;self.api.player_protection:apply(receipt.player_protection)
    end
    receipt.mutations.brain = true -- 用途：先记恢复责任，再调用；函数中途失败也需要恢复。
    self.calls:stop_brain(brain)
    if receipt.combat then
        receipt.mutations.combat=true
        self.api.combat:apply(receipt.combat)
    end
    if receipt.remote_control then
        receipt.mutations.remote=true
        self.api.remote:apply(receipt.remote_control)
    else
        receipt.mutations.possession = true
        self.calls:possess(pc, boss)
    end
    receipt.mutations.camera = true
    local target=boss
    if self.api.camera then target=self.api.camera:create(pc,boss,receipt) end
    if self.api.input_barrier then
        assert(receipt.camera_rig,'input barrier requires an owned camera actor')
        self.api.input_barrier:attach(pc,target,receipt)
    end
    self.calls:view(pc, target)
    receipt.input_enabled = true
    return self:verify_control(receipt)
end

function Bridge:maintain_control(receipt)
    -- 用途：逐帧调度前仍核对本轮构建/World；维护只作用于本次遥控的临时Boss。
    self:check(receipt)
    if receipt.remote_control then
        local ready,why=self.api.remote:maintain(receipt.remote_control)
        if not ready then return false,why end
    end
    -- 用途：原AIController tick保持关闭；仅子招式间隙重对准已锁定目标，不改正在运行的根运动。
    if receipt.combo_trial and not receipt.combo_trial.child_active and self.api.face_target then
        assert(receipt.combat and self.api.combat:verify_target(receipt.combat),'combo target changed between leaves')
        self.api.face_target(self.calls:resolve(receipt.boss),self.calls:resolve(receipt.combat.selected_target))
    end
    return true
end

function Bridge:verify_control(receipt)
    local pc = self:check(receipt)
    local boss, brain = self.calls:resolve(receipt.boss), self.calls:resolve(receipt.brain)
    local target=receipt.camera_rig and self.api.camera:target(receipt.camera_rig) or boss
    local owned=receipt.remote_control and self.api.remote:verify(receipt.remote_control)
        or(not receipt.remote_control and self.calls:same(self.calls:pawn(pc),boss)and self.calls:same(self.calls:controller(boss),pc))
    local checks={combat=not receipt.combat or self.api.combat:verify(receipt.combat),owned=owned,
        barrier=not self.api.input_barrier or self.api.input_barrier:verify(receipt.input_barrier),
        protected=not receipt.player_protection or self.api.player_protection:verify(receipt.player_protection),
        camera=self.calls:same(self.calls:view_target(pc), target),brain_stopped=receipt.remote_control
            and (self.api.remote.brain_policy_valid and self.api.remote:brain_policy_valid(receipt.remote_control)
                or(not self.api.remote.brain_policy_valid and self.api.remote:brain_suspended(receipt.remote_control)))
            or(not receipt.remote_control and brain:IsRunning()==false)}
    for name,value in pairs(checks)do
        if not value then
            if not receipt.failure_logged then print('PBZ_CONTROL_VERIFY:FAILED='..name);receipt.failure_logged=true end
            return false
        end
    end
    return true
end

function Bridge:definition(id)
    local definition = (self.profile.skills or {})[id]
    assert(definition and definition.binding_verified == true and type(definition.class_path) == "string"
        and type(definition.active_count_field) == "string", "verified skill and activity binding required")
    return definition
end

function Bridge:spec(receipt, definition) -- 用途：逐次校验长度后读取已授予能力；不授予新技能，不越界索引。
    local asc = self.calls:resolve(receipt.asc)
    local items, found = asc.ActivatableAbilities.Items, nil
    local count = items:GetArrayNum()
    assert(math.type(count) == "integer" and count >= 0 and count <= 512, "invalid bounded ability list")
    for index = 1, count do
        assert(index <= items:GetArrayNum(), "ability list changed before indexed access")
        local candidate = items[index]
        if valid(candidate.Ability) and class_path(candidate.Ability) == definition.class_path then
            assert(found == nil, "multiple grants share the skill class; handle binding required")
            found = candidate
        end
    end
    assert(found ~= nil, "skill is not granted to the selected boss")
    local active = found[definition.active_count_field]
    assert(math.type(active) == "integer" and active >= 0 and active <= 255, "skill activity is unreadable")
    return found, active, asc
end

function Bridge:can_start_skill(receipt, id)
    self:check(receipt)
    if receipt.target_transition then return false,'target change pending' end
    if not receipt.input_enabled or not self:verify_control(receipt) then return false,'control unavailable' end
    local definition=self:definition(id)
    if definition.requires_target then
        if not receipt.combat or not self.api.combat:verify_target(receipt.combat)then return false,'target lock unavailable' end
        if self.api.target_selector then
            local ok,target=pcall(self.calls.resolve,self.calls,receipt.combat.selected_target)
            if not ok then return false,'target no longer available'end
            local eligible,why=self.api.target_selector:eligible(self.calls:resolve(receipt.boss),self.calls:resolve(receipt.player),target)
            if not eligible then return false,'target rejected: '..tostring(why)end
        end
    end
    local _, active = self:spec(receipt, self:definition(id))
    return active == 0, active>0 and 'ability already active' or nil -- 冷却、资源仍由原生激活检查。
end

function Bridge:cycle_target(receipt) -- 用途：请求切换后保留旧目标凭据，等待真实技能查询在后续帧确认。
    self:check(receipt)
    if not self.api.target_selector or not receipt.combat then return false,'target selection unavailable' end
    if not receipt.input_enabled or not self:verify_control(receipt)then return false,'control unavailable' end
    local boss,player=self.calls:resolve(receipt.boss),self.calls:resolve(receipt.player)
    local previous=receipt.combat.selected_target
    local ok,current=pcall(self.calls.resolve,self.calls,previous)
    local target,why,count=self.api.target_selector:next(boss,player,ok and current or nil)
    if not target then return false,why end
    -- 用途：先登记恢复责任；SetLockTarget成功、SetFocus失败时也能清理部分修改。
    receipt.target_transition={previous=previous,requested=self.calls:reference(target),polls=0,count=count}
    self.api.combat:request_target(receipt.combat,target,'None')
    return target:GetFullName()
end

function Bridge:poll_target_change(receipt)
    self:check(receipt)
    local pending=assert(receipt.target_transition,'no target transition')
    local target=self.calls:resolve(pending.requested)
    if not self.api.target_selector:eligible(self.calls:resolve(receipt.boss),self.calls:resolve(receipt.player),target)then
        return 'rejected','requested target is no longer eligible'
    end
    if self.api.combat:verify_target(receipt.combat)then
        receipt.target_transition=nil
        return 'verified',target:GetFullName()
    end
    pending.polls=pending.polls+1
    if pending.polls>=90 then return 'rejected','target query did not settle in 90 frames' end
    return 'pending'
end

function Bridge:cancel_target_change(receipt) -- 用途：失败时恢复先前目标；旧目标也失效则清锁定，不自动出招。
    self:check(receipt)
    local pending=receipt.target_transition
    if not pending then return true end
    local combat,ticket=self.api.combat,receipt.combat
    local ok,target=pcall(self.calls.resolve,self.calls,pending.previous)
    if ok and self.api.target_selector:eligible(self.calls:resolve(receipt.boss),self.calls:resolve(receipt.player),target)then
        combat:request_target(ticket,target,'None')
    else
        combat.native.clear_target(self.calls:resolve(ticket.targeting))
        if ticket.focus_controller then combat.native.set_focus(self.calls:resolve(ticket.focus_controller),nil)end
        ticket.selected_target=nil
    end
    receipt.target_transition=nil
    return true
end

function Bridge:start_skill(receipt, id)
    if not self:can_start_skill(receipt, id) then return false end
    local definition = self:definition(id)
    local spec, _, asc = self:spec(receipt, definition)
    if definition.requires_target and self.api.face_target then
        self.api.face_target(self.calls:resolve(receipt.boss),self.calls:resolve(receipt.combat.selected_target))
    end
    if self.api.before_skill then self.api.before_skill(receipt,id)end
    if self.api.combo_scheduler then self.api.combo_scheduler:begin(receipt,id,definition)end
    if not self.calls:activate(asc, spec.Ability:GetClass()) then
        if self.api.combo_scheduler then self.api.combo_scheduler:cancel_all(receipt)end
        return false
    end
    if self.api.combo_scheduler and receipt.combo_trial then self.api.combo_scheduler:changed(receipt)end
    self.serial = self.serial + 1
    local token = "skill-" .. self.serial
    self.tokens[token] = { id = id, receipt = receipt, started_at = self.api.now() }
    return token
end

function Bridge:is_skill_finished(receipt, token) -- 用途：读取真实活动计数；不按动画秒数猜测结束。
    self:check(receipt)
    local record = assert(self.tokens[token], "unknown skill token")
    assert(record.receipt == receipt, "skill belongs to another control session")
    local _, active = self:spec(receipt, self:definition(record.id))
    local finished=active==0
    if self.api.combo_scheduler and receipt.combo_trial then finished=self.api.combo_scheduler:poll(receipt,active)end
    if finished then self.tokens[token] = nil; return true end
    -- 用途：挂起招式走原有的真实取消/恢复通道；拒绝仅在Lua里把current_skill清空而让游戏继续出招。
    local limit=self.profile.skill_timeout_seconds or 30
    assert(type(limit)=='number'and limit>=5 and limit<=120,'invalid skill activity timeout')
    assert(self.api.now()-record.started_at<=limit,'skill activity timeout: '..record.id)
    return false
end

function Bridge:cancel_skills(receipt) -- 用途：只中断此Mod启动的技能；不清空Boss的所有能力或冷却。
    self:check(receipt)
    receipt.input_enabled = false
    local disposed=self:owned_boss_disposed(receipt)
    local asc_disposed=disposed and self.calls:optional(receipt.asc)==nil
    local all_ok = true
    if self.api.combo_scheduler and receipt.combo_trial and not asc_disposed then
        local ok,why=pcall(self.api.combo_scheduler.cancel_all,self.api.combo_scheduler,receipt)
        if not ok then print('PBZ_COMBO_CANCEL:FAILED='..tostring(why)..'\n');all_ok=false end
    end
    for token, record in pairs(self.tokens) do
        if record.receipt == receipt then
            local ok = pcall(function()
                if asc_disposed then
                    print('PBZ_CONTROL_RESTORE:OWNED_SKILL_DISPOSED='..record.id..'\n')
                    return
                end
                local definition = self:definition(record.id)
                local spec, active = self:spec(receipt, definition)
                if active > 0 then
                    assert(type(self.api.cancel_skill) == "function", "verified cancellation binding missing")
                    assert(self.api.cancel_skill(spec, definition) == true, "skill cancellation rejected")
                    local _, after = self:spec(receipt, definition)
                    assert(after == 0, "skill remains active after cancellation")
                end
            end)
            if ok then self.tokens[token] = nil else all_ok = false end
        end
    end
    return all_ok
end

function Bridge:restore(receipt) -- 用途：技能中断失败也优先尝试还原主角和镜头，各阶段独立处理。
    local pc = self:check(receipt)
    receipt.input_enabled = false
    local failures = {}
    local function attempt(label, fn)
        local ok, why = pcall(fn)
        if not ok then
            failures[#failures + 1] = label .. ": " .. tostring(why)
            -- 用途：保留具体失败阶段，不能只给玩家一条“restore not verified”。
            print('PBZ_CONTROL_RESTORE:FAILED='..label..'|'..tostring(why)..'\n')
        end
    end
    if receipt.mutations.possession then
        attempt("player", function() self.calls:possess(pc, self.calls:resolve(receipt.player)) end)
    end
    if receipt.input_barrier then
        attempt('input barrier',function()self.api.input_barrier:detach(receipt.input_barrier)end)
    end
    if receipt.mutations.camera then
        attempt("camera", function()
            self.calls:view(pc, self.calls:resolve(receipt.camera))
            if receipt.camera_rig then self.api.camera:destroy(receipt.camera_rig) end
        end)
    end
    local disposed=false
    attempt('owned death disposal',function()
        if self:owned_boss_disposed(receipt)then
            self:dispose_owned_controller(receipt);disposed=true
        end
    end)
    if receipt.mutations.combat then
        -- 用途：阵营恢复失败也继续恢复原AI控制器和Brain，分别保留错误供集中修复。
        attempt("combat identity", function() self.api.combat:restore(receipt.combat,disposed)end)
    end
    if receipt.mutations.possession and not disposed then
        attempt("boss AI controller", function()
            self.calls:possess(self.calls:resolve(receipt.ai), self.calls:resolve(receipt.boss))
        end)
    end
    if receipt.mutations.brain and not disposed then
        attempt("brain", function()
            self.calls:restore_brain(self.calls:resolve(receipt.brain), receipt.ai_was_running)
        end)
    end
    if receipt.mutations.remote then
        attempt('player input',function()self.api.remote:restore(receipt.remote_control,disposed)end)
    end
    if receipt.mutations.player_protection then
        attempt('original player protection',function()self.api.player_protection:restore(receipt.player_protection)end)
    end
    receipt.restore_failures = failures
    return #failures == 0
end

function Bridge:verify_restored(receipt)
    local pc = self:check(receipt)
    local player = self.calls:resolve(receipt.player)
    local verified = self.calls:same(self.calls:pawn(pc), player) and self.calls:same(self.calls:controller(player), pc)
        and self.calls:same(self.calls:view_target(pc), self.calls:resolve(receipt.camera))
    if self:owned_boss_disposed(receipt)then
        verified=verified and receipt.owned_disposal_verified==true and not self.calls:optional(receipt.asc)
            and not self.calls:optional(receipt.ai)and not self.calls:optional(receipt.brain)
    else
        local boss,ai,brain=self.calls:resolve(receipt.boss),self.calls:resolve(receipt.ai),self.calls:resolve(receipt.brain)
        verified=verified and self.calls:same(self.calls:pawn(ai),boss)and self.calls:same(self.calls:controller(boss),ai)
            and brain:IsRunning()==receipt.ai_was_running
    end
    if receipt.combat and receipt.mutations.combat then verified=verified and receipt.combat.restored==true end
    if receipt.remote_control then verified=verified and receipt.remote_control.restored==true end
    if receipt.input_barrier then verified=verified and receipt.input_barrier.removed==true end
    if receipt.camera_rig then verified=verified and receipt.camera_rig.destroyed==true end
    if receipt.player_protection then verified=verified and receipt.player_protection.restored==true end
    if verified then self.active_receipt = nil end
    return verified
end

function Bridge:move(receipt, x, y, scale)
    self:check(receipt)
    assert(receipt.input_enabled and self:verify_control(receipt), "movement requires current possession")
    if receipt.remote_control then return self.api.remote:move(receipt.remote_control,x,y,scale)end
    return self.calls:move(self.calls:resolve(receipt.boss), x, y, scale)
end

function Bridge:look(receipt, yaw, pitch)
    self:check(receipt)
    assert(receipt.input_enabled and self:verify_control(receipt), "look requires current possession")
    if receipt.remote_control then return self.api.remote:look(receipt.remote_control,yaw,pitch)end
    return self.calls:look(self.calls:resolve(receipt.boss), yaw, pitch)
end

function Bridge:update_camera(receipt)
    local pc=self:check(receipt)
    if receipt.camera_rig then
        assert(receipt.input_enabled,"camera update requires active input")
        return self.api.camera:update(pc,self.calls:resolve(receipt.boss),receipt.camera_rig)
    end
    return true
end

return Bridge
