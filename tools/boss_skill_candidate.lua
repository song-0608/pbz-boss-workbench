-- A generated independent four-action expansion definition precedes this file.
-- All selected actions must exist as unique idle native grants; no fallback slots.
local Candidate={}
local slots={'skill_01','heavy_01','skill_02','dash'}
local function exact(object,path)
    assert(object and object:IsValid() and object:GetFullName():match('^[^ ]+ (.+)$')==path,
        'expansion asset identity mismatch: '..path)
end
local function definitions()
    assert(#definition.ability_pool==4,'exact four-action expansion required')
    local seen={}
    for _,path in ipairs(definition.ability_pool)do
        assert(type(path)=='string'and not seen[path],'duplicate expansion action')
        seen[path]=true
    end
    return seen
end
function Candidate.prepare(id,grant,load,log)
    definitions()
    assert(id==definition.id and grant.boss_candidate==id and grant.exe_sha256==definition.exe_sha256,
        'same-build independent skill expansion required')
    assert(grant.identity_receipt_sha256==definition.identity_receipt_sha256
        and grant.ability_metadata_receipt_sha256==definition.ability_metadata_receipt_sha256,
        'closed expansion source receipts required')
    local cls=load(definition.class_path);exact(cls,definition.class_path)
    assert(cls:IsA('/Script/CoreUObject.Class'),'expansion character class required')
    local cdo=cls:GetCDO();assert(cdo and cdo:IsValid(),'expansion character defaults required')
    local config=cdo['Actor Config'];exact(config,definition.config_path)
    assert(config:GetCharacterName():ToString()==definition.display_name,'expansion character name changed')
    for _,path in ipairs(definition.ability_pool)do
        local class=load(path);exact(class,path)
        assert(class:IsA('/Script/CoreUObject.Class'),'expansion ability class required')
        local defaults=class:GetCDO()
        assert(defaults and defaults:IsValid() and defaults:IsA('/Script/GameplayAbilities.GameplayAbility')
            and not defaults:IsA('/Script/SGameAI.RunSubtreeAbility'),'expansion requires a native leaf, not an AI subtree')
        log('CANDIDATE_LEAF_METADATA',id..'|pool|'..path)
    end
    log('CANDIDATE_IDENTITY_READY',id..'|'..definition.class_path..'|'..definition.config_path)
    return {id=id,display_name=definition.display_name,exe_sha256=definition.exe_sha256,
        identity_verified=true,identity_evidence=definition.identity_receipt_sha256,
        class_path=definition.class_path,config_path=definition.config_path,skills={},
        skill_timeout_seconds=30,control_verified=false,playable=false,training_target_profile='profiles.ahua',
        input={input_verified=false,mouse_scale=0.1},
        camera={binding_verified=false,distance=650,pivot_height=100,shoulder_offset=45,probe_size=14,
            fov=90,min_pitch=-60,max_pitch=20,keep_relative=0,keep_world=1,snap=2,camera_channel=4,
            spawn_collision=3,spawn_scale=0}}
end
function Candidate.bind_granted(profile,items,valid,log)
    assert(profile.id==definition.id and profile.playable==false,'exact expansion profile required')
    local allowed=definitions();local matches={}
    local count=items:GetArrayNum()
    assert(math.type(count)=='integer'and count>=1 and count<=512,'bounded expansion native grants required')
    for index=1,count do
        assert(items:GetArrayNum()==count,'expansion grant list changed')
        local spec=items[index];local ability=spec.Ability
        if valid(ability)then
            local path=ability:GetClass():GetFullName():match('^[^ ]+ (.+)$')
            if allowed[path]then
                assert(ability:IsA('/Script/GameplayAbilities.GameplayAbility')
                    and not ability:IsA('/Script/SGameAI.RunSubtreeAbility'),'live expansion subtree rejected')
                assert(math.type(spec.ActiveCount)=='integer'and spec.ActiveCount==0,'expansion native grant is not idle')
                assert(not matches[path],'duplicate expansion native grant');matches[path]=true
            end
        end
    end
    assert(items:GetArrayNum()==count,'expansion grant list changed before binding')
    local selected={}
    for index,path in ipairs(definition.ability_pool)do
        assert(matches[path],'required expansion native grant missing: '..path)
        selected[slots[index]]={name=assert(definition.action_names[slots[index]]),class_path=path,binding_verified=true,
            active_count_field='ActiveCount',requires_target=true,cancel_binding_verified=true,cancel_function='K2_CancelAbility'}
    end
    profile.skills=selected
    for _,id in ipairs(slots)do log('CANDIDATE_LIVE_BINDING',profile.id..'|'..id..'|'..selected[id].class_path)end
    return profile
end
return Candidate
