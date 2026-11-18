local definition=assert(loadfile(assert(arg[2])))()
local candidate=assert(loadfile(assert(arg[1])))()
local function object(path,kind)
    local value={}
    function value:IsValid()return true end
    function value:GetFullName()return'Fixture '..path end
    function value:IsA(wanted)return kind=='class'and wanted=='/Script/CoreUObject.Class'
        or kind=='ability'and wanted=='/Script/GameplayAbilities.GameplayAbility'end
    function value:GetClass()return object(path,'class')end
    function value:GetCDO()return object(path,'ability')end
    return value
end
local function load(path)
    local value=object(path,'class')
    if path==definition.class_path then
        function value:GetCDO()
            local config=object(definition.config_path,'config')
            function config:GetCharacterName()return{ToString=function()return definition.display_name end}end
            return{IsValid=function()return true end,['Actor Config']=config}
        end
    end
    return value
end
local grant={boss_candidate=definition.id,exe_sha256='fixture',
    identity_receipt_sha256=definition.identity_receipt_sha256,
    ability_metadata_receipt_sha256=definition.ability_metadata_receipt_sha256}
local function prepare()return candidate.prepare(definition.id,grant,load,function()end)end
local function items(paths)
    local result={};function result:GetArrayNum()return #self end
    for _,path in ipairs(paths)do result[#result+1]={Ability=object(path,'ability'),ActiveCount=0}end
    return result
end
local function valid(value)return value and value:IsValid()end
local profile=prepare();local pool=profile.developer_ability_pool
assert(#pool==#definition.ability_pool and not profile.playable and not profile.control_verified)
candidate.bind_granted(profile,items(pool),valid,function()end)
local slots={'skill_01','heavy_01','skill_02','dash'}
assert(#pool>=1)
for index=1,math.min(#pool,4)do assert(profile.skills[slots[index]].class_path==pool[index])end
-- Ownership wins over metadata priority: only a real native grant can create a binding.
if definition.require_complete_pool then
    assert(#pool<=4)
    for missing=1,#pool do
        local subset={};for i,path in ipairs(pool)do if i~=missing then subset[#subset+1]=path end end
        profile=prepare()
        assert(not pcall(candidate.bind_granted,profile,items(subset),valid,function()end),'incomplete page must reject')
        assert(next(profile.skills)==nil,'fixed page slots must not shift or partly bind')
    end
else
    local subset={};for index,path in ipairs(pool)do if index==2 or index==#pool then subset[#subset+1]=path end end
    profile=prepare();candidate.bind_granted(profile,items(subset),valid,function()end)
    assert(profile.skills.skill_01.class_path==subset[1]and not profile.skills.dash)
    if #subset==2 then assert(profile.skills.heavy_01.class_path==subset[2])else assert(not profile.skills.heavy_01)end
end
for _,mode in ipairs({'empty','duplicate','active','scheduler','changing'})do
    profile=prepare();local rows=items(pool)
    if mode=='empty'then rows=items({})
    elseif mode=='duplicate'then rows[#rows+1]=rows[1]
    elseif mode=='active'then rows[#rows].ActiveCount=1
    elseif mode=='scheduler'then rows[#rows].Ability.IsA=function()return true end
    else local n=0;function rows:GetArrayNum()n=n+1;return #self+(n>1 and 1 or 0)end end
    assert(not pcall(candidate.bind_granted,profile,rows,valid,function()end),mode)
    assert(next(profile.skills)==nil,'rejection must not partially bind')
end
assert(not pcall(candidate.prepare,'wrong_boss',grant,load,function()end))
grant.identity_receipt_sha256='wrong'
assert(not pcall(candidate.prepare,definition.id,grant,load,function()end))
print('PASS '..definition.id..': exact CDO identity, native unique grants, atomic rejection')
