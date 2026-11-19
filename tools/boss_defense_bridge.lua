-- Explicit development adapter for a role's unique, already granted NPC stance.
-- No player skeleton transplant, new grants, timer edits or resource/cooldown bypass.
local Adapter={}
function Adapter.attach(bridge,receipt,contract,clock,input_allowed)
    assert(not receipt.native_defense,'native defense already attached; release before replacement')
    assert(contract and contract.developer_only==true and contract.declaration_verified==true
        and contract.class_path and contract.active_count_field=='ActiveCount'
        and contract.cancel_binding_verified==true and contract.cancel_function=='K2_CancelAbility',
        'reviewed NPC stance and cancellation contract required')
    assert(type(clock)=='function'and type(input_allowed)=='function','live clock and input permission required')
    bridge:check(receipt)
    local spec,active=bridge:spec(receipt,contract)
    assert(active==0 and spec.Ability:IsA('/PBZDeflectSystem/Abilities/BP_StanceAction_Base_NPC.BP_StanceAction_Base_NPC_C'),
        'one idle native NPC stance grant required')
    local identity=receipt.world_id..'|'..receipt.boss.name..'|'..tostring(receipt.boss.address)
    local function current()
        bridge:check(receipt)
        assert(bridge.active_receipt==receipt,'defense receipt no longer active')
        local spec,active,asc=bridge:spec(receipt,contract)
        assert(spec.Ability:IsA('/PBZDeflectSystem/Abilities/BP_StanceAction_Base_NPC.BP_StanceAction_Base_NPC_C'),
            'native stance ancestry changed')
        return spec,active,asc
    end
    local defense=require('boss_defense_input').new({
        context=function()
            current()
            return {now=clock(),identity=identity,same_world=true,
                allowed=receipt.input_enabled and input_allowed()==true and bridge:verify_control(receipt)==true,
                busy=receipt.target_transition~=nil or receipt.combat_action_active==true}
        end,
        active=function()local _,count=current();return count>0 end,
        activate=function()
            local spec,active,asc=current();assert(active==0,'native stance is already active')
            return bridge.calls:activate(asc,spec.Ability:GetClass())
        end,
        -- NPC stance has no player KeyUp event. Its native ability cancellation
        -- owns frame listeners, timeline, animation layers and walking modifiers.
        release=function()current();return true end,
        cancel=function()
            local spec,active=current()
            return active==0 or bridge.calls:cancel(spec,contract)==true
        end,
    })
    receipt.native_defense=defense
    return defense
end
return Adapter
