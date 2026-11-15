-- Exercise generated identity jobs without a game: scheduling, exact identity and refusal paths.
local script=assert(arg[1])
local log,queue,loaded={}, {}, {}
local loop
local mode=arg[2] or 'ok'
local original_print=print
print=function(value)log[#log+1]=value end
LoopAsync=function(interval,callback)assert(interval==100);loop=callback end
ExecuteInGameThread=function(callback)queue[#queue+1]=callback end
local function object(path,kind)
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
 local package,leaf=path:match('^(.+)%.([^%.]+)$')
 local isclass=leaf:match('_C$')
 local result=object(mode=='wrong_identity' and '/Wrong.Asset' or path,isclass and 'BlueprintGeneratedClass' or 'PDA_ActorConfig_C')
 if isclass then
  local folder=assert(package:match('^(/PBZCombatAsset/ActorData/Mobs/[^/]+/)'))
  local configs={
   ['057_WanJun']='ActorData/ActorC_WanJun_JinGua',
   ['073_YanQianSui']='ActorConfig/ActorC_YanQianSui',
   ['056_YouLong']='ActorData/ActorC_YouLong_SecondBrother',
  }
  local name=assert(folder:match('/([^/]+)/$'));local config=assert(configs[name])
  local configleaf=config:match('([^/]+)$')
  local configpath=folder..config..'.'..configleaf
  if mode=='wrong_config'then configpath='/Wrong.Config'end
  function result:GetCDO()return {IsValid=function()return true end,['Actor Config']=object(configpath,'PDA_ActorConfig_C')}end
  function result:GetSuperStruct()return nil end
 else
  function result:GetCharacterName()return {ToString=function()return 'Fixture name'end}end
 end
 return result
end
assert(loadfile(script))()
assert(#loaded==0,'probe must wait for scheduler')
local stopped=false
for i=1,20 do
 stopped=loop();if stopped then break end
 assert(#queue==1,'one outstanding game-thread request required')
 if i==6 then
  assert(not loop(),'END emitted while final request still queued')
  assert(#queue==1,'pending request duplicated')
 end
 local callback=table.remove(queue,1);callback()
end
assert(stopped and #loaded==6)
local joined=table.concat(log,'\n')
assert(joined:find('PBZ_MULTI_ID:END=',1,true))
if mode=='ok'then
 assert(not joined:find('REJECTED',1,true));local _,count=joined:gsub('DEFAULT_CONFIG_MATCH=','');assert(count==3)
else
 assert(joined:find('REJECTED=',1,true));assert(not joined:find('DEFAULT_CONFIG_MATCH=',1,true))
end
original_print('PASS generated identity queue: '..mode)
