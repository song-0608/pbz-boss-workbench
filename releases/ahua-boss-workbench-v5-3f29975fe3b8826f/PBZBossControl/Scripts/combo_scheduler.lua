-- 用途：开发专用Attack_01调度实验。真实回读父/子能力；默认玩家入口仍隔离。
local Trial={};Trial.__index=Trial
local contracts=require('subtree_contracts')
Trial.class='/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/New/GA_AHua_Attack_01.GA_AHua_Attack_01_C'
Trial.tree='/PBZCombatAsset/ActorData/Mobs/042_AHua/BehaviorTree/GuiTouDao/BT_AHua_TeleportAttack_01.BT_AHua_TeleportAttack_01'
-- 用途：来自精确子树的AbilityToActivate引用；仅允许引擎自己授予这些已反射叶类，Mod不调用GiveAbility。
Trial.native_leaves={
    ['/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/GA_AHua_Skill_03.GA_AHua_Skill_03_C']=true,
    ['/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/New/GA_AHua_CA_01_GEx_Teleport_RedEye.GA_AHua_CA_01_GEx_Teleport_RedEye_C']=true,
    ['/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/New/GA_AHua_Skill_05_Hard.GA_AHua_Skill_05_Hard_C']=true,
    ['/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/New/GA_AHua_Skill_08.GA_AHua_Skill_08_C']=true,
    ['/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/New/GA_AHua_Teleport_Left.GA_AHua_Teleport_Left_C']=true,
    ['/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/New/GA_AHua_Teleport_Right.GA_AHua_Teleport_Right_C']=true,
}
function Trial.new(calls,remote,cancel,log)
    assert(remote.scheduler_trial and type(cancel)=='function'and type(log)=='function','explicit scheduler assembly required')
    return setmetatable({calls=calls,remote=remote,cancel=cancel,log=log},Trial)
end
local function path(object)return assert(object:GetClass():GetFullName():match('^[^ ]+ (.+)$'))end
function Trial:snapshot(receipt)
    local items=self.calls:resolve(receipt.asc).ActivatableAbilities.Items
    local count=items:GetArrayNum();assert(math.type(count)=='integer'and count>=1 and count<=512,'bounded granted ability list required')
    local result={}
    for i=1,count do
        assert(items:GetArrayNum()==count,'grant list changed during scheduler experiment')
        local spec=items[i];local ability=spec.Ability
        if ability and ability:IsValid()then
            local key=path(ability);assert(not result[key],'ambiguous duplicate grant')
            local active=spec.ActiveCount;assert(math.type(active)=='integer'and active>=0 and active<=255,'unreadable ability activity')
            result[key]={spec=spec,active=active,address=ability:GetAddress()}
        end
    end
    return result
end
function Trial:begin(receipt,id,definition)
    local contract=id=='attack_01'and {class=Trial.class,trees={[Trial.tree]=true},leaves=Trial.native_leaves}or contracts[id]
    if not contract then return false end
    assert(not receipt.combo_trial and receipt.remote_control and definition.class_path==contract.class,'exact registered subtree parent required')
    local baseline=self:snapshot(receipt);local parent=assert(baseline[contract.class],'subtree parent is not granted')
    assert(parent.active==0,'parent already active')
    local ability=parent.spec.Ability
    assert(ability:IsA('/Script/SGameAI.RunSubtreeAbility'),'unexpected parent scheduler type')
    local trees,seen=0,{}
    ability.ComboTreeWithWeight:ForEach(function(key,value)
        trees=trees+1;local tree=key:get()
        assert(tree and tree:IsValid(),'exact known subtree required')
        local path=tree:GetFullName():match('^BehaviorTree (.+)$');local expected=contract.trees[path]
        assert(expected and not seen[path]and value:get()>0 and(expected==true or value:get()==expected),'exact known subtree required')
        seen[path]=true
    end)
    local expected_count=0;for _ in pairs(contract.trees)do expected_count=expected_count+1 end
    assert(trees==expected_count,'ambiguous combo subtree')
    for _,row in pairs(baseline)do row.spec=nil end -- 仅保留类/地址/计数，不把旧Spec跨帧留在恢复凭据中。
    -- 用途：登记在首次调度写操作之前；激活抛异常也保留取消责任。
    receipt.combo_trial={baseline=baseline,observed={},id=id,parent_class=contract.class,native_leaves=contract.leaves}
    self.remote:begin_scheduler(receipt.remote_control,id,25)
    self.log('COMBO_SCHEDULER_BEGIN',id..'|brain_tick=true|outer_ai=false|ai_tick=false|limit=25')
    return true
