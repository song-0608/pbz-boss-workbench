-- Execute one generated batch against fake native metadata, never a game.
local script,mode=assert(arg[1]),arg[2]or'ok'
local file=assert(io.open(script,'rb'));local raw=file:read('*a');file:close()
local jobs={}
for key,role,path in raw:gmatch('{key="([^"]+)",role="([^"]+)",path="([^"]+)"}')do
    jobs[#jobs+1]={key=key,role=role,path=path}
end
assert(#jobs>0 and #jobs<=64)
local roles={};for _,job in ipairs(jobs)do roles[job.path]=job.role end
local logs,queue,loaded={},{},{}
local old_print,old_time=print,os.time
local clock=100
os.time=function()return clock end
print=function(value)logs[#logs+1]=value end
local loop
LoopAsync=function(ms,fn)assert(ms==100);loop=fn end
ExecuteInGameThread=function(fn)queue[#queue+1]=fn end
local function object(path,kind)
    local o={}
    function o:IsValid()return true end
    function o:GetFullName()return kind..' '..path end
    function o:IsA(wanted)return kind=='Class'and wanted=='/Script/CoreUObject.Class'
        or kind=='Config'and wanted=='/Script/Engine.PrimaryDataAsset'end
    return o
end
local configs={
    ['054_ZuoShang']='ActorConfig/ActorC_ZuoShang',
    ['066_RenTuZi']='ActorData/ActorC_RenTuZi_AutoGolden',
    ['071_XianZhe']='ActorConfig/ActorC_XianZhe',
}
LoadAsset=function(path)
    loaded[#loaded+1]=path;local role=assert(roles[path])
    if mode=='unavailable'and role=='ability'then return nil end
    local asset=object(mode=='wrong_identity'and'/Wrong.Asset'or path,'Class')
    function asset:GetCDO()
        if role=='ability'then
            return {IsValid=function()return true end,IsA=function(_,kind)
                return kind=='/Script/GameplayAbilities.GameplayAbility'
                    or kind=='/Script/SGameAI.RunSubtreeAbility'and mode=='subtree'
            end}
        end
        local folder=assert(path:match('/Mobs/([^/]+)/'));local config=assert(configs[folder])
        local config_path='/PBZCombatAsset/ActorData/Mobs/'..folder..'/'..config..'.'..config:match('([^/]+)$')
        local c=object(mode=='foreign_config'and'/Shared/Config.Config'or config_path,'Config')
        function c:GetCharacterName()return {ToString=function()return 'Fixture Boss'end}end
        return {IsValid=function()return true end,['Actor Config']=c}
    end
    local npc=object('/Script/ProjectPBZ.PBZCharacter_NPC','Class')
    local root=object('/Script/CoreUObject.Object','Class')
    function asset:GetSuperStruct()return mode=='lineage_cycle'and asset or npc end
    function npc:GetSuperStruct()return root end
    function root:GetSuperStruct()return nil end
    return asset
end
assert(loadfile(script))();assert(#loaded==0)
local stopped=false
if mode=='busy_timeout'or mode=='frozen_clock_budget'then
    assert(not loop()and #queue==1)
    if mode=='busy_timeout'then clock=191 end
    for _=1,1201 do stopped=loop();if stopped then break end end
    assert(stopped and #loaded==0 and #queue==1)
    table.remove(queue,1)();assert(#loaded==0,'late callback loaded after stop')
else
    for _=1,#jobs+2 do
        stopped=loop();if stopped then break end
        assert(#queue==1,'one pending metadata request')
        assert(not loop()and #queue==1,'pending request duplicated or completed early')
        if mode=='expired'then clock=191 end
        table.remove(queue,1)()
    end
    assert(stopped and #queue==0)
end
local joined=table.concat(logs,'\n')
local _,outcomes=joined:gsub('PBZ_ADAPTER_META:OUTCOME=','')
local _,rejected=joined:gsub('PBZ_ADAPTER_META:REJECTED=','')
local abilities,characters=0,0
for _,job in ipairs(jobs)do if job.role=='ability'then abilities=abilities+1 else characters=characters+1 end end
if mode=='expired'or mode=='busy_timeout'or mode=='frozen_clock_budget'then
    assert(#loaded==0 and joined:find('PBZ_ADAPTER_META:STOP=',1,true))
    assert(not joined:find('PBZ_ADAPTER_META:END=',1,true))
else
    assert(#loaded==#jobs and outcomes+rejected==#jobs and joined:find('PBZ_ADAPTER_META:END=',1,true))
    if mode=='wrong_identity'then assert(outcomes==0 and rejected==#jobs)
    elseif mode=='unavailable'then assert(outcomes==characters and rejected==abilities)
    elseif mode=='lineage_cycle'then assert(outcomes==abilities and rejected==characters)
    else
        assert(rejected==0)
        if mode=='subtree'then assert(joined:find('|subtree',1,true))end
        if mode=='foreign_config'then assert(joined:find('|/Shared/Config.Config|',1,true))end
    end
end
print=old_print;os.time=old_time
print('PASS 1 metadata jobs groups; generated CDO query queue: '..mode)
