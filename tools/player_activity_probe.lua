-- Keep the per-frame original-player leakage audit, but do not resolve or
-- inspect UObject abilities whose native spec is inactive. No frame cache.
local Probe={}
function Probe.snapshot(player,usable)
    local found={}
    local specs=player.AbilitySystemComponent.ActivatableAbilities.Items
    local size=specs:GetArrayNum();assert(size<=512,'player ability bound')
    for i=1,size do
        local spec=specs[i]
        if spec.ActiveCount>0 then
            local ability=spec.Ability
            if usable(ability)then found[ability:GetClass():GetFullName()]=true end
        end
    end
    return found
end
return Probe