end
function Trial:changed(receipt)
    local ticket=assert(receipt.combo_trial,'scheduler receipt required');local current=self:snapshot(receipt);local changed={}
    ticket.child_active=false
    for key,row in pairs(current)do
        local before=ticket.baseline[key]
        if not before then
            self.log('COMBO_NATIVE_GRANT',key..'|active='..row.active..'|known_leaf='..tostring(ticket.native_leaves[key]==true))
            assert(ticket.native_leaves[key]==true,'foreign native grant during scheduler experiment: '..key)
            before={active=0,address=row.address,native_leaf=true};ticket.baseline[key]=before
        end
        assert(before.address==row.address,'grant identity changed')
        assert(row.active>=before.active,'preexisting activity changed during scheduler experiment')
        if row.active>before.active then
            assert(key==ticket.parent_class or ticket.native_leaves[key]==true,
                'foreign activity during registered subtree: '..key)
            if key~=ticket.parent_class then ticket.child_active=true end
            changed[#changed+1]=row
            if not ticket.observed[key]then ticket.observed[key]=true;self.log('COMBO_OBSERVED_ACTIVE',key..'|active='..row.active..'|baseline='..before.active)end
        end
    end
    for key in pairs(ticket.baseline)do assert(current[key],'grant disappeared during scheduler experiment')end
    return changed
end
function Trial:poll(receipt,parent_active)
    if not receipt.combo_trial then return parent_active==0 end
    local changed=self:changed(receipt)
    if parent_active>0 or #changed>0 or not receipt.combo_trial.observed[receipt.combo_trial.parent_class]then return false end
    self.remote:end_scheduler(receipt.remote_control)
    self.log('COMBO_SCHEDULER_END','natural=true|all_grants_at_baseline=true|brain_tick=false')
    receipt.combo_trial=nil;return true
end
function Trial:cancel_all(receipt)
    if not receipt.combo_trial then return true end
    -- 用途：先暂停树，再取消本次增加的活动；不清空原有被动、不强写计数或EndAbility。
    self.remote:end_scheduler(receipt.remote_control)
    local changed=self:changed(receipt)
    local parent_class=receipt.combo_trial.parent_class
    -- 用途：先中断叶能力，再请求原生StopLogic使宿主树发送真实结束；不手调OnHostTreeFinished。
    table.sort(changed,function(a,b)return path(a.spec.Ability)~=parent_class and path(b.spec.Ability)==parent_class end)
    local ok=true
    for _,row in ipairs(changed)do
        local before=receipt.combo_trial.baseline[path(row.spec.Ability)]
        if before.active~=0 then ok=false
        elseif row.spec.ActiveCount>0 and path(row.spec.Ability)~=parent_class then
            local cancelled,result=pcall(self.cancel,row.spec,{class_path=path(row.spec.Ability),cancel_binding_verified=true,cancel_function='K2_CancelAbility',active_count_field='ActiveCount'})
            if not cancelled or result~=true then ok=false end
        end
    end
    local brain=self.calls:resolve(receipt.remote_control.brain)
    self.log('COMBO_TREE_STOP','running_before='..tostring(brain:IsRunning()))
    self.calls:stop_brain(brain)
    local parent=assert(self:snapshot(receipt)[parent_class])
    if parent.active>0 then
        local cancelled,result=pcall(self.cancel,parent.spec,{class_path=parent_class,cancel_binding_verified=true,cancel_function='K2_CancelAbility',active_count_field='ActiveCount'})
        if not cancelled or result~=true then ok=false end
    end
    -- 用途：取消可能重开Brain；再次暂停并读取所有授予，不以父能力归零代替完整取消。
    self.remote.native.set_brain_tick(self.calls:resolve(receipt.remote_control.ai),false)
    local remaining=self:changed(receipt)
    assert(self.remote:brain_suspended(receipt.remote_control),'cancel reopened scheduler')
    assert(ok and #remaining==0,'combo parent or child cancellation unverified')
    self.log('COMBO_SCHEDULER_END','cancelled=true|all_grants_at_baseline=true|brain_tick=false')
    receipt.combo_trial=nil;return true
end
return Trial
