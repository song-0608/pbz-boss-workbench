-- 用途：实际UE4SS反射调用层；只封装本构建已读取过声明的接管、镜头、AI和移动接口。
-- 本模块不会自行启动游戏、创建Boss、修改存档或注册按键；上层须先验证对象身份与研究环境。
local Calls = {}
Calls.__index = Calls

local function valid(object, label)
    assert(object and object:IsValid(), (label or "object") .. " is invalid")
    return object
end

function Calls.new(api) -- 用途：实机使用UE4SS全局，测试时可注入假对象，不混淆两种证据。
    assert(type(api) == "table" and type(api.find_exact) == "function", "object resolver required")
    return setmetatable({ api = api }, Calls)
end

function Calls:reference(object) -- 用途：恢复凭据保存名字/地址/类；每次操作重新查找，不持有旧UObject。
    valid(object)
    if self.api.usable then assert(self.api.usable(object),'engine rejected object reference')end
    return { name = object:GetFullName(), address = object:GetAddress(), class = object:GetClass():GetFullName() }
end

function Calls:optional(reference) -- 用途：仅将确证不存在/已失效视为缺席；身份替换和有效性读取失败仍抛错。
    assert(type(reference) == "table" and type(reference.name) == "string", "reference required")
    local path = assert(reference.name:match("^[^ ]+ (.+)$"), "full object name required")
    local object = self.api.find_exact(path)
    if object == nil then return nil end
    local weak_valid=object:IsValid()
    assert(type(weak_valid)=='boolean','object weak validity unreadable')
    if not weak_valid then return nil end
    assert(object:GetFullName() == reference.name and object:GetAddress() == reference.address
        and object:GetClass():GetFullName() == reference.class, "object identity changed")
    if self.api.usable then
        local usable=self.api.usable(object)
        assert(type(usable)=='boolean','object engine validity unreadable')
        if not usable then return nil end
    end
    return object
end

function Calls:resolve(reference)
    return assert(self:optional(reference),'resolved object is absent or no longer engine-usable')
end

