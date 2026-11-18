-- Exercise generated two-action follow-up modules against fake native objects.
local definition=assert(loadfile(assert(arg[2])))()
local candidate=assert(loadfile(assert(arg[1])))()
assert(#definition.ability_pool==2)
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
local pool=definition.ability_pool
local profile=prepare()
candidate.bind_granted(profile,items(pool),valid,function()end)
assert(profile.skills.skill_01.class_path==pool[1]and profile.skills.heavy_01.class_path==pool[2])
assert(not profile.skills.skill_02 and not profile.skills.dash and not profile.playable)
profile=prepare();candidate.bind_granted(profile,items({pool[2]}),valid,function()end)
assert(profile.skills.skill_01.class_path==pool[2]and not profile.skills.heavy_01,'fresh grants decide actual bindings')
for _,mode in ipairs({'empty','foreign','duplicate','active','scheduler','changing'})do
    profile=prepare();local rows=items(pool)
    if mode=='empty'then rows=items({})
    elseif mode=='foreign'then rows=items({'/Wrong/Ability.Ability_C'})
    elseif mode=='duplicate'then rows[#rows+1]=rows[1]
    elseif mode=='active'then rows[2].ActiveCount=1
    elseif mode=='scheduler'then rows[2].Ability.IsA=function()return true end
    else local n=0;function rows:GetArrayNum()n=n+1;return #self+(n>1 and 1 or 0)end end
    assert(not pcall(candidate.bind_granted,profile,rows,valid,function()end),mode)
    assert(next(profile.skills)==nil,'late rejection cannot partially enable a skill')
end
grant.ability_metadata_receipt_sha256='changed'
assert(not pcall(candidate.prepare,definition.id,grant,load,function()end))
print('PASS '..definition.id..': two exact follow-ups, fresh grants, atomic rejection; no engine verification')
