local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local candidate=require('boss_candidate')
local grant={boss_candidate='057_wanjun',identity_receipt_sha256=string.rep('a',64),exe_sha256='fixture'}
local prefix='/PBZCombatAsset/ActorData/Mobs/057_WanJun/'
local function object(path,kind)
    local value={path=path,kind=kind}
    function value:IsValid()return true end
    function value:GetFullName()return 'Fixture '..self.path end
    function value:IsA(cls)return cls==(self.kind=='class'and'/Script/CoreUObject.Class'or'/Script/GameplayAbilities.GameplayAbility')end
    function value:GetClass()return object(self.path,'class')end
    function value:GetCDO()return object(self.path,'ability')end
    return value
end
local function loader(path)
    local value=object(path,'class')
    if path==prefix..'BP_Monster_WanJun_JinGua.BP_Monster_WanJun_JinGua_C'then
        function value:GetCDO()
            local config=object(prefix..'ActorData/ActorC_WanJun_JinGua.ActorC_WanJun_JinGua','config')
            function config:GetCharacterName()return{ToString=function()return'巨锤客：万钧'end}end
            return{['Actor Config']=config}
        end
    end
    return value
end
local function log()end
assert(not pcall(candidate.prepare,'057_wanjun',{},loader,log))
assert(not pcall(candidate.prepare,'unknown',grant,loader,log))
local profile=candidate.prepare('057_wanjun',grant,loader,log)
assert(profile.playable==false and profile.control_verified==false)
local items={};function items:GetArrayNum()return #self end
for _,definition in pairs(profile.skills)do
    assert(not definition.binding_verified and not definition.activation_runtime_verified and not definition.gameplay_verified)
    items[#items+1]={Ability=object(definition.class_path,'ability'),ActiveCount=0}
end
candidate.bind_granted(profile,items,function(v)return v:IsValid()end,log)
assert(profile.skills.skill_01.binding_verified and not profile.skills.skill_01.natural_completion_verified)
items[1].ActiveCount=1
assert(not pcall(candidate.bind_granted,profile,items,function(v)return v:IsValid()end,log))
items[1].ActiveCount=0;items[#items+1]=items[1]
assert(not pcall(candidate.bind_granted,profile,items,function(v)return v:IsValid()end,log))
local function subtree_loader(path)
    local result=loader(path)
    if path:find('/Abilities/',1,true)then
        function result:GetCDO()
            local default=object(path,'ability')
            function default:IsA(cls)return cls=='/Script/GameplayAbilities.GameplayAbility'or cls=='/Script/SGameAI.RunSubtreeAbility'end
            return default
        end
    end
    return result
end
assert(not pcall(candidate.prepare,'057_wanjun',grant,subtree_loader,log))
print('Candidate identity, independent scope, exact idle unique grants and subtree rejection: PASS')
