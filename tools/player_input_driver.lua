-- 用途：持续输入驱动；把按键状态转换成镜头朝向的移动方向，仅ACTIVE会话可提交输入。
-- 输入采样函数由本构建验证过的UE绑定提供，不用固定坐标传送模拟移动。
local Driver = {}
Driver.__index = Driver

function Driver.new(session, api)
    assert(type(api) == "table" and type(api.read_input) == "function", "input reader required")
    return setmetatable({ session = session, api = api }, Driver)
end

function Driver:step() -- 用途：由游戏线程周期调用；暂停/失焦/恢复中不继续推动Boss。
    local session = self.session
    if session.state=='TRANSITIONING'then session:poll();return false,'world transition input suspended'end
    if session.state ~= "ACTIVE" or not session.receipt then return false, "not active" end
    local ok, why = session:poll()
    if not ok then return false, why end
    if session.bridge.maintain_control then
        local maintained,ready=pcall(session.bridge.maintain_control,session.bridge,session.receipt)
        if not maintained or ready~=true then
            session:restore('control maintenance rejected');return false,'control maintenance rejected'
        end
    end
    -- 用途：即使没按移动键，也要发现控制权被游戏收回，避免继续接受技能输入。
    local verified, controlled = pcall(session.bridge.verify_control, session.bridge, session.receipt)
    if not verified or controlled ~= true then
        session:restore("possession lost")
        return false, "possession lost"
    end
    local read_ok, input = pcall(self.api.read_input, session.receipt)
    if not read_ok or type(input) ~= "table" then
        session:restore("input unreadable")
        return false, "input unreadable"
    end
    if input.paused==true then
        -- 用途：在暂停菜单选择读档/离开前先归还主角；跨World后绝不使用旧恢复凭据。
        session:restore('pause menu opened')
        return false,'pause menu opened'
    end
    if input.allowed ~= true then
        if session.clear_buffered_skill then session:clear_buffered_skill('input suspended')end
        return true, "input suspended"
    end
    local forward = (input.forward and 1 or 0) - (input.backward and 1 or 0)
    local right = (input.right and 1 or 0) - (input.left and 1 or 0)
    local length = math.sqrt(forward * forward + right * right)
    if type(input.yaw_degrees) ~= "number" or input.yaw_degrees ~= input.yaw_degrees
        or math.abs(input.yaw_degrees) > 1000000 then
        session:restore("invalid camera rotation"); return false, "invalid camera rotation"
    end
    local result, reason = pcall(function()
        if session.flush_buffered_skill then assert(session:flush_buffered_skill()==true,'skill input buffer failed')end
        -- Process this frame's look before orienting movement and drawing the arm.
        -- A verified bridge may return its actual post-input yaw (locked or free).
        local yaw, pitch = input.look_yaw or 0, input.look_pitch or 0
        local move_yaw=input.yaw_degrees
        if yaw ~= 0 or pitch ~= 0 then
            local accepted,actual_yaw=session.bridge:look(session.receipt,yaw,pitch)
            assert(accepted==true,'look rejected')
            if actual_yaw~=nil then
                assert(type(actual_yaw)=='number'and actual_yaw==actual_yaw
                    and math.abs(actual_yaw)<=1000000,'post-input yaw unreadable')
                move_yaw=actual_yaw
            end
        end
        if session.bridge.update_camera then
            assert(session.bridge:update_camera(session.receipt)==true,'camera update failed')
        end
        if length > 0 and not session.current_skill then
            forward, right = forward / length, right / length
            local radians = math.rad(move_yaw)
            local x = math.cos(radians) * forward - math.sin(radians) * right
            local y = math.sin(radians) * forward + math.cos(radians) * right
            assert(session.bridge:move(session.receipt, x, y, 1), "move rejected")
        end
    end)
    if not result then session:restore("movement or look failed"); return false, tostring(reason) end
    return true
end

return Driver
