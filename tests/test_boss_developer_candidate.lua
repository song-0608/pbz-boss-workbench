local module_path,identity_hash,metadata_hash=assert(arg[1]),assert(arg[2]),assert(arg[3])
local candidate=assert(loadfile(module_path))()
local prefix='/PBZCombatAsset/ActorData/Mobs/073_YanQianSui/'
local configpath=prefix..'ActorConfig/ActorC_YanQianSui.ActorC_YanQianSui'
local classpath=prefix..'BP_Monster_YanQianSui.BP_Monster_YanQianSui_C'
local grant={boss_candidate='073_yanqiansui',exe_sha256='fixture',
    identity_receipt_sha256=identity_hash,ability_metadata_receipt_sha256=metadata_hash}
local function object(path,kind)
    local value={path=path}
    function value:IsValid()return true end
    function value:GetFullName()return 'Fixture '..self.path end
    function value:IsA(wanted)
        return kind=='class' and wanted=='/Script/CoreUObject.Class'
            or kind=='ability' and wanted=='/Script/GameplayAbilities.GameplayAbility'
    end
    function value:GetClass()return object(path,'class')end
    function value:GetCDO()return object(path,'ability')end
    return value
end
local function loader(path)
    local value=object(path,'class')
    if path==classpath then
        function value:GetCDO()
            local config=object(configpath,'config')
            function config:GetCharacterName()return{ToString=function()return'琴女烟千岁'end}end
            return{IsValid=function()return true end,['Actor Config']=config}
        end
    end
    return value
end
local logs={}
local function log(event,payload)logs[#logs+1]={event,payload}end
local function prepared()return candidate.prepare('073_yanqiansui',grant,loader,log)end
local function items(paths)
    local result={}
    function result:GetArrayNum()return #self end
    for _,path in ipairs(paths)do result[#result+1]={Ability=object(path,'ability'),ActiveCount=0}end
    return result
end
local function valid(v)return v and v:IsValid()end
assert(not pcall(candidate.prepare,'057_wanjun',grant,loader,log))
assert(not pcall(candidate.prepare,'073_yanqiansui',{},loader,log))
local p=prepared()
assert(not p.playable and not p.control_verified and next(p.skills)==nil)
assert(#p.developer_ability_pool==18)
local native=items(p.developer_ability_pool)
candidate.bind_granted(p,native,valid,log)
assert(p.skills.skill_01.class_path==p.developer_ability_pool[1])
assert(p.skills.dash.class_path==p.developer_ability_pool[4])
for _,skill in pairs(p.skills)do
    assert(skill.binding_verified and skill.cancel_binding_verified)
    assert(not skill.activation_runtime_verified and not skill.gameplay_verified and not skill.natural_completion_verified)
end
-- Missing native primary falls back in deterministic priority; nothing is manually granted.
p=prepared();native=items({p.developer_ability_pool[2],p.developer_ability_pool[4]})
candidate.bind_granted(p,native,valid,log)
assert(p.skills.skill_01.class_path==p.developer_ability_pool[2] and not p.skills.skill_02)
for _,mode in ipairs({'none','duplicate_late','active_late','float_active','scheduler','changing_list'})do
    p=prepared();native=items(p.developer_ability_pool)
    if mode=='none'then native=items({'/Foreign.Ability_C'})
    elseif mode=='duplicate_late'then native[#native+1]=native[1]
    elseif mode=='active_late'then native[#native].ActiveCount=1
    elseif mode=='float_active'then native[1].ActiveCount=0.5
    elseif mode=='scheduler'then
        local ability=native[1].Ability
        function ability:IsA(wanted)
            return wanted=='/Script/GameplayAbilities.GameplayAbility' or wanted=='/Script/SGameAI.RunSubtreeAbility'
        end
    else
        local calls=0
        function native:GetArrayNum()calls=calls+1;return #self+(calls>1 and 1 or 0)end
    end
    assert(not pcall(candidate.bind_granted,p,native,valid,log),mode)
    assert(next(p.skills)==nil,'failed late validation must not partially bind: '..mode)
end
local function changed_loader(path)
    local result=loader(path)
    if path==classpath then
        function result:GetCDO()return{IsValid=function()return true end,['Actor Config']=object('/Wrong.Config','config')}end
    end
    return result
end
assert(not pcall(candidate.prepare,'073_yanqiansui',grant,changed_loader,log))
print('PASS isolated developer candidate: identity, native unique idle grants, deterministic selection, atomic rejection')
