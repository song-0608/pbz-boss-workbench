-- 用途：使用当前PBZ实读声明的FactionComponent和ComponentSocket；不把AI Team字段当作战斗阵营。
local Native={}
function Native.new(g,binding)
    g=g or _G
    assert(binding and binding.binding_verified==true,"combat binding must be verified")
    local function valid(object,label)assert(object and object:IsValid(),label.." missing");return object end
    local utils=valid(g.StaticFindObject('/Script/SGameCombatSystem.Default__FactionUtils'),'faction library')
    return {
        capture_focus=function(boss)
            local controller=valid(boss:GetController(),'boss AI controller')
            local focus=controller:GetFocusActor()
            return controller,focus and focus:IsValid()and focus or nil
        end,
        set_focus=function(controller,target)
            if target then controller:K2_SetFocus(target)else controller:K2_ClearFocus()end
        end,
        faction_component=function(actor)return valid(actor['Faction Component'],'actor faction component')end,
        read_faction=function(component)return component:GetCurrnetFaction().TagName:ToString()end,
        set_faction=function(component,name)
            assert(type(name)=='string'and name~=''and name~='None','nonempty faction tag required')
            component:SetFaction({TagName=g.FName(name)})
        end,
        relation=function(a,b)return utils:GetFactionRelation(a,b)end,
        target_component=function(actor)return valid(actor:GetTargetingComponent(),'target component')end,
        read_target=function(component)
            local socket=component.LockTarget
            local component=socket.Component
            if not(component and component:IsValid())then return nil,socket.SocketName:ToString(),nil end
            return component:GetOwner(),socket.SocketName:ToString(),component
        end,
        set_target=function(component,actor,socket,exact_component)
            -- 用途：恢复用原来的Mesh/Root组件，不把原锁定点悄悄替换成根组件。
            local result=component:SetLockTarget({Component=valid(exact_component or actor.RootComponent,'target component'),SocketName=g.FName(socket or 'None')})
            if binding.diagnostic then
                local c=component.LockTarget.Component
                print('PBZ_COMBAT_TARGET:COMPONENT='..(c and c:IsValid()and c:GetFullName()or'None')..'|has='..tostring(component:HasLockTarget())..'\n')
            end
            return result
        end,
        clear_target=function(component)component:StopLockTarget()end,
        target_actor=function(actor)
            local target=actor:GetLockingTarget(false)
            if binding.diagnostic then
                local hard=actor:GetLockingTarget(true)
                local function name(o)return o and o:IsValid()and o:GetFullName()or'None'end
                print('PBZ_COMBAT_TARGET:QUERY='..name(target)..'|ignore_soft='..name(hard)..'\n')
            end
            return target
        end,
    }
end
return Native