function Calls:retirement_optional(reference)
    -- 同名新World会遮蔽旧对象。仅清理检查允许独立枚举原类，以原地址查旧对象是否仍登记。
    -- 正常恢复/技能仍使用严格optional，绝不将新对象交给旧凭据。
    if not self.api.find_all then return self:optional(reference)end
    local path=assert(reference.name:match('^[^ ]+ (.+)$'),'full object name required')
    local named=self.api.find_exact(path)
    if named and named:IsValid()and named:GetAddress()==reference.address then
        if self.api.usable then
            local usable=self.api.usable(named);assert(type(usable)=='boolean','retirement validity unreadable')
            if not usable then return nil end
        end
        if named:GetFullName()==reference.name and named:GetClass():GetFullName()==reference.class then return named end
        return {retirement_ambiguous=true}
    end
    local class_name=assert(reference.class:match('([^%. /]+)$'),'class short name required')
    local candidates=self.api.find_all(class_name)or{}
    assert(type(candidates)=='table'and #candidates<=4096,'retirement class enumeration exceeded bound')
    local found
    for _,object in ipairs(candidates)do
        if object and object:IsValid()and object:GetAddress()==reference.address then
            assert(not found,'ambiguous retired object address')
            local usable=true
            if self.api.usable then
                usable=self.api.usable(object);assert(type(usable)=='boolean','retirement validity unreadable')
            end
            if usable then
                if object:GetFullName()==reference.name and object:GetClass():GetFullName()==reference.class then found=object
                else found={retirement_ambiguous=true}end
            end
        end
    end
    return found
end

function Calls:optional_world(actor)
    local world=valid(actor):GetWorld()
    if not world or not world:IsValid()then return nil end
    if self.api.usable then
        local usable=self.api.usable(world);assert(type(usable)=='boolean','World validity unreadable')
        if not usable then return nil end
    end
    return self:reference(world)
end

function Calls:world(actor) -- 用途：用真实UWorld身份比较；流送子关卡路径不同不应误判成不同世界。
    return self:reference(valid(actor):GetWorld())
end

function Calls:same(a, b)
    return a and b and a:IsValid() and b:IsValid() and a:GetAddress() == b:GetAddress()
        and a:GetFullName() == b:GetFullName()
end

function Calls:pawn(controller) return valid(valid(controller):K2_GetPawn(), "controlled pawn") end
function Calls:controller(pawn) return valid(valid(pawn):GetController(), "pawn controller") end
function Calls:view_target(controller) return valid(valid(controller):GetViewTarget(), "view target") end

function Calls:possess(controller, pawn) -- 用途：走引擎接管流程，不能只把Pawn属性改成另一个指针。
    valid(controller):Possess(valid(pawn))
    assert(self:same(self:pawn(controller), pawn) and self:same(self:controller(pawn), controller),
        "Possess returned without reciprocal possession")
    return true
end

function Calls:view(controller, target) -- 用途：切换真实ViewTarget；保留原对象以便恢复镜头。
    valid(controller):SetViewTargetWithBlend(valid(target), 0.0, 0, 0.0, false)
    assert(self:same(self:view_target(controller), target), "view target did not change")
    return true
end

function Calls:stop_brain(brain) -- 用途：停止实际Brain决策并回读；不靠删除AI组件停AI。
    valid(brain):StopLogic("PBZBossControl player takeover")
    assert(brain:IsRunning() == false, "AI brain did not stop")
    return true
end

function Calls:restore_brain(brain, was_running)
    valid(brain)
    if was_running then brain:StartLogic() else brain:StopLogic("PBZBossControl restore stopped state") end
    assert(brain:IsRunning() == was_running, "AI running state did not restore")
    return true
end

function Calls:move(pawn, x, y, scale) -- 用途：把世界方向交给原MovementComponent，不直接写坐标或穿墙。
    assert(type(x) == "number" and type(y) == "number" and x == x and y == y, "finite direction required")
    assert(type(scale) == "number" and scale >= -1 and scale <= 1, "bounded movement scale required")
    assert(x * x + y * y <= 1.000001, "direction must be normalized")
    valid(pawn):AddMovementInput({ X = x, Y = y, Z = 0.0 }, scale, false)
    return true -- 用途：这里只表示已提交输入；是否真实移动必须在实机回读位置验收。
end

function Calls:look(pawn, yaw, pitch)
    assert(type(yaw) == "number" and math.abs(yaw) <= 10 and type(pitch) == "number"
        and math.abs(pitch) <= 10, "bounded look input required")
    valid(pawn):AddControllerYawInput(yaw)
    pawn:AddControllerPitchInput(pitch)
    return true
end

function Calls:activate(asc, ability_class) -- 用途：真实GAS激活会检查游戏冷却/资源；禁用远程激活。
    return valid(asc):TryActivateAbilityByClass(valid(ability_class), false) == true
end

function Calls:cancel(spec, binding) -- 用途：仅调用该技能实际实例的取消入口；不对CDO或其他技能批量取消。
    assert(binding.cancel_binding_verified == true and binding.cancel_function == "K2_CancelAbility",
        "verified cancellation declaration required")
    local ability_class = valid(spec.Ability):GetClass():GetFullName()
    local matched,invoked=0,0
    local function trace(reason,instance)
        -- 用途：明确区分“不允许取消”“没有匹配实例”和“调用后未归零”；诊断失败不改变取消结果。
        if self.api.cancel_trace then pcall(self.api.cancel_trace,{reason=reason,ability_class=ability_class,
            active=spec[binding.active_count_field],matched=matched,invoked=invoked,
            instance=instance and instance:GetFullName()or'None'})end
    end
    for _, field in ipairs({ "NonReplicatedInstances", "ReplicatedInstances" }) do
        local instances = spec[field]
        local count = instances:GetArrayNum()
        assert(math.type(count) == "integer" and count >= 0 and count <= 64, "invalid ability instance list")
        for index = 1, count do
            assert(index <= instances:GetArrayNum(), "ability instances changed before indexed access")
            local instance = instances[index]
            if instance and instance:IsValid() and instance:GetClass():GetFullName() == ability_class
                and not instance:GetFullName():find("Default__", 1, true) and instance.bIsActive == true then
                matched=matched+1
                if instance.bIsCancelable ~= true then trace('instance_not_cancelable',instance);return false end
                trace('invoking_cancel',instance)
                instance:K2_CancelAbility()
                invoked=invoked+1
            end
        end
    end
    local cleared=spec[binding.active_count_field] == 0
    trace(cleared and'activity_cleared'or(matched==0 and'no_matching_active_instance'or'cancel_invoked_but_still_active'))
    return cleared
end

return Calls
