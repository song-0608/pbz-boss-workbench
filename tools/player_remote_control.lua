-- 用途：保留Boss原AIController，停止其Brain后直接驱动移动与技能，避免NPC目标查询丢失。
-- 主角继续属于原PlayerController；只临时屏蔽主角输入，所有变更登记后可逐项恢复。
local Remote={};Remote.__index=Remote
local function boolean(value,label)
    assert(type(value)=='boolean','remote state unreadable: '..label)
    return value
end
function Remote.new(calls,native,binding)
    assert(binding and binding.binding_verified==true,'verified remote-control declarations required')
    for _,name in ipairs({'ai_started','set_ai_started','ai_tick','set_ai_tick','brain_tick','set_brain_tick','snapshot','block_move','block_look','disable_input','enable_input','input_enabled','move_ignored','look_ignored','rotation','set_rotation','move'})do
        assert(type(native[name])=='function','remote adapter missing '..name)
    end
    if binding.scheduler_trial then assert(type(binding.now)=='function','scheduler clock required')end
    return setmetatable({calls=calls,native=native,scheduler_trial=binding.scheduler_trial==true,now=binding.now},Remote)
end
-- 用途：仅开发装配可签发一次有界Brain调度；不启动外层AI，不改变Controller归属。
function Remote:begin_scheduler(t,id,seconds)
    assert(self.scheduler_trial and(id=='attack_01'or require('subtree_contracts')[id]),'explicit registered subtree scheduler trial required')
    assert(type(seconds)=='number'and seconds>=1 and seconds<=25,'bounded scheduler duration required')
    assert(not t.scheduler and not t.restored and self:verify(t),'idle controlled owner required')
    t.scheduler={id=id,expires_at=self.now()+seconds}
    self.native.set_brain_tick(self.calls:resolve(t.ai),true)
    assert(self:brain_policy_valid(t)and not self:brain_suspended(t),'scheduler enable did not verify')
end
function Remote:brain_policy_valid(t)
    local enabled=self.native.brain_tick(self.calls:resolve(t.ai))
    if t.scheduler then
        -- 用途：叶能力会自行暂停/恢复Brain（右瞬移已实测）；许可不强行重开它的暂停。
        -- 仍真实读取布尔值，逐帧验证其余控制约束，且不延长许可。
        return self.scheduler_trial and not t.restored and self.now()<t.scheduler.expires_at and type(enabled)=='boolean'
    end
    return enabled==false
end
function Remote:end_scheduler(t)
    if not t.scheduler then return true end
    self.native.set_brain_tick(self.calls:resolve(t.ai),false)
    assert(self:brain_suspended(t),'scheduler pause did not verify')
    t.scheduler=nil;return true
end
function Remote:capture(pc,player,boss,ai)
    local initial=self.native.snapshot(pc,player)
    assert(not initial.move_ignored and not initial.look_ignored,'player input already blocked; enter from gameplay')
    local ticket={pc=self.calls:reference(pc),player=self.calls:reference(player),boss=self.calls:reference(boss),
        ai=self.calls:reference(ai),ai_started_initial=self.native.ai_started(ai),ai_tick_initial=self.native.ai_tick(ai),brain_tick_initial=self.native.brain_tick(ai),initial=initial,mutations={}}
    for key,component in pairs({game_ai=ai.SGameAIComponent,brain=ai.BrainComponent})do
        if component and component:IsValid()then ticket[key]=self.calls:reference(component)end
    end
    if self.locomotion then ticket.locomotion=self.locomotion:capture(boss)end
    return ticket
end
function Remote:apply(t)
    local pc,player=self.calls:resolve(t.pc),self.calls:resolve(t.player)
    -- 用途：停止游戏外层SGameAI状态机；只停Brain会被它再次启动。
    t.mutations.ai_started=true;self.native.set_ai_started(self.calls:resolve(t.ai),false)
    -- 用途：游戏会再次StartLogic；暂停Brain的调度，保留AIController的焦点查询与能力系统。
    t.mutations.brain_tick=true;self.native.set_brain_tick(self.calls:resolve(t.ai),false)
    t.mutations.ai_tick=true;self.native.set_ai_tick(self.calls:resolve(t.ai),false)
    t.mutations.move=true;self.native.block_move(pc,true)
    t.mutations.look=true;self.native.block_look(pc,true)
    if t.initial.input_enabled then t.mutations.input=true;self.native.disable_input(player,pc)end
    assert(self:verify(t),'remote control did not verify')
end
function Remote:checks(t)
    local pc,player,boss,ai=self.calls:resolve(t.pc),self.calls:resolve(t.player),self.calls:resolve(t.boss),self.calls:resolve(t.ai)
    local checks={player=self.calls:same(self.calls:pawn(pc),player),boss_controller=self.calls:same(self.calls:controller(boss),ai),
        ai_pawn=self.calls:same(self.calls:pawn(ai),boss),move_block=boolean(self.native.move_ignored(pc),'move input'),look_block=boolean(self.native.look_ignored(pc),'look input'),
        input_block=not t.mutations.input or not boolean(self.native.input_enabled(player),'player input'),
        ai_stopped=not boolean(self.native.ai_started(ai),'outer AI'),
        brain_tick_disabled=not boolean(self.native.brain_tick(ai),'brain tick'),
        ai_tick_disabled=not boolean(self.native.ai_tick(ai),'controller tick')}
    return checks
