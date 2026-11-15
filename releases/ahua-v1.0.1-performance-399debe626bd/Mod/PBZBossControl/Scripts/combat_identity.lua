-- 用途：事务化保存/切换/恢复Boss阵营和战斗目标；不修改全局关系表、角色配置资产或存档。
local Combat={};Combat.__index=Combat

function Combat.new(calls,native,binding)
    assert(binding and binding.binding_verified==true,"verified faction/target contracts required")
    for _,name in ipairs({'faction_component','read_faction','set_faction','relation','target_component','read_target','set_target','clear_target','target_actor'})do
        assert(type(native[name])=='function',"missing combat adapter: "..name)
    end
    return setmetatable({calls=calls,native=native,binding=binding},Combat)
end

function Combat:capture(player,boss)
    local component=self.native.faction_component(boss)
    local targeting=self.native.target_component(boss)
    local target,socket,original_component=self.native.read_target(targeting)
    local ticket={component=self.calls:reference(component),targeting=self.calls:reference(targeting),
        original=self.native.read_faction(component),desired=self.native.read_faction(self.native.faction_component(player)),
        original_target=target and self.calls:reference(target)or nil,original_socket=socket,
        original_component=original_component and self.calls:reference(original_component)or nil,
        player=self.calls:reference(player),boss=self.calls:reference(boss),mutated=false}
    if self.binding.ai_focus_bridge then
        local controller,focus=self.native.capture_focus(boss)
        ticket.focus_controller=self.calls:reference(controller)
        ticket.original_focus=focus and self.calls:reference(focus)or nil
    end
    return ticket
end

function Combat:apply(ticket)
    ticket.mutated=true -- 用途：调用前登记恢复责任，原生函数部分成功或抛错仍会恢复。
    if ticket.focus_controller then self.native.set_focus(self.calls:resolve(ticket.focus_controller),nil)end
    self.native.clear_target(self.calls:resolve(ticket.targeting))
    self.native.set_faction(self.calls:resolve(ticket.component),ticket.desired)
    assert(self:verify(ticket),"player faction switch did not verify")
    return true
end

function Combat:verify(ticket)
    local boss,player=self.calls:resolve(ticket.boss),self.calls:resolve(ticket.player)
    return self.native.read_faction(self.calls:resolve(ticket.component))==ticket.desired
        and self.native.relation(boss,player)==self.binding.friendly
        and self.native.relation(player,boss)==self.binding.friendly
end

function Combat:request_target(ticket,target,socket)
    assert(self:verify(ticket),"faction not ready for target selection")
    local boss,player=self.calls:resolve(ticket.boss),self.calls:resolve(ticket.player)
    assert(not self.calls:same(target,boss)and not self.calls:same(target,player),"self or saved player cannot be a target")
    local world,other=self.calls:world(boss),self.calls:world(target)
    assert(world.name==other.name and world.address==other.address,"cross-world target rejected")
    assert(self.native.relation(boss,target)==self.binding.hostile,"target is not hostile")
    local targeting=self.calls:resolve(ticket.targeting)
    assert(self.native.set_target(targeting,target,socket)==true,"native target lock rejected")
    if ticket.focus_controller then self.native.set_focus(self.calls:resolve(ticket.focus_controller),target)end
    ticket.selected_target=self.calls:reference(target)
    return true
end

function Combat:set_target(ticket,target,socket)
    self:request_target(ticket,target,socket)
    assert(self:verify_target(ticket),'ability target query differs from selected target')
    return true
end

function Combat:verify_target(ticket)
    if not ticket.selected_target then return false end
    local target=self.calls:resolve(ticket.selected_target)
    local boss=self.calls:resolve(ticket.boss)
    return self:verify(ticket)and self.native.relation(boss,target)==self.binding.hostile
        and self.calls:same(self.native.target_actor(boss),target)
end

function Combat:restore(ticket,disposed_owner)
    if not ticket or not ticket.mutated then return true end
    if disposed_owner then
        assert(not self.calls:optional(ticket.boss)and not self.calls:optional(ticket.component)
            and not self.calls:optional(ticket.targeting),'disposed combat components remain engine-usable')
        if ticket.focus_controller then
            assert(not self.calls:optional(ticket.focus_controller),'disposed focus controller remains engine-usable')
        end
        ticket.restored=true;ticket.owner_disposed=true;return true
    end
    local targeting=self.calls:resolve(ticket.targeting)
    local failures={}
    local function attempt(fn)local ok,why=pcall(fn);if not ok then failures[#failures+1]=tostring(why)end end
    -- 用途：目标清除失败仍尝试恢复阵营；每项失败独立记录，禁止把部分恢复报告为成功。
    attempt(function()self.native.clear_target(targeting)end)
    attempt(function()self.native.set_faction(self.calls:resolve(ticket.component),ticket.original)end)
    if ticket.focus_controller then
        attempt(function()self.native.set_focus(self.calls:resolve(ticket.focus_controller),
            ticket.original_focus and self.calls:resolve(ticket.original_focus)or nil)end)
    end
    attempt(function()
        if ticket.original_target then
            assert(ticket.original_component,"original target component snapshot missing")
            assert(self.native.set_target(targeting,self.calls:resolve(ticket.original_target),ticket.original_socket,
                self.calls:resolve(ticket.original_component))==true,"original target restore rejected")
        end
        local target,socket,component=self.native.read_target(targeting)
        if ticket.original_target then
            assert(self.calls:same(target,self.calls:resolve(ticket.original_target))
                and self.calls:same(component,self.calls:resolve(ticket.original_component))
                and socket==ticket.original_socket,'original target/component/socket readback mismatch')
        else assert(not target and not component,'original empty target not restored')end
    end)
    attempt(function()assert(self.native.read_faction(self.calls:resolve(ticket.component))==ticket.original,"original faction restore failed")end)
    assert(#failures==0,table.concat(failures,'; '))
    ticket.restored=true
    return true
end

return Combat
