-- 用途：只读生成玩家状态；渲染由当前进程已核对的原生适配器承担，不以显示成功代替战斗回读。
local Hud={};Hud.__index=Hud
function Hud.new(calls,native,config)
    for _,key in ipairs({'now','render','health','name'})do assert(type(native[key])=='function','HUD reader missing '..key)end
    return setmetatable({calls=calls,native=native,config=config,last_at=-math.huge,last_text=nil},Hud)
end
function Hud:update(session,force)
    local now=self.native.now()
    assert(type(now)=='number'and now==now and math.abs(now)<math.huge,'HUD clock invalid')
    if not force and now-self.last_at<1 then return false end
    -- 不解析切图中的旧对象；OFF提示由当前有效PlayerController承载。
    if session.state=='TRANSITIONING'or session.state=='FAULTED'then return false end
    local receipt=session.receipt
    local pc=receipt and self.calls:optional(receipt.player_controller)or self.native.player_controller()
    if not pc then return false end
    local rows={(self.config.boss_display_name or'Boss')..' | '..session.state}
    if receipt and session.state=='ACTIVE'then
        local boss=self.calls:resolve(receipt.boss)
        local hp=self.native.health(boss);assert(type(hp)=='number'and hp==hp and math.abs(hp)<math.huge,'HUD health invalid')
        rows[#rows+1]=string.format('生命 %.0f | %s',hp,session.current_skill and'技能执行中'or'可行动')
        local ref=receipt.combat and receipt.combat.selected_target
        local target=ref and self.calls:optional(ref)
        if target then
            local health=self.native.health(target);assert(type(health)=='number'and health==health and math.abs(health)<math.huge,'HUD target health invalid')
            local condition=health<=0 and'（已死亡）'or''
            if health>0 and self.native.visible then
                local ok,visible=pcall(self.native.visible,boss,target)
                condition=ok and(visible and''or'（视线遮挡）')or'（视线待核对）'
            end
            rows[#rows+1]=string.format('目标：%s%s | 生命 %.0f',self.native.name(target),condition,health)
        else rows[#rows+1]='目标：无有效锁定'end
    end
    local keys=self.config.controls
    rows[#rows+1]=keys.enter..' 接管 | '..keys.cycle_target..' 切换目标 | '..keys.exit..' 恢复主角'
    rows[#rows+1]='WASD 移动 | Shift+技能可用 | Esc 先退出接管'
    if receipt and receipt.player_target_lock then
        rows[#rows+1]='鼠标中键 锁敌开关 | 镜头：'..(receipt.player_target_lock.enabled and'锁定目标'or'自由')
    end
    rows[#rows+1]='Insert Boss 工作台：选择角色与查看适配状态'
    local bindings={}
    for slot,d in pairs(self.config.skills)do
        if d.verified and not d.lab_only then bindings[#bindings+1]={slot=slot,text=d.key..' '..(d.name or d.id)}end
    end
    table.sort(bindings,function(a,b)return a.slot<b.slot end)
    local line={}
    for i,row in ipairs(bindings)do
        line[#line+1]=row.text
        if #line==3 or i==#bindings then rows[#rows+1]=table.concat(line,' | ');line={}end
    end
    local text=table.concat(rows,'\n')
    self.native.render(pc,text,1.3,'PBZBossControl.Status')
    self.last_at=now;self.last_text=text
    return true,text
end
return Hud
