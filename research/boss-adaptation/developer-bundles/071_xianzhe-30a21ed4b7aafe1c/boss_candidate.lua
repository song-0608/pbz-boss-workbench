local definition={["id"]="071_xianzhe",["class_path"]="/PBZCombatAsset/ActorData/Mobs/071_XianZhe/BP_Monster_XianZhe.BP_Monster_XianZhe_C",["config_path"]="/PBZCombatAsset/ActorData/Mobs/071_XianZhe/ActorConfig/ActorC_XianZhe.ActorC_XianZhe",["display_name"]="弦儿",["identity_receipt_sha256"]="31f9e0abaa339bbecaceb3bfaa83163f928cadc03d4b7e375bddf736f7011f62",["ability_metadata_receipt_sha256"]="31f9e0abaa339bbecaceb3bfaa83163f928cadc03d4b7e375bddf736f7011f62",["ability_pool"]={"/PBZCombatAsset/ActorData/Mobs/071_XianZhe/Ability/GA_XianZhe_Skill_05.GA_XianZhe_Skill_05_C","/PBZCombatAsset/ActorData/Mobs/071_XianZhe/Ability/GA_XianZhe_Skill_06.GA_XianZhe_Skill_06_C","/PBZCombatAsset/ActorData/Mobs/071_XianZhe/Ability/GA_XianZhe_Skill_07.GA_XianZhe_Skill_07_C","/PBZCombatAsset/ActorData/Mobs/071_XianZhe/Ability/GA_XianZhe_Dodge_B.GA_XianZhe_Dodge_B_C","/PBZCombatAsset/ActorData/Mobs/071_XianZhe/Ability/GA_XianZhe_Dodge_L.GA_XianZhe_Dodge_L_C"},["blocked_scene_abilities"]={"/PBZCombatAsset/ActorData/Mobs/071_XianZhe/Ability/GA_XianZhe_CA_02.GA_XianZhe_CA_02_C","/PBZCombatAsset/ActorData/Mobs/071_XianZhe/Ability/GA_XianZhe_EnterCombat.GA_XianZhe_EnterCombat_C","/PBZCombatAsset/ActorData/Mobs/071_XianZhe/BulletData/GA_XianZhe_EnergySpear_Blue.GA_XianZhe_EnergySpear_Blue_C","/PBZCombatAsset/ActorData/Mobs/071_XianZhe/BulletData/GA_XianZhe_EnergySpear_Red.GA_XianZhe_EnergySpear_Red_C"},["max_local_displacement_cm"]=3000}
-- Generated constants precede this isolated developer module. No player registration.
local Candidate={}
local function exact(object,path)
    assert(object and object:IsValid() and object:GetFullName():match('^[^ ]+ (.+)$')==path,
        'candidate asset identity changed: '..path)
end
function Candidate.prepare(id,grant,load,log)
    assert(id==definition.id and grant.boss_candidate==id,'exact developer candidate required')
    assert(grant.identity_receipt_sha256==definition.identity_receipt_sha256
        and grant.ability_metadata_receipt_sha256==definition.ability_metadata_receipt_sha256,
        'independent closed metadata receipts required')
    local cls=load(definition.class_path);exact(cls,definition.class_path)
    assert(cls:IsA('/Script/CoreUObject.Class'),'candidate class required')
    local defaults=cls:GetCDO();assert(defaults and defaults:IsValid(),'candidate defaults required')
    local config=defaults['Actor Config'];exact(config,definition.config_path)
    assert(config:GetCharacterName():ToString()==definition.display_name,'candidate name changed')
    local pool={}
    for _,path in ipairs(definition.ability_pool)do
        local ability=load(path);exact(ability,path)
        assert(ability:IsA('/Script/CoreUObject.Class'),'ability class required')
        local cdo=ability:GetCDO()
        assert(cdo and cdo:IsValid() and cdo:IsA('/Script/GameplayAbilities.GameplayAbility')
            and not cdo:IsA('/Script/SGameAI.RunSubtreeAbility'),'independent leaf metadata required')
        pool[#pool+1]=path
        log('CANDIDATE_LEAF_METADATA',id..'|pool|'..path)
    end
    assert(#pool>=1 and #pool<=32,'bounded candidate pool required')
    log('CANDIDATE_IDENTITY_READY',id..'|'..definition.class_path..'|'..definition.config_path)
    return {id=id,display_name=definition.display_name,exe_sha256=grant.exe_sha256,
        identity_verified=true,identity_evidence=definition.identity_receipt_sha256,
        class_path=definition.class_path,config_path=definition.config_path,
        skill_timeout_seconds=30,control_verified=false,playable=false,
        training_target_profile='profiles.ahua',input={input_verified=false,mouse_scale=0.1},
        camera={binding_verified=false,distance=650,pivot_height=100,shoulder_offset=45,probe_size=14,
            fov=90,min_pitch=-60,max_pitch=20,keep_relative=0,keep_world=1,snap=2,camera_channel=4,
            spawn_collision=3,spawn_scale=0},skills={},developer_ability_pool=pool}
end
function Candidate.bind_granted(profile,items,valid,log)
    assert(profile.id==definition.id and profile.playable==false,'exact developer profile required')
    local count=items:GetArrayNum()
    assert(math.type(count)=='integer' and count>=1 and count<=512,'bounded live grants required')
    local matches={}
    local allowed={};for _,path in ipairs(profile.developer_ability_pool)do allowed[path]=true end
    for index=1,count do
        assert(items:GetArrayNum()==count,'grant list changed')
        local spec=items[index];local ability=spec.Ability
        if valid(ability)then
            local path=ability:GetClass():GetFullName():match('^[^ ]+ (.+)$')
            if allowed[path]then
                assert(ability:IsA('/Script/GameplayAbilities.GameplayAbility')
                    and not ability:IsA('/Script/SGameAI.RunSubtreeAbility'),'live scheduler rejected')
                assert(math.type(spec.ActiveCount)=='integer' and spec.ActiveCount==0,'live candidate not idle')
                assert(not matches[path],'duplicate live grant')
                matches[path]=true
            end
        end
    end
    -- Commit bindings only after the entire live list passed, never before a late rejection.
    local selected={};local ids={'skill_01','heavy_01','skill_02','dash'};local next_id=1
    for _,path in ipairs(profile.developer_ability_pool)do
        if matches[path] and next_id<=#ids then
            local id=ids[next_id];next_id=next_id+1
            selected[id]={name=path:match('%.(.+)_C$'),class_path=path,binding_verified=true,
                active_count_field='ActiveCount',requires_target=true,cancel_binding_verified=true,
                cancel_function='K2_CancelAbility'}
        end
    end
    assert(selected.skill_01,'no unique idle native candidate grants; no manual grants allowed')
    profile.skills=selected
    for _,id in ipairs(ids)do
        if selected[id]then log('CANDIDATE_LIVE_BINDING',profile.id..'|'..id..'|'..selected[id].class_path)end
    end
    return profile
end
return Candidate
