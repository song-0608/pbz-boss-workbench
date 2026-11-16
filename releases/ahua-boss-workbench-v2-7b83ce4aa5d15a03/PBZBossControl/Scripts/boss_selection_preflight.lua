-- Read-only selection check. Keep the current assembly until a new location is suitable.
local Check={}
local NEED_SPACE='烟千岁需要周围至少9米的同层开阔地面。按 Esc 返回，移动到开阔处后再选择。'
function Check.verify(g,binding,pc,player,id,valid,build)
    if id~='073_yanqiansui' then return true end
    assert(valid(pc)and valid(player)and valid(pc.Pawn)
        and pc.Pawn:GetAddress()==player:GetAddress(),'current restored player required')
    local profile=require('boss_catalog').profile(id)
    assert(profile.identity_verified and profile.exe_sha256==build,'selection identity required')
    local function verified_class(p)
        assert(p.identity_verified and p.exe_sha256==build,'same-build target required')
        local cls=g.LoadAsset(p.class_path);assert(valid(cls),'selection class unavailable')
        local defaults=cls:GetCDO();assert(valid(defaults),'selection defaults unavailable')
        local config=defaults['Actor Config'];assert(valid(config),'selection config unavailable')
        assert(config:GetFullName():match('^[^ ]+ (.+)$')==p.config_path
            and config:GetCharacterName():ToString()==p.display_name,'selection identity changed')
        return defaults.CapsuleComponent
    end
    local boss=verified_class(profile)
    local target=verified_class(require(assert(profile.training_target_profile)))
    local p=player.CapsuleComponent
    assert(valid(p)and valid(boss)and valid(target),'selection capsule unavailable')
    local project=require('ue_arena_layout').new(g,binding,pc)
    local plan=require('yanqiansui_arena_clearance').choose(project,
        player:K2_GetActorLocation(),player:GetActorForwardVector(),
        p.CapsuleHalfHeight,boss.CapsuleHalfHeight,boss.CapsuleRadius,1,nil,
        target.CapsuleHalfHeight,target.CapsuleRadius)
    if not plan then return false,NEED_SPACE end
    assert(plan.clearance_cm==900 and plan.clearance_samples==24 and plan.queries_used<=192,
        'bounded selection clearance required')
    -- This is only a preflight. The actual new assembly must check terrain again.
    return true
end
return Check
