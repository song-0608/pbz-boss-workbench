-- 用途：遥控所需的原生反射调用；无写偏移、无全局Hook，不改控制器归属或角色配置。
local Native={}
function Native.new(binding)
    assert(binding and binding.binding_verified,'remote native contract required')
    return{
        ai_started=function(ai)return ai.SGameAIComponent.bAIStarted end,
        set_ai_started=function(ai,on)if on then ai.SGameAIComponent:StartAI()else ai.SGameAIComponent:StopAI()end end,
        ai_tick=function(ai)return ai:IsActorTickEnabled()end,
        set_ai_tick=function(ai,on)ai:SetActorTickEnabled(on)end,
        brain_tick=function(ai)return ai.BrainComponent:IsComponentTickEnabled()end,
        set_brain_tick=function(ai,on)ai.BrainComponent:SetComponentTickEnabled(on)end,
        snapshot=function(pc,player)local r=pc:GetControlRotation();return{move_ignored=pc:IsMoveInputIgnored(),
            look_ignored=pc:IsLookInputIgnored(),input_enabled=nil,rotation={Pitch=r.Pitch,Yaw=r.Yaw,Roll=r.Roll}}end,
        block_move=function(pc,value)pc:SetIgnoreMoveInput(value)end,
        block_look=function(pc,value)pc:SetIgnoreLookInput(value)end,
        disable_input=function(player,pc)player:DisableInput(pc)end,
        enable_input=function(player,pc)player:EnableInput(pc)end,
        -- 用途：InputEnabled在此构建不是UFunction；未证明原输入栈状态前不调用Disable/EnableInput。
        input_enabled=function(player)return nil end,
        move_ignored=function(pc)return pc:IsMoveInputIgnored()end,
        look_ignored=function(pc)return pc:IsLookInputIgnored()end,
        rotation=function(pc)return pc:GetControlRotation()end,
        set_rotation=function(pc,r)pc:SetControlRotation(r)end,
        move=function(boss,x,y,scale)boss:AddMovementInput({X=x,Y=y,Z=0},scale,false)end,
    }
end
return Native
