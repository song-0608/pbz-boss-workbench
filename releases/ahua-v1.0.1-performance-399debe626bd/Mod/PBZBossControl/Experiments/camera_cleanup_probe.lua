-- 用途：在离线研究箱比较UE4SS对象可解析、引擎对象可用和销毁状态；只生成自己的诊断对象，不接管主角。
local function log(k,v)print('PBZ_CAMERA_CLEANUP_PROBE:'..k..'='..tostring(v)..'\n')end
local function valid(x)return x and x:IsValid()end
ExecuteInGameThread(function()
 local ok,why=pcall(function()
  assert(os.time()<camera_probe_deadline,'camera probe lease ended')
  local pc
  for _,candidate in ipairs(FindAllOf('PBZPlayerController')or{})do
   if valid(candidate)and valid(candidate.Pawn)and candidate:GetFullName():find(':PersistentLevel.',1,true)then
    assert(not pc,'ambiguous player');pc=candidate
   end
  end
  assert(pc,'gameplay player required')
  local system=StaticFindObject('/Script/Engine.Default__KismetSystemLibrary')
  local is_valid=StaticFindObject('/Script/Engine.KismetSystemLibrary:IsValid')
  assert(valid(system)and valid(is_valid),'validated engine validity query missing')
  -- 用途：CallFunction显式指定反射函数，避免system:IsValid()命中UE4SS自身同名方法。
  local function engine_valid(value)
   if not(value and value:IsValid())then return false end
   return system:CallFunction(is_valid,value)==true
  end
  assert(engine_valid(pc)and not engine_valid(nil),'engine validity positive/negative controls failed')
  local statics=StaticFindObject('/Script/Engine.Default__GameplayStatics')
  local maths=StaticFindObject('/Script/Engine.Default__KismetMathLibrary')
  local p=pc.Pawn:K2_GetActorLocation()
  local objects={}
  for index,path in ipairs({'/Script/Engine.CameraActor','/Script/Engine.Actor'})do
   local transform=maths:MakeTransform({X=p.X+index*100,Y=p.Y,Z=p.Z+150},{Pitch=0,Yaw=0,Roll=0},{X=1,Y=1,Z=1})
   local cls=StaticFindObject(path)
   local actor=statics:BeginDeferredActorSpawnFromClass(pc,cls,transform,3,nil,0)
   assert(valid(actor),'probe actor rejected')
   statics:FinishSpawningActor(actor,transform,0)
   local label=tostring(index)
   objects[#objects+1]=actor
   log('BEFORE',label..'|object='..actor:GetFullName()..'|role='..tostring(actor:GetLocalRole())
    ..'|engine_valid='..tostring(engine_valid(actor))..'|destroying='..tostring(actor:IsActorBeingDestroyed()))
   if index==1 then
    local relative=maths:MakeTransform({X=0,Y=0,Z=0},{Pitch=0,Yaw=0,Roll=0},{X=1,Y=1,Z=1})
    local boom=actor:AddComponentByClass(StaticFindObject('/Script/Engine.SpringArmComponent'),true,relative,false)
    assert(valid(boom),'probe arm rejected')
    boom:SetComponentTickEnabled(false);boom:K2_DestroyComponent(actor)
    log('BOOM_AFTER','engine_valid='..tostring(engine_valid(boom))..'|ue4ss_valid='..tostring(valid(boom))
      ..'|destroying='..tostring(boom:IsBeingDestroyed())..'|tick='..tostring(boom:IsComponentTickEnabled()))
   end
   actor:K2_DestroyActor()
   log('AFTER',label..'|engine_valid='..tostring(engine_valid(actor))..'|ue4ss_valid='..tostring(valid(actor))
      ..'|destroying='..tostring(actor:IsActorBeingDestroyed())..'|role='..tostring(actor:GetLocalRole()))
  end
  for _,delay in ipairs({500,1500,3000})do
   ExecuteInGameThreadWithDelay(delay,function()
    if os.time()>=camera_probe_deadline then return end
    local observed,error=pcall(function()
     for index,actor in ipairs(objects)do
      log('DELAYED',tostring(delay)..'|'..index..'|engine_valid='..tostring(engine_valid(actor))..'|ue4ss_valid='..tostring(valid(actor)))
     end
    end)
    if not observed then log('OBSERVATION_REJECTED',error)end
   end)
  end
  log('REQUESTS_COMPLETE','two owned actors only; player control untouched')
 end)
 if not ok then log('REJECTED',why)end
end)