end
local function verify_checks(self,t,checks)
    for name,value in pairs(checks)do
        if name=='brain_tick_disabled'then value=self:brain_policy_valid(t)end
        if not value then
            -- 用途：只记录首次失效项目，定位异步游戏逻辑，不绕过控制权校验。
            if not t.failure_logged then print('PBZ_REMOTE_VERIFY:FAILED='..name);t.failure_logged=true end
            return false
        end
    end
    return true
end
function Remote:verify(t)
    return verify_checks(self,t,self:checks(t))
end
function Remote:maintain(t)
    -- 用途：实机Attack_01会重开Brain tick；只在其他所有控制/输入约束仍成立时，重申本次已登记的暂停。
    -- 不修补控制器变化、主角输入泄漏或SGameAI重启；这些情况仍交由恢复和监督器处理。
    assert(not t.restored and t.mutations.brain_tick,'active owned brain suspension required')
    local checks=self:checks(t)
    for name,value in pairs(checks)do
        if name~='brain_tick_disabled' and not value then return false,'control invariant changed: '..name end
    end
    if t.scheduler then
        local tick=not checks.brain_tick_disabled
        if t.scheduler.last_tick~=tick then
            t.scheduler.last_tick=tick
            print('PBZ_COMBO_SCHEDULER:STATE='..t.scheduler.id..'|brain_tick='..tostring(tick)..'\n')
        end
        return verify_checks(self,t,checks)
    end
    if not checks.brain_tick_disabled then
        t.brain_reassertions=(t.brain_reassertions or 0)+1
        assert(t.brain_reassertions<=8,'brain scheduling repeatedly contested; stop experiment')
        self.native.set_brain_tick(self.calls:resolve(t.ai),false)
        print('PBZ_REMOTE_MAINTAIN:BRAIN_REASSERT='..t.brain_reassertions..'\n')
        -- A native write can change ownership/input state. Re-read every
        -- invariant after it; never carry this snapshot into a later action.
        return self:verify(t)
    end
    -- This snapshot belongs only to this call, with no intervening native write.
    -- Driver verification and move/look keep their own fresh reads.
    return verify_checks(self,t,checks)
end
function Remote:brain_suspended(t)return not self.native.brain_tick(self.calls:resolve(t.ai))end
function Remote:move(t,x,y,scale)
    assert(self:verify(t),'remote control lost')
    assert(type(x)=='number'and type(y)=='number'and x*x+y*y<=1.000001 and type(scale)=='number'and math.abs(scale)<=1,'bounded direction required')
    if self.locomotion and t.locomotion then self.locomotion:step(t.locomotion,x,y,scale)end
    self.native.move(self.calls:resolve(t.boss),x,y,scale);return true
end
function Remote:look(t,yaw,pitch)
    assert(self:verify(t),'remote control lost')
    local limit=self.locomotion and require('player_3c_tuning').look_limit(self.locomotion)or 10
    assert(type(yaw)=='number'and type(pitch)=='number'and math.abs(yaw)<=limit and math.abs(pitch)<=limit,'bounded look required')
    local pc=self.calls:resolve(t.pc);local r=self.native.rotation(pc)
    self.native.set_rotation(pc,{Pitch=math.max(-60,math.min(20,r.Pitch+pitch)),Yaw=(r.Yaw+yaw+180)%360-180,Roll=0})
    return true
end
function Remote:restore(t,disposed_owner)
    local pc,player=self.calls:resolve(t.pc),self.calls:resolve(t.player);local errors={}
    local function attempt(name,fn)local ok,why=pcall(fn);if ok then t.mutations[name]=nil else errors[#errors+1]=tostring(why)end end
    if t.mutations.move then attempt('move',function()self.native.block_move(pc,false)end)end
    if t.mutations.look then attempt('look',function()self.native.block_look(pc,false)end)end
    if t.mutations.input then attempt('input',function()self.native.enable_input(player,pc)end)end
    local ai_disposed=false
    if disposed_owner then
        attempt('owned disposal',function()
            assert(not self.calls:optional(t.boss)and not self.calls:optional(t.ai),'disposed remote owner/controller remains engine-usable')
            ai_disposed=true
        end)
    end
    if not ai_disposed then
        if t.mutations.brain_tick then attempt('brain_tick',function()self.native.set_brain_tick(self.calls:resolve(t.ai),t.brain_tick_initial)end)end
        if t.mutations.ai_tick then attempt('ai_tick',function()self.native.set_ai_tick(self.calls:resolve(t.ai),t.ai_tick_initial)end)end
        if t.mutations.ai_started then attempt('ai_started',function()self.native.set_ai_started(self.calls:resolve(t.ai),t.ai_started_initial)end)end
    end
    if self.locomotion and t.locomotion then
        attempt('locomotion',function()assert(self.locomotion:restore(t.locomotion,ai_disposed))end)
    end
    attempt('rotation',function()self.native.set_rotation(pc,t.initial.rotation)end)
    assert(#errors==0,table.concat(errors,'; '))
    assert(self.native.move_ignored(pc)==t.initial.move_ignored and self.native.look_ignored(pc)==t.initial.look_ignored
        and (ai_disposed or (self.native.brain_tick(self.calls:resolve(t.ai))==t.brain_tick_initial
        and self.native.ai_tick(self.calls:resolve(t.ai))==t.ai_tick_initial
        and self.native.ai_started(self.calls:resolve(t.ai))==t.ai_started_initial))
        and(t.initial.input_enabled==nil or self.native.input_enabled(player)==t.initial.input_enabled),'player input restoration mismatch')
    t.scheduler=nil;t.restored=true;return true
end
return Remote
