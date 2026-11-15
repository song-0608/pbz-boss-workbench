-- 用途：集中管理进入、技能按键、逐帧输入和退出；可注入假宿主做测试，不自动启用实验。
local Session = require("session")
local Driver = require("input_driver")
local Runtime = {}
Runtime.__index = Runtime

function Runtime.new(bridge, config, host)
    assert(type(host) == "table" and type(host.on_game_thread) == "function"
        and type(host.bind_key) == "function" and type(host.every_frame) == "function"
        and type(host.cancel_frame) == "function" and type(host.read_input) == "function"
        and type(host.log) == "function", "runtime host incomplete")
    local session = Session.new(bridge, config)
    return setmetatable({ session = session, config = config, host = host, running = false,
        queued = false, frame_handle = nil, last_problem = nil }, Runtime)
end

function Runtime:report(label, success, reason)
    self.host.log(string.format("%s success=%s state=%s reason=%s", label, tostring(success),
        self.session.state, tostring(reason or "")))
end

function Runtime:action(label, fn) -- 用途：所有按键回调排入游戏线程，关闭后积压的回调直接失效。
    if not self.running then return end
    self.host.on_game_thread(function()
        if not self.running then return end
        if self.host.workbench and self.host.workbench:is_open()
            and not label:match('^workbench') and label~='exit' then return end
        local receipt_before=self.session.receipt
        -- 长按/重复退出已恢复的会话时不再发布缺少回读的第二次“恢复成功”。
        if (label=='exit'or label=='menu_exit')and self.session.state=='OFF'and not receipt_before
            and not(self.host.workbench and self.host.workbench:is_open())then return end
        local ok, success, why = pcall(fn)
        if not ok then
            self.session:restore("action exception")
            self:report(label, false, success)
        else self:report(label, success, why) end
        if self.host.status then self.host.status(self.session,true)end
        if label~='exit'and label~='menu_exit'and receipt_before and not self.session.receipt and self.session.state=='OFF'then
            self:report(receipt_before.world_retired and'world_retired'or'auto_exit',true,self.session.last_restore_reason)
        end
    end)
end

function Runtime:workbench_action(label,key,fn)
    if not self.running or self.workbench_action_pending then return end
    if not self.host.after_key_release then return self:action(label,fn)end
    self.workbench_action_pending=true
    self.host.after_key_release(key,function()
        self.workbench_action_pending=false
        if self.running then self:action(label,fn)end
    end)
end

