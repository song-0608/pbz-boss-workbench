-- The generated definition comes only from a closed same-variant dependency report.
-- It binds one native parent; the engine chooses its tree and activates its leaves.
local Candidate={}
local function exact(object,path)
    assert(object and object:IsValid() and object:GetFullName():match('^[^ ]+ (.+)$')==path,
        'combo asset identity changed: '..path)
end
function Candidate.prepare(id,grant,load,log)
    assert(id==definition.id and grant.boss_candidate==id and grant.developer_combo_only==true,
        'explicit isolated native-combo candidate required')
    assert(grant.developer_combo_evidence_sha256==definition.dependency_report_sha256,
        'closed exact combo evidence required')
    local cls=load(definition.class_path);exact(cls,definition.class_path)
    assert(cls:IsA('/Script/CoreUObject.Class'),'combo Actor class required')
    local defaults=cls:GetCDO();assert(defaults and defaults:IsValid(),'combo Actor defaults required')
    local config=defaults['Actor Config'];exact(config,definition.config_path)
    assert(config:GetCharacterName():ToString()==definition.display_name,'combo Actor name changed')
    local parent=load(definition.parent_class);exact(parent,definition.parent_class)
    assert(parent:IsA('/Script/CoreUObject.Class'),'combo parent class required')
    local cdo=parent:GetCDO()
    assert(cdo and cdo:IsValid() and cdo:IsA('/Script/GameplayAbilities.GameplayAbility')
        and cdo:IsA('/Script/SGameAI.RunSubtreeAbility'),'native subtree parent required')
    log('CANDIDATE_IDENTITY_READY',id..'|'..definition.class_path..'|'..definition.config_path)
    return {id=id,display_name=definition.display_name,exe_sha256=grant.exe_sha256,
        identity_verified=true,identity_evidence=definition.dependency_report_sha256,
        class_path=definition.class_path,config_path=definition.config_path,
        skill_timeout_seconds=30,control_verified=false,playable=false,developer_native_combo=true,
        training_target_profile='profiles.ahua',input={input_verified=false,mouse_scale=0.1},
        camera={binding_verified=false,distance=650,pivot_height=100,shoulder_offset=45,probe_size=14,
            fov=90,min_pitch=-60,max_pitch=20,keep_relative=0,keep_world=1,snap=2,camera_channel=4,
            spawn_collision=3,spawn_scale=0},skills={},developer_ability_pool={definition.parent_class}}
end
function Candidate.bind_granted(profile,items,valid,log)
    assert(profile.id==definition.id and profile.playable==false and profile.developer_native_combo==true
        and profile.class_path==definition.class_path and profile.config_path==definition.config_path,
        'exact developer combo profile required')
    local count=items:GetArrayNum()
    assert(math.type(count)=='integer' and count>=1 and count<=512,'bounded native combo grants required')
    local found=0
    for index=1,count do
        assert(items:GetArrayNum()==count,'native combo grant list changed')
        local spec=items[index];local ability=spec.Ability
        if valid(ability) and ability:GetClass():GetFullName():match('^[^ ]+ (.+)$')==definition.parent_class then
            assert(ability:IsA('/Script/GameplayAbilities.GameplayAbility')
                and ability:IsA('/Script/SGameAI.RunSubtreeAbility'),'live native subtree type changed')
            assert(math.type(spec.ActiveCount)=='integer' and spec.ActiveCount==0,'live combo parent not idle')
            found=found+1
        end
    end
    assert(found==1,'exactly one idle native parent grant required; never grant abilities')
    profile.skills={skill_01={name=definition.display_name..'原生Special05连招（开发）',
        class_path=definition.parent_class,binding_verified=true,active_count_field='ActiveCount',
        requires_target=true,cancel_binding_verified=true,cancel_function='K2_CancelAbility'}}
    log('CANDIDATE_LIVE_BINDING',profile.id..'|skill_01|'..definition.parent_class)
    return profile
end
return Candidate
