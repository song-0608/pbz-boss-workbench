local Assets=require('player_spawn_assets')
local profile={identity_verified=true,class_path='/Fixture/Target.Target_C',
    config_path='/Fixture/TargetConfig.TargetConfig',display_name='target'}
local function object(path)
    return{GetFullName=function()return'Object '..path end}
end
local generation=0
local g={}
local dependencies={}
function g.LoadAsset(path)
    if path~=profile.class_path then return object(path)end
    generation=generation+1
    local born=generation
    local class=object(path)
    class.generation=born
    function class:GetCDO()
        assert(born==generation,'stale cached class used')
        local config=object(profile.config_path)
        function config:GetCharacterName()return{ToString=function()return profile.display_name end}end
        return{['Actor Config']=config}
    end
    return class
end
function g.StaticFindObject(path)
    local value=object(path);dependencies[#dependencies+1]=value;return value
end
local logs={}
local valid=function(o)return o~=nil and not o.invalid end
local log=function(k,v)logs[#logs+1]={k,v}end
local first=Assets.target(g,profile,valid,log)
local second=Assets.target(g,profile,valid,log)
assert(first~=second and first.generation==1 and second.generation==2)
assert(#dependencies==4 and #logs==2,'every spawn resolves dependencies and records readiness')
local load=g.LoadAsset
g.LoadAsset=function(path)if path==profile.class_path then return nil end;return load(path)end
assert(not pcall(Assets.target,g,profile,valid,log),'missing current class must reject before native spawn')
g.LoadAsset=function(path)
    local value=load(path)
    if path==profile.class_path then value.GetFullName=function()return'Object /Wrong.Class_C'end end
    return value
end
assert(not pcall(Assets.target,g,profile,valid,log),'wrong current class must reject')
g.LoadAsset=function(path)
    local value=load(path)
    if path==profile.class_path then value.GetCDO=function()
        return{['Actor Config']=object('/Wrong.Config')}
    end end
    return value
end
assert(not pcall(Assets.target,g,profile,valid,log),'wrong current config must reject')
assert(#logs==2,'rejection cannot attest spawn readiness')
print('PASS delayed spawn assets reacquire exact current classes and reject missing or changed identities')
