local candidate=assert(loadfile(assert(arg[1])))()
local identity,metadata=assert(arg[2]),assert(arg[3])
local prefix='/PBZCombatAsset/ActorData/Mobs/056_YouLong/'
local cls=prefix..'BP_Monster_YouLong_Harpoon.BP_Monster_YouLong_Harpoon_C'
local configpath=prefix..'ActorData/ActorC_YouLong_Harpoon.ActorC_YouLong_Harpoon'
local function obj(path,kind)
    local v={};function v:IsValid()return true end
    function v:GetFullName()return'Fixture '..path end
    function v:IsA(wanted)return kind=='class'and wanted=='/Script/CoreUObject.Class'
        or kind=='ability'and wanted=='/Script/GameplayAbilities.GameplayAbility'end
    function v:GetClass()return obj(path,'class')end
    function v:GetCDO()return obj(path,'ability')end
    return v
end
local function load(path)
    local v=obj(path,'class')
    if path==cls then function v:GetCDO()
        local c=obj(configpath,'config')
        function c:GetCharacterName()return{ToString=function()return'发狂的水行帮主：游龙'end}end
        return{IsValid=function()return true end,['Actor Config']=c}
    end end
    return v
end
local grant={boss_candidate='056_youlong',exe_sha256='build',identity_receipt_sha256=identity,
    ability_metadata_receipt_sha256=metadata}
local function prepared()return candidate.prepare('056_youlong',grant,load,function()end)end
local function items(paths)
    local rows={};function rows:GetArrayNum()return #self end
    for _,p in ipairs(paths)do rows[#rows+1]={Ability=obj(p,'ability'),ActiveCount=0}end
    return rows
end
local function valid(v)return v and v:IsValid()end
local p=prepared();assert(#p.developer_ability_pool==8 and not p.playable and not p.control_verified)
local pool=p.developer_ability_pool
candidate.bind_granted(p,items(pool),valid,function()end)
assert(p.skills.skill_01.class_path==pool[1]and p.skills.dash.class_path==pool[4])
p=prepared();candidate.bind_granted(p,items({pool[2],pool[6]}),valid,function()end)
assert(p.skills.skill_01.class_path==pool[2]and p.skills.heavy_01.class_path==pool[6]and not p.skills.dash)
for _,mode in ipairs({'none','duplicate','active','scheduler','changing'})do
    p=prepared();local rows=items(pool)
    if mode=='none'then rows=items({prefix..'Ability/Abilities/GA_YouLong_TakeSpear.GA_YouLong_TakeSpear_C'})
    elseif mode=='duplicate'then rows[#rows+1]=rows[1]
    elseif mode=='active'then rows[#rows].ActiveCount=1
    elseif mode=='scheduler'then rows[1].Ability.IsA=function()return true end
    else local n=0;function rows:GetArrayNum()n=n+1;return #self+(n>1 and 1 or 0)end end
    assert(not pcall(candidate.bind_granted,p,rows,valid,function()end),mode)
    assert(next(p.skills)==nil,'failed grants cannot partially bind')
end
assert(not pcall(candidate.prepare,'073_yanqiansui',grant,load,function()end))
print('PASS YouLong exact Harpoon identity, native idle-only bindings, excluded dependence and atomic rejection')
