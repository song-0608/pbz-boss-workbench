local source=assert(arg[1])
local mode=arg[2] or 'ok'
local old_print=print
local events,queue,loaded={},{},{}
local loop,now
now=100
local old_time=os.time
os.time=function()return now end
print=function(value)events[#events+1]=value end
LoopAsync=function(interval,callback)assert(interval==100);loop=callback end
ExecuteInGameThread=function(callback)queue[#queue+1]=callback end
local folder='/PBZCombatAsset/ActorData/Mobs/056_YouLong/'
local configpath=folder..'ActorData/ActorC_YouLong_Harpoon.ActorC_YouLong_Harpoon'
local function obj(path,kind)
 local result={}
 function result:IsValid()return true end
 function result:GetFullName()return kind..' '..path end
 function result:IsA(wanted)
  return wanted=='/Script/CoreUObject.Class' and kind=='BlueprintGeneratedClass'
    or wanted=='/Script/Engine.PrimaryDataAsset' and kind=='PDA_ActorConfig_C'
 end
 return result
end
LoadAsset=function(path)
 loaded[#loaded+1]=path
 if mode=='unavailable' and path:find('/073_YanQianSui/',1,true)then return nil end
 local ability=path:find('/073_YanQianSui/',1,true)
 local isclass=path:sub(-2)=='_C'
 local result=obj(mode=='wrong_identity' and '/Wrong.Asset' or path,isclass and 'BlueprintGeneratedClass' or 'PDA_ActorConfig_C')
 if ability then
  function result:GetCDO()
   return {IsValid=function()return true end,IsA=function(_,wanted)
    return wanted=='/Script/GameplayAbilities.GameplayAbility'
      or wanted=='/Script/SGameAI.RunSubtreeAbility' and mode=='subtree'
   end}
  end
 elseif isclass then
  function result:GetCDO()return {IsValid=function()return true end,
   ['Actor Config']=obj(mode=='wrong_config' and '/Wrong.Config' or configpath,'PDA_ActorConfig_C')}end
  local npc=obj('/Script/ProjectPBZ.PBZCharacter_NPC','Class')
  local root=obj('/Script/CoreUObject.Object','Class')
  function result:GetSuperStruct()return npc end
  function npc:GetSuperStruct()return root end
  function root:GetSuperStruct()return nil end
 else
  function result:GetCharacterName()return {ToString=function()return 'Fixture Boss'end}end
 end
 return result
end
assert(loadfile(source))()
assert(#loaded==0)
local stopped=false
for i=1,100 do
 stopped=loop();if stopped then break end
 assert(#queue==1,'one pending game-thread job')
 assert(not loop() and #queue==1,'queued job duplicated or ended early')
 if mode=='expired'then now=200 end
 table.remove(queue,1)()
end
assert(stopped and #queue==0)
local joined=table.concat(events,'\n')
if mode=='expired'then
 assert(#loaded==0 and joined:find('PBZ_BOSS_META:STOP=',1,true))
 assert(not joined:find('PBZ_BOSS_META:END=',1,true))
else
 assert(#loaded==26 and joined:find('PBZ_BOSS_META:END=',1,true))
 local _,count=joined:gsub('PBZ_BOSS_META:ABILITY=','')
 assert(count==((mode=='wrong_identity'or mode=='unavailable')and 0 or 24))
 if mode=='ok'or mode=='subtree'then
  assert(not joined:find('REJECTED=',1,true))
  assert(joined:find('PBZ_MULTI_ID:DEFAULT_CONFIG_MATCH=056_youlong',1,true))
 elseif mode=='wrong_config'then
  assert(joined:find('PBZ_MULTI_ID:REJECTED=',1,true))
 end
 if mode=='subtree'then assert(joined:find('|subtree',1,true))end
end
print=old_print;os.time=old_time
print('PASS followup metadata queue: '..mode)
