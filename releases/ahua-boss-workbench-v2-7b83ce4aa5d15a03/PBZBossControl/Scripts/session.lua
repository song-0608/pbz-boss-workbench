-- Boss控制会话：这是独立Lua逻辑，游戏读写只能经过另行验证的bridge。
-- 本文件没有猜测PBZ函数、类名、偏移，也不会直接读写UObject或存档。
local Session = {}
Session.__index = Session

local methods = { "context", "capture", "take_control", "verify_control", "can_start_skill",
    "start_skill", "is_skill_finished", "cancel_skills", "restore", "verify_restored" }

local function call(bridge, name, ...) -- 用途：每次引擎调用都截获Lua异常，返回可诊断结果。
    local result = table.pack(pcall(bridge[name], bridge, ...))
    if not result[1] then return false, tostring(result[2]) end
    return true, table.unpack(result, 2, result.n)
end

function Session.new(bridge, config) -- 用途：检查桥接契约，不把缺少真实实现的接口当作可用。
    assert(type(bridge) == "table" and type(config) == "table", "bridge/config required")
    for _, name in ipairs(methods) do assert(type(bridge[name]) == "function", "bridge missing " .. name) end
    return setmetatable({ bridge = bridge, config = config, state = "OFF", receipt = nil,
        world_id = nil, current_skill = nil, diagnostics = {} }, Session)
end

