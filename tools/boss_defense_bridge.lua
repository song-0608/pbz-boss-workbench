-- Explicit development adapter for a role's unique, already granted NPC stance.
-- No player skeleton transplant, new grants, timer edits or resource/cooldown bypass.
local Adapter={}
function Adapter.attach(bridge,receipt,contract,clock,input_allowed,native_sample)
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
    local function check_owner()
        bridge:check(receipt)
        assert(bridge.active_receipt==receipt,'defense receipt no longer active')
    end
    local function current()
        check_owner()
        local spec,active,asc=bridge:spec(receipt,contract)
        assert(spec.Ability:IsA('/PBZDeflectSystem/Abilities/BP_StanceAction_Base_NPC.BP_StanceAction_Base_NPC_C'),
            'native stance ancestry changed')
        return spec,active,asc
    end
    local defense=require('boss_defense_input').new({
        context=function(input)
            check_owner()
            local now,permitted
            if native_sample and input then
                now,permitted=input.now,input.allowed==true
            else
                now,permitted=clock(),input_allowed()==true
            end
            return {now=now,identity=identity,same_world=true,
                allowed=receipt.input_enabled and permitted and bridge:verify_control(receipt)==true,
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
