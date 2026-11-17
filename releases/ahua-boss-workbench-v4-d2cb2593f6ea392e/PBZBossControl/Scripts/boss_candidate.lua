-- Explicit developer candidates. This module never registers a playable Boss.
local Candidate={}
local definitions={
    ['057_wanjun']={id='057_wanjun',display_name='巨锤客：万钧',
        class_path='/PBZCombatAsset/ActorData/Mobs/057_WanJun/BP_Monster_WanJun_JinGua.BP_Monster_WanJun_JinGua_C',
        config_path='/PBZCombatAsset/ActorData/Mobs/057_WanJun/ActorData/ActorC_WanJun_JinGua.ActorC_WanJun_JinGua',
        ability_root='/PBZCombatAsset/ActorData/Mobs/057_WanJun/Ability/JinGua/Abilities/',
        leaves={'GA_WanJun_HeavyAttack_01','GA_WanJun_DodgeAttack_L','GA_WanJun_DodgeAttack_R','GA_WanJun_Attack_L'}},
}
local function exact(object,path)
    assert(object and object:IsValid() and object:GetFullName():match('^[^ ]+ (.+)$')==path,'candidate asset identity mismatch: '..path)
end

function Candidate.prepare(id,grant,load,log)
    local row=assert(definitions[id],'unregistered developer Boss candidate')
    assert(grant.boss_candidate==id and type(grant.identity_receipt_sha256)=='string'
        and #grant.identity_receipt_sha256==64,'independent candidate grant required')
    local cls=load(row.class_path);exact(cls,row.class_path)
    assert(cls:IsA('/Script/CoreUObject.Class'),'candidate class metadata required')
    local config=cls:GetCDO()['Actor Config'];exact(config,row.config_path)
    assert(config:GetCharacterName():ToString()==row.display_name,'candidate display name changed')
    local profile={id=id,display_name=row.display_name,exe_sha256=grant.exe_sha256,
        identity_verified=true,identity_evidence=grant.identity_receipt_sha256,
        class_path=row.class_path,config_path=row.config_path,skill_timeout_seconds=30,
        control_verified=false,playable=false,training_target_profile='profiles.ahua',
        input={input_verified=false,mouse_scale=0.1},
        camera={binding_verified=false,distance=650,pivot_height=100,shoulder_offset=45,probe_size=14,
            fov=90,min_pitch=-60,max_pitch=20,keep_relative=0,keep_world=1,snap=2,camera_channel=4,
            spawn_collision=3,spawn_scale=0},skills={}}
    local ids={'skill_01','heavy_01','skill_02','dash'}
    local next_id=1
    for _,name in ipairs(row.leaves)do
        local path=row.ability_root..name..'.'..name..'_C'
        local ok,ability=pcall(load,path)
        if ok and ability and ability:IsValid()then
            exact(ability,path)
            local default=ability:GetCDO()
            assert(default and default:IsValid(),'candidate ability CDO unavailable')
            if default:IsA('/Script/GameplayAbilities.GameplayAbility')and not default:IsA('/Script/SGameAI.RunSubtreeAbility')then
                local key=ids[next_id];next_id=next_id+1
                profile.skills[key]={name=name,class_path=path,binding_verified=false,active_count_field='ActiveCount',
                    requires_target=true,cancel_binding_verified=false,cancel_function='K2_CancelAbility'}
                log('CANDIDATE_LEAF_METADATA',id..'|'..key..'|'..path)
            else log('CANDIDATE_LEAF_REJECTED',id..'|'..path..'|scheduler_or_non_ability')end
        else log('CANDIDATE_LEAF_REJECTED',id..'|'..path..'|unavailable')end
    end
    assert(profile.skills.skill_01,'no independently verified leaf metadata available')
    log('CANDIDATE_IDENTITY_READY',id..'|'..row.class_path..'|'..row.config_path)
    return profile
end

function Candidate.bind_granted(profile,items,valid,log)
    local count=items:GetArrayNum()
    assert(math.type(count)=='integer'and count>0 and count<=512,'bounded live grants required')
    for id,definition in pairs(profile.skills)do
        local matched=0
        for index=1,count do
            assert(index<=items:GetArrayNum(),'candidate grant list changed')
            local spec=items[index];local ability=spec.Ability
            if valid(ability)and ability:GetClass():GetFullName():match('^[^ ]+ (.+)$')==definition.class_path then
                assert(ability:IsA('/Script/GameplayAbilities.GameplayAbility')and not ability:IsA('/Script/SGameAI.RunSubtreeAbility'),
                    'live candidate ability requires unadapted scheduler')
                assert(math.type(spec.ActiveCount)=='integer'and spec.ActiveCount==0,'candidate grant not idle')
                matched=matched+1
            end
        end
        assert(matched==1,'candidate leaf must have exactly one live grant: '..id)
        definition.binding_verified=true;definition.cancel_binding_verified=true
        log('CANDIDATE_LIVE_BINDING',profile.id..'|'..id..'|'..definition.class_path)
    end
    return profile
end
return Candidate
