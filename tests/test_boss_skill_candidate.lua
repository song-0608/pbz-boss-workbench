local bundle=assert(arg[1])
local file=assert(io.open(bundle..'/boss_candidate.lua','rb'));local source=file:read('*a');file:close()
local first=assert(source:match('^(local definition=[^\n]+)'))
local definition=assert(load(first:gsub('^local definition=','return '),'expansion constants','t',{}))()
local Candidate=assert(load(source,'expansion module','t',_G))()
local checks=0
local function check(name,fn)fn();checks=checks+1;print('PASS '..name)end
local function fixture()
    local f={loads=0,logs={}}
    f.grant={boss_candidate=definition.id,exe_sha256=definition.exe_sha256,
        identity_receipt_sha256=definition.identity_receipt_sha256,
        ability_metadata_receipt_sha256=definition.ability_metadata_receipt_sha256}
    local function obj(path,class)
        return {IsValid=function()return true end,GetFullName=function()return class..' '..path end}
    end
    f.load=function(path)
        f.loads=f.loads+1
        if f.missing==path then return nil end
        local o=obj(f.wrong_asset and path..'_wrong'or path,'BlueprintGeneratedClass')
        function o:IsA(kind)return kind=='/Script/CoreUObject.Class'end
        function o:GetCDO()
            if path==definition.class_path then
                local c=obj(f.wrong_config and '/Wrong.Config'or definition.config_path,'PDA_ActorConfig_C')
                function c:GetCharacterName()return {ToString=function()return f.wrong_name and 'other'or definition.display_name end}end
                return {IsValid=function()return true end,['Actor Config']=c}
            end
            return {IsValid=function()return true end,IsA=function(_,kind)
                return kind=='/Script/GameplayAbilities.GameplayAbility'or(f.subtree==path and kind=='/Script/SGameAI.RunSubtreeAbility')
            end}
        end
        return o
    end
    f.log=function(kind,value)f.logs[#f.logs+1]=kind..'='..value end
    function f:prepare()return Candidate.prepare(definition.id,self.grant,self.load,self.log)end
    f.entries={}
    function f:add(path,active)
        local a={IsValid=function()return true end,GetClass=function()return {GetFullName=function()return 'BlueprintGeneratedClass '..path end}end,
            IsA=function(_,kind)return kind=='/Script/GameplayAbilities.GameplayAbility'or(f.live_subtree==path and kind=='/Script/SGameAI.RunSubtreeAbility')end}
        self.entries[#self.entries+1]={Ability=a,ActiveCount=active or 0}
    end
    for _,path in ipairs(definition.ability_pool)do f:add(path)end
    local reads=0
    f.items=setmetatable({GetArrayNum=function()
        reads=reads+1
        return #f.entries+(f.change_after and reads>=f.change_after and 1 or 0)
    end},{__index=function(_,i)return f.entries[i]end})
    function f:bind(profile)return Candidate.bind_granted(profile,self.items,function(o)return o and o:IsValid()end,self.log)end
    return f
end
check('current metadata verification leaves profile unplayable',function()
    local f=fixture();local p=f:prepare();assert(p.id==definition.id and p.playable==false and next(p.skills)==nil)
end)
check('different build fails before loading assets',function()
    local f=fixture();f.grant.exe_sha256='other';assert(not pcall(f.prepare,f)and f.loads==0)
end)
check('different source receipt fails before loading assets',function()
    local f=fixture();f.grant.ability_metadata_receipt_sha256='other';assert(not pcall(f.prepare,f)and f.loads==0)
end)
check('asset suffix similarity cannot satisfy exact identity',function()
    local f=fixture();f.wrong_asset=true;assert(not pcall(f.prepare,f))
end)
check('character config and display name remain independent checks',function()
    local f=fixture();f.wrong_config=true;assert(not pcall(f.prepare,f))
    f=fixture();f.wrong_name=true;assert(not pcall(f.prepare,f))
end)
check('native subtree metadata cannot enter the expansion',function()
    local f=fixture();f.subtree=definition.ability_pool[1];assert(not pcall(f.prepare,f))
end)
check('missing ability metadata prevents all binding',function()
    local f=fixture();f.missing=definition.ability_pool[4];assert(not pcall(f.prepare,f))
end)
check('four unique idle native grants bind the four exact tested slots',function()
    local f=fixture();local p=f:prepare();assert(f:bind(p)==p)
    for i,id in ipairs({'skill_01','heavy_01','skill_02','dash'})do assert(p.skills[id].class_path==definition.ability_pool[i])end
    assert(p.playable==false and not p.control_verified)
end)
check('native grant enumeration order cannot shift skill keys',function()
    local f=fixture();f.entries[1],f.entries[4]=f.entries[4],f.entries[1]
    local p=f:prepare();f:bind(p);assert(p.skills.skill_01.class_path==definition.ability_pool[1])
end)
check('missing required grant does not silently substitute another skill',function()
    local f=fixture();table.remove(f.entries,1);local p=f:prepare();local original=p.skills
    assert(not pcall(f.bind,f,p)and p.skills==original and next(original)==nil)
end)
check('late duplicate native grant cannot partially commit bindings',function()
    local f=fixture();f:add(definition.ability_pool[4]);local p=f:prepare()
    assert(not pcall(f.bind,f,p)and next(p.skills)==nil)
end)
check('active or noninteger native grant is rejected atomically',function()
    for _,active in ipairs({1,.5})do
        local f=fixture();f.entries[4].ActiveCount=active;local p=f:prepare()
        assert(not pcall(f.bind,f,p)and next(p.skills)==nil)
    end
end)
check('a same-named ability from another package is not a grant match',function()
    local f=fixture();table.remove(f.entries,1);f:add('/Other/Package.'..definition.ability_pool[1]:match('%.(.+)$'))
    assert(not pcall(f.bind,f,f:prepare()))
end)
check('live subtree cannot pass on earlier metadata',function()
    local f=fixture();f.live_subtree=definition.ability_pool[4];assert(not pcall(f.bind,f,f:prepare()))
end)
check('grant count changes before commit leave no partial skills',function()
    local f=fixture();f.change_after=6;local p=f:prepare();assert(not pcall(f.bind,f,p)and next(p.skills)==nil)
end)
check('mutable profile fields cannot replace the frozen action allowlist',function()
    local f=fixture();local p=f:prepare();p.developer_ability_pool={'/Other.Fake_C'};f:bind(p)
    assert(p.skills.skill_01.class_path==definition.ability_pool[1])
end)
print('PASS '..checks..' skill expansion groups; fake native objects, no game started')