function Session:record(message) -- 用途：保存少量诊断，调用方可输出到UE4SS日志。
    self.diagnostics[#self.diagnostics + 1] = tostring(message)
    if #self.diagnostics > 64 then table.remove(self.diagnostics, 1) end
end

function Session:context() -- 用途：每次修改前核对离线隔离、构建和World；不接受失效对象。
    local ok, context = call(self.bridge, "context")
    if not ok or type(context) ~= "table" then return nil, "context unreadable" end
    if context.isolated ~= true or context.offline ~= true then return nil, "offline isolation not attested" end
    if context.exe_sha256 ~= self.config.expected_exe_sha256 then return nil, "game build mismatch" end
    if type(context.world_id) ~= "string" or context.world_id == "" then return nil, "missing world identity" end
    if self.world_id and context.world_id ~= self.world_id then return nil, "world changed; stale receipt rejected" end
    return context
end

function Session:world_boundary()
    if not self.receipt or type(self.bridge.world_boundary)~='function'then return 'same'end
    local ok,status,why,now=call(self.bridge,'world_boundary',self.receipt)
    if not ok or (status~='same'and status~='pending'and status~='retired')then
        self.state='FAULTED';self:record('world boundary unreadable: '..tostring(status));return 'faulted',tostring(status)
    end
    if status=='same'then
        if self.state=='TRANSITIONING'then self.state='FAULTED';self:record('world transition returned to old objects');return 'faulted'end
        return 'same'
    end
    if status=='retired'then
        self.retired_world_id=self.world_id
        self.receipt,self.world_id,self.current_skill,self.pending_target,self.world_wait_at=nil,nil,nil,nil,nil
        self.state='OFF';self.last_restore_reason='old world and modified participants disposed'
        self:record('world retired: '..tostring(self.retired_world_id));return 'retired'
    end
    if type(now)~='number'or now~=now or math.abs(now)==math.huge then self.state='FAULTED';self:record('world transition clock unreadable');return 'faulted'end
    self.world_wait_at=self.world_wait_at or now
    if now-self.world_wait_at>15 then self.state='FAULTED';self:record('world retirement timed out: '..tostring(why));return 'faulted'end
    self.state='TRANSITIONING';return 'pending'
end

function Session:restore(reason) -- 用途：撤销技能和接管，并回读确认；失败保留FAULTED而不是假报恢复。
    if not self.receipt then self.state = "OFF"; return true end
    local boundary=self:world_boundary()
    if boundary=='retired'then return true end
    if boundary~='same'then return false,'world transition pending or unverified'end
    local context, why = self:context()
    if not context then self.state = "FAULTED"; self:record(why); return false, why end
    self.state = "RESTORING"
    -- 用途：即使中断招式失败仍尝试恢复控制，但最终必须两个操作和回读都通过。
    local cancel_ok, cancel_result = call(self.bridge, "cancel_skills", self.receipt)
    local restore_ok, restore_result = call(self.bridge, "restore", self.receipt)
    local read_ok, restored = call(self.bridge, "verify_restored", self.receipt)
    if not cancel_ok or cancel_result ~= true or not restore_ok or restore_result ~= true or not read_ok or restored ~= true then
        self.state = "FAULTED"
        self:record("restore failed: " .. tostring(reason))
        return false, "restore not verified"
    end
    self.receipt, self.world_id, self.current_skill, self.pending_target = nil, nil, nil, nil
    self.state = "OFF"
    self.last_restore_reason=tostring(reason)
    self:record("restored: " .. tostring(reason))
    return true
end

function Session:health_guard()
    if type(self.bridge.control_health)~='function'then return true end
    local ok,alive,reason=call(self.bridge,'control_health',self.receipt)
    if ok and alive==true then return true end
    local why=ok and(reason or 'boss no longer alive')or 'boss health unreadable'
    self:restore(why)
    return false,why
end

function Session:enter() -- 用途：先保存恢复凭据，再暂停AI/接管，任何部分失败都走恢复路径。
    if self.state ~= "OFF" then return false, "session is not OFF" end
    local context, why = self:context()
    if not context then self:record(why); return false, why end
    if context.boss_available ~= true then return false, "no verified unlocked boss instance" end
    local ok, receipt = call(self.bridge, "capture")
    if not ok or type(receipt) ~= "table" then
        local reason="capture failed before mutation: "..tostring(receipt)
        self:record(reason)
        return false,reason
    end
    -- 用途：凭据只能存逻辑ID/状态快照；bridge每次都要重查实例，不跨场景持有旧对象。
    self.receipt, self.world_id, self.state = receipt, context.world_id, "PREPARING"
    local takeover_ok, taken = call(self.bridge, "take_control", receipt)
    local verify_ok, controlled = false, false
    if takeover_ok and taken == true then verify_ok, controlled = call(self.bridge, "verify_control", receipt) end
    if not takeover_ok or taken ~= true or not verify_ok or controlled ~= true then
        local restored = self:restore("takeover failed")
        return false, restored and "takeover failed; restored" or "takeover failed; restoration unverified"
    end
    self.state = "ACTIVE"
    self:record("control verified")
    return true
end

function Session:skill(slot) -- 用途：只执行已验证技能，保留原游戏资源、冷却和状态限制。
    if self.state ~= "ACTIVE" then return false, "not controlling a boss" end
    if self:world_boundary()~='same'then return false,'world transition; skill blocked'end
    if self.current_skill then return false, "a skill is still running" end
    if self.pending_target then return false,"target change awaiting game readback" end
    local definition = (self.config.skills or {})[slot]
    if not definition or definition.verified ~= true or type(definition.id) ~= "string" or definition.id == "" then
        return false, "skill has no verified game binding"
    end
    local context, why = self:context()
    if not context then self.state = "FAULTED"; self:record(why); return false, why end
    local alive,health_reason=self:health_guard();if not alive then return false,health_reason end
    local can_ok, allowed, rejection = call(self.bridge, "can_start_skill", self.receipt, definition.id)
    if not can_ok or allowed ~= true then return false, rejection or "game state/cooldown rejected skill" end
    local ok, token = call(self.bridge, "start_skill", self.receipt, definition.id)
    if ok and token == false then
        self:record("game rejected activation: " .. definition.id)
        return false, "game rejected activation; possession retained"
    end
    if not ok or type(token) ~= "string" or token == "" then
        self:restore("skill start failed")
        return false, "skill failed; inspect restoration state"
    end
    self.current_skill = token
    self:record("skill started: " .. definition.id)
    return true
end

function Session:cycle_target() -- 用途：只在没有招式运行时切目标；按键返回“请求”，确认由逐帧回读完成。
    if self.state~='ACTIVE'then return false,'not controlling a boss' end
    if self:world_boundary()~='same'then return false,'world transition; target blocked'end
    if self.current_skill then return false,'finish current skill before changing target' end
    if self.pending_target then return false,'target change already pending' end
    if type(self.bridge.cycle_target)~='function'then return false,'target selection unavailable' end
    local context,why=self:context();if not context then self.state='FAULTED';return false,why end
    local ok,name,reason=call(self.bridge,'cycle_target',self.receipt)
    if not ok then self:restore('target request failed');return false,name end
    if name==false then return false,reason end
    if type(name)~='string'or name==''then self:restore('invalid target request receipt');return false,'invalid target request receipt'end
    self.pending_target=true;self:record('target requested: '..tostring(name))
    return true,'requested; awaiting readback: '..tostring(name)
end

function Session:poll() -- 用途：由验证过的游戏线程回调检查技能结束，不用猜动画播放时间。
    if self.state=='ACTIVE'or self.state=='TRANSITIONING'then
        local boundary,detail=self:world_boundary()
        if boundary~='same'then return false,'world transition: '..boundary..'|'..tostring(detail or'')end
    end
    if self.state ~= "ACTIVE" then return false, "not active" end
    local context, why = self:context()
    if not context then self.state = "FAULTED"; self:record(why); return false, why end
    local alive,health_reason=self:health_guard();if not alive then return false,health_reason end
    if self.pending_target then
        local ok,status,name=call(self.bridge,'poll_target_change',self.receipt)
        if ok and status=='verified'then
            self.pending_target=nil;self:record('target verified: '..tostring(name))
            return true,'target verified: '..tostring(name)
        elseif not ok or status~='pending'then
            local cancelled,result=call(self.bridge,'cancel_target_change',self.receipt)
            self.pending_target=nil
            if not cancelled or result~=true then self:restore('target rollback failed')end
            return false,'target change rejected: '..tostring(name or status)
        end
    end
    if not self.current_skill then return true end
    local ok, finished = call(self.bridge, "is_skill_finished", self.receipt, self.current_skill)
    if not ok or type(finished) ~= "boolean" then
        self:restore("skill completion unreadable")
        return false, "skill completion unreadable"
    end
    if finished then self.current_skill = nil end
    return true
end

return Session
