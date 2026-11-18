-- Resolve a fresh native class immediately before a delayed spawn. A Lua
-- closure is not an engine ownership receipt for an unloaded asset.
local Assets={}
local function object_path(object)
    return object:GetFullName():match('^[^ ]+ (.+)$')
end
function Assets.target(g,profile,valid,log)
    assert(profile.identity_verified==true,'verified training target identity required')
    local class=g.LoadAsset(profile.class_path)
    assert(valid(class),'current training target class unavailable')
    assert(object_path(class)==profile.class_path,'current training target class identity changed')
    local defaults=class:GetCDO()
    assert(valid(defaults),'current training target defaults unavailable')
    local config=defaults['Actor Config']
    assert(valid(config)and object_path(config)==profile.config_path,'current training target config changed')
    assert(config:GetCharacterName():ToString()==profile.display_name,'current training target name changed')
    local controller=g.LoadAsset('/PBZCombatAsset/Prototypes/AI/BP_PBZAIController.BP_PBZAIController_C')
    local maths=g.StaticFindObject('/Script/Engine.Default__KismetMathLibrary')
    local statics=g.StaticFindObject('/Script/Engine.Default__GameplayStatics')
    assert(valid(controller)and valid(maths)and valid(statics),'current spawn dependencies unavailable')
    log('TARGET_SPAWN_ASSETS_VERIFIED',profile.class_path)
    return class,controller,maths,statics
end
return Assets
