-- Generated offline. Read-only asset metadata only; not a playable profile.
-- Must run only in the existing protected, idle, fixed-build research carrier.
local requests={
 {id="057_wanjun",role="character",path="/PBZCombatAsset/ActorData/Mobs/057_WanJun/BP_Monster_WanJun_JinGua.BP_Monster_WanJun_JinGua_C",config="/PBZCombatAsset/ActorData/Mobs/057_WanJun/ActorData/ActorC_WanJun_JinGua"},
 {id="057_wanjun",role="config",path="/PBZCombatAsset/ActorData/Mobs/057_WanJun/ActorData/ActorC_WanJun_JinGua.ActorC_WanJun_JinGua",config="/PBZCombatAsset/ActorData/Mobs/057_WanJun/ActorData/ActorC_WanJun_JinGua"},
 {id="073_yanqiansui",role="character",path="/PBZCombatAsset/ActorData/Mobs/073_YanQianSui/BP_Monster_YanQianSui.BP_Monster_YanQianSui_C",config="/PBZCombatAsset/ActorData/Mobs/073_YanQianSui/ActorConfig/ActorC_YanQianSui"},
 {id="073_yanqiansui",role="config",path="/PBZCombatAsset/ActorData/Mobs/073_YanQianSui/ActorConfig/ActorC_YanQianSui.ActorC_YanQianSui",config="/PBZCombatAsset/ActorData/Mobs/073_YanQianSui/ActorConfig/ActorC_YanQianSui"},
 {id="056_youlong",role="character",path="/PBZCombatAsset/ActorData/Mobs/056_YouLong/BP_Monster_YouLong_Harpoon.BP_Monster_YouLong_Harpoon_C",config="/PBZCombatAsset/ActorData/Mobs/056_YouLong/ActorData/ActorC_YouLong_SecondBrother"},
 {id="056_youlong",role="config",path="/PBZCombatAsset/ActorData/Mobs/056_YouLong/ActorData/ActorC_YouLong_SecondBrother.ActorC_YouLong_SecondBrother",config="/PBZCombatAsset/ActorData/Mobs/056_YouLong/ActorData/ActorC_YouLong_SecondBrother"},
}
local deadline=os.time()+90
local next_item,busy=1,false
local function emit(event,value) print('PBZ_MULTI_ID:'..event..'='..tostring(value)..'\n') end
emit('START','read-only metadata; no spawning, possession or ability activation')
LoopAsync(100,function()
 if os.time()>=deadline then emit('STOP','deadline');return true end
 if busy then return false end
 if next_item>#requests then emit('END','all requests processed; unverified outcomes remain blocked');return true end
 busy=true
 local row=requests[next_item];next_item=next_item+1
 ExecuteInGameThread(function()
  local ok,why=pcall(function()
   assert(os.time()<deadline,'probe expired before game-thread execution')
   local asset=LoadAsset(row.path)
   assert(asset and asset:IsValid(),'asset unavailable: '..row.path)
   local full=asset:GetFullName()
   assert(full:match('^[^ ]+ (.+)$')==row.path,'loaded asset differs from requested identity')
   emit('ASSET',row.id..'|'..row.role..'|'..full)
   if row.role=='character' then
    assert(asset:IsA('/Script/CoreUObject.Class'),'class metadata required')
    local cls,depth=asset,0
    while cls and cls:IsValid() and depth<16 do
     emit('LINEAGE',row.id..'|'..depth..'|'..cls:GetFullName())
     cls=cls:GetSuperStruct();depth=depth+1
    end
    assert(not(cls and cls:IsValid()),'class lineage exceeds bound')
    local defaults=asset:GetCDO()
    assert(defaults and defaults:IsValid(),'class default object unavailable')
    -- This is a CDO property observation, not a live actor/granted-ability proof.
    local config=defaults['Actor Config']
    assert(config and config:IsValid(),'Actor Config default reference unavailable')
    local actual=config:GetFullName()
    emit('CDO_CONFIG',row.id..'|'..actual)
    local object_path=assert(actual:match('^[^ ]+ (.+)$'),'config path format unavailable')
    assert(object_path:match('^([^%.]+)')==row.config,'default config differs from candidate')
    emit('DEFAULT_CONFIG_MATCH',row.id)
   else
    assert(asset:IsA('/Script/Engine.PrimaryDataAsset'),'config must be a primary data asset')
    emit('NAME',row.id..'|'..asset:GetCharacterName():ToString())
   end
  end)
  if not ok then emit('REJECTED',row.id..'|'..row.role..'|'..tostring(why)) end
  busy=false
 end)
 return false
end)
