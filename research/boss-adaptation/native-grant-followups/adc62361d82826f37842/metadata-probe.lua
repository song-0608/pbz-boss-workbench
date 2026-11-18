-- Frozen read-only metadata. No Actors, grants, possession or activation.
local jobs={
 {key="bc2327eecef6430ea5b3",role="ability",path="/PBZCombatAsset/ActorData/Mobs/071_XianZhe/Ability/GA_XianZhe_Skill_01.GA_XianZhe_Skill_01_C"},
 {key="ab33422aa78342e9dcd4",role="ability",path="/PBZCombatAsset/ActorData/Mobs/071_XianZhe/Ability/GA_XianZhe_CA.GA_XianZhe_CA_C"},
 {key="3f84e75463bc6d91ac18",role="ability",path="/PBZCombatAsset/ActorData/Mobs/067_MoTian/Ability/Dodge/GA_MoTian_Dodge_F_02.GA_MoTian_Dodge_F_02_C"},
 {key="eb00bd1346d05bcfe341",role="ability",path="/PBZCombatAsset/ActorData/Mobs/067_MoTian/Ability/Dodge/GA_MoTian_Dodge_R_02.GA_MoTian_Dodge_R_02_C"},
}
local fingerprint='adc62361d82826f37842'
local deadline=os.time()+90
local index,busy,stopped,polls=1,false,false,0
local function emit(event,value)print('PBZ_ADAPTER_META:'..event..'='..value..'\n')end
local function clean(value)return tostring(value):gsub('[%c|]',' '):sub(1,1024)end
local function path(object)
 assert(object and object:IsValid(),'metadata object unavailable')
 local value=assert(object:GetFullName():match('^[^ ]+ (/.+)$'),'metadata path unavailable')
 assert(#value<=1024 and value:match('^/[A-Za-z0-9_/%.]+$'),'metadata path changed')
 return value
end
local function stop(reason)
 if not stopped then stopped=true;emit('STOP',reason)end
 return true
end
emit('START',fingerprint)
LoopAsync(100,function()
 if stopped then return true end
 polls=polls+1
 if os.time()>=deadline or polls>900 then return stop('deadline or polling budget')end
 if busy then return false end
 if index>#jobs then stopped=true;emit('END',fingerprint);return true end
 local job=jobs[index];index=index+1;busy=true
 ExecuteInGameThread(function()
  if stopped then return end
  if os.time()>=deadline then stop('queued job expired');busy=false;return end
  local ok,why=pcall(function()
   local asset=LoadAsset(job.path)
   assert(path(asset)==job.path and asset:IsA('/Script/CoreUObject.Class'),'exact class required')
   local defaults=asset:GetCDO();assert(defaults and defaults:IsValid(),'metadata CDO unavailable')
   if job.role=='ability' then
    assert(defaults:IsA('/Script/GameplayAbilities.GameplayAbility'),'not a gameplay ability')
    local kind=defaults:IsA('/Script/SGameAI.RunSubtreeAbility')and'subtree'or'leaf'
    emit('OUTCOME',job.key..'|ability|'..job.path..'|'..kind)
   else
    local lineage,seen,npc={}, {},false
    local cls=asset
    while cls and cls:IsValid()and #lineage<16 do
     local name=path(cls);assert(not seen[name],'cyclic class lineage');seen[name]=true
     lineage[#lineage+1]=name;npc=npc or name=='/Script/ProjectPBZ.PBZCharacter_NPC'
     cls=cls:GetSuperStruct()
    end
    assert(not(cls and cls:IsValid())and npc and lineage[#lineage]=='/Script/CoreUObject.Object',
     'complete native NPC lineage required')
    local config=defaults['Actor Config'];local config_path=path(config)
    assert(config:IsA('/Script/Engine.PrimaryDataAsset'),'Actor Config data asset required')
    local name=config:GetCharacterName():ToString()
    assert(type(name)=='string'and #name>0 and #name<=512 and not name:find('[%c|]'),'bounded display name required')
    emit('OUTCOME',job.key..'|character|'..job.path..'|'..config_path..'|'..name..'|'..table.concat(lineage,','))
   end
  end)
  if not ok then emit('REJECTED',job.key..'|'..clean(why))end
  busy=false
 end)
 return false
end)
