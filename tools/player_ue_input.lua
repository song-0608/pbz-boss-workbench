-- 用途：实际读取UE玩家控制器的键盘、鼠标和控制旋转；不自行声明当前版本已经验证。
local Input = {}
Input.__index = Input

function Input.new(bridge, api, binding)
    assert(type(api) == "table" and type(api.make_name) == "function"
        and type(api.game_paused) == "function", "FName and pause query bindings required")
    assert(type(binding) == "table" and binding.input_verified == true,
        "FKey fields, out parameters and control rotation must be verified first")
    assert(type(binding.mouse_scale) == "number" and binding.mouse_scale > 0 and binding.mouse_scale <= 1,
        "bounded mouse scale required")
    local tuned={};for key,value in pairs(binding)do tuned[key]=value end
    tuned.look_step_degrees=require('player_3c_tuning').look_limit(bridge.api and bridge.api.locomotion)
    if bridge.profile and bridge.profile.id then
        tuned.mouse_scale=require('player_3c_tuning').resolve(bridge.profile.id).mouse_scale
    end
    return setmetatable({ bridge = bridge, api = api, binding = tuned, key_names = {} }, Input)
end

function Input:read(receipt,checked_pc)
    -- 只在同一次同步调度中复用维护后核对过的控制器。独立读取仍核验 World 和遥控归属。
    local pc = checked_pc or self.bridge:check(receipt)
    -- 用途：遥控模式由本Mod屏蔽原主角输入，但仍读取原始键位驱动Boss；暂停仍一律停止采样。
    local remote=receipt.remote_control and (checked_pc~=nil or self.bridge.api.remote:verify(receipt.remote_control))
    if self.api.game_paused(pc)then return {allowed=false,paused=true}end
    if pc:IsMoveInputIgnored()and not remote then return {allowed=false}end
    local function down(name)
        -- FName 是进程内名称值，非 UObject；只缓存四个名称，角色身份仍逐帧核对。
        local key=self.key_names[name]
        if key==nil then key=self.api.make_name(name);self.key_names[name]=key end
        return pc:IsInputKeyDown({ KeyName = key }) == true
    end
    local rotation = pc:GetControlRotation()
    local dx, dy = {}, {}
    pc:GetInputMouseDelta(dx, dy) -- 用途：固定源码将标量out参数写入同名字段，不是Lua多返回值。
    assert(type(dx.DeltaX) == "number" and type(dy.DeltaY) == "number", "mouse out parameters unreadable")
    local look_allowed = remote or pc:IsLookInputIgnored() == false
    local function look_delta(value)
        assert(value==value and math.abs(value)<math.huge,'nonfinite mouse input')
        -- 用途：低帧率或快速甩鼠标会积累大位移；限制单帧转角，不因此退回主角。
        local limit=self.binding.look_step_degrees
        return math.max(-limit,math.min(limit,value*self.binding.mouse_scale))
    end
    return { allowed = true, forward = down("W"), backward = down("S"), left = down("A"), right = down("D"),
        yaw_degrees = rotation.Yaw,
        look_yaw = look_allowed and look_delta(dx.DeltaX) or 0,
        look_pitch = look_allowed and look_delta(dy.DeltaY) or 0 }
end

return Input