function Runtime:start()
    assert(not self.running, "runtime already started")
    local keys = {}
    local function check_key(key)
        assert(type(key) == "string" and key ~= "" and not keys[key], "missing or duplicate action key")
        keys[key] = true
    end
    check_key(self.config.controls.enter); check_key(self.config.controls.exit)
    if self.config.controls.menu_exit then check_key(self.config.controls.menu_exit)end
    if self.config.controls.cycle_target then check_key(self.config.controls.cycle_target)end
    if self.host.workbench then
        for _,key in ipairs({'INS','UP_ARROW','DOWN_ARROW','RETURN'})do check_key(key)end
        if not self.config.controls.menu_exit then check_key('ESCAPE')end
    end
    for _, definition in pairs(self.config.skills or {}) do
        if definition.verified and not definition.lab_only then check_key(definition.key) end
    end
    if self.config.skill_lab then
        check_key(self.config.skill_lab.next_key);check_key(self.config.skill_lab.cast_key)
        self.lab=require('skill_lab').new(self.session,self.config.skill_lab.slots)
    end
    if self.host.validate_keys then self.host.validate_keys(keys)end
    self.driver = Driver.new(self.session, { read_input = self.host.read_input })
    self.running = true
    self.host.bind_key(self.config.controls.enter, function()
        self:action("enter", function() return self.session:enter() end)
    end)
    self.host.bind_key(self.config.controls.exit, function()
        if self.host.workbench and self.host.workbench:is_open()then
            self:workbench_action('exit',self.config.controls.exit,function()return self.host.workbench:close()end);return
        end
        self:action("exit", function()
            if self.host.workbench and self.host.workbench:is_open()then return self.host.workbench:close()end
            return self.session:restore("user exit")
        end)
    end)
    if self.config.controls.menu_exit then
        self.host.bind_key(self.config.controls.menu_exit,function()
            if self.host.workbench and self.host.workbench:is_open()then
                self:workbench_action('workbench_close',self.config.controls.menu_exit,function()return self.host.workbench:close()end);return
            end
            -- 用途：UE4SS输入独立于原主角屏障；OFF时不重复恢复，允许原游戏自行处理菜单。
            if self.session.state=='OFF'then return end
            self:action('menu_exit',function()return self.session:restore('Esc requested menu exit')end)
        end)
    end
    if self.host.workbench then
        if not self.config.controls.menu_exit then
            self.host.bind_key('ESCAPE',function()
                if self.host.workbench:is_open()then
                    self:workbench_action('workbench_close','ESCAPE',function()return self.host.workbench:close()end)
                end
            end)
        end
        for key,action in pairs({INS='toggle',UP_ARROW='up',DOWN_ARROW='down',RETURN='confirm'})do
            local selected=action
            self.host.bind_key(key,function()
                if selected~='toggle'and not self.host.workbench:is_open()then return end
                local function invoke()
                    local workbench=self.host.workbench
                    if selected=='up'then return workbench:move(-1)
                    elseif selected=='down'then return workbench:move(1)
                    else return workbench[selected](workbench)end
                end
                if selected=='confirm'or(selected=='toggle'and self.host.workbench:is_open())then
                    self:workbench_action('workbench_'..selected,key,invoke)
                else self:action('workbench_'..selected,invoke)end
            end)
        end
    end
    if self.config.controls.cycle_target then
        self.host.bind_key(self.config.controls.cycle_target,function()
            self:action('target_request',function()return self.session:cycle_target()end)
        end)
    end
    for slot, definition in pairs(self.config.skills or {}) do
        if definition.verified and not definition.lab_only then
            local selected = slot
            self.host.bind_key(definition.key, function()
                self:action(selected, function() return self.session:skill(selected) end)
            end)
        end
    end
    if self.lab then
        self.host.bind_key(self.config.skill_lab.next_key,function()
            self:action('lab_next',function()return self.lab:next()end)
        end)
        self.host.bind_key(self.config.skill_lab.cast_key,function()
            self:action('lab_cast',function()return self.lab:cast()end)
        end)
        self.host.log('lab_selected='..self.config.skills[self.lab:selected()].id)
    end
    self.frame_handle = self.host.every_frame(function()
        if not self.running then return end
        if self.session.state~='ACTIVE'and self.session.state~='TRANSITIONING'then
            if self.session.state=='OFF'and self.host.inspect_idle_world then
                local ok,ready=pcall(self.host.inspect_idle_world)
                if not ok then
                    self.host.log('idle_world_check success=false reason='..tostring(ready))
                    self:stop('idle world check failed');return
                end
                if ready~=true then return end
            end
            if self.host.status then self.host.status(self.session,false)end
            return
        end
        local receipt_before=self.session.receipt
        local ok, success, why = pcall(self.driver.step, self.driver)
        if not ok then
            self.session:restore("frame exception")
            success, why = false, success
        end
        if receipt_before and not self.session.receipt and self.session.state=='OFF'then
            self:report(receipt_before.world_retired and'world_retired'or'auto_exit',true,self.session.last_restore_reason)
        end
        -- 用途：失败仅在原因变化时记日志，避免每帧刷屏；恢复失败状态仍然可见。
        if success == false and why ~= self.last_problem then self:report("frame", false, why) end
        self.last_problem = success and nil or why
        if self.host.status then self.host.status(self.session,false)end
        -- 用途：只记录新出现的真实目标回读，不把按F7本身算作切换成功。
        local diagnostic=self.session.diagnostics[#self.session.diagnostics]
        if diagnostic and diagnostic:find('target verified: ',1,true)==1 and diagnostic~=self.last_target then
            self.host.log(diagnostic);self.last_target=diagnostic
        end
    end)
    self:report("ready", true, "input dispatch ready; only verified bindings enabled")
    if self.host.status then self.host.status(self.session,true)end
    return true
end

function Runtime:stop(reason) -- 用途：先让已排队按键失效，再取消帧循环，最后尝试恢复主角。
    self.running = false
    if self.host.release_keys then self.host.release_keys()end
    if self.frame_handle then self.host.cancel_frame(self.frame_handle); self.frame_handle = nil end
    if self.host.workbench then
        local ok,restored,why=pcall(self.host.workbench.shutdown,self.host.workbench)
        if not ok or restored~=true then
            why=ok and why or restored;self:report('workbench_cleanup',false,why);return false,why
        end
    end
    local restored, why = self.session:restore(reason or "runtime stop")
    self:report("stop", restored, why)
    return restored, why
end

return Runtime
