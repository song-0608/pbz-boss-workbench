-- Exercise the actual generated delayed-target function, not a copied version.
local path=assert(arg[1],'generated arena fixture required')
local file=assert(io.open(path,'rb'));local source=file:read('*a');file:close()
local marker='-- End current target asset resolver.\n'
local first,last=assert(source:find(marker,1,true))
local resolver=source:sub(1,first-1)
local start=assert(source:find('        local function spawn_training_target(index)\n',last+1,true))
local finish=assert(source:find('        -- 用途：运行时生成的Pawn',start,true))
local body=source:sub(start,finish-1)
local prefix=[[
local generation,guarded,spawned=0,0,0
local current=true
local old={};setmetatable(old,{__index=function()error('stale cached dependency read')end})
local target_class,controller_class,maths,statics=old,old,old,old
local target_profile={identity_verified=true,class_path='/Fixture/Target.Target_C',config_path='/Fixture/Config.Config',display_name='target'}
local function object(path)return{GetFullName=function()return'Object '..path end}end
local valid=function(o)return o~=nil end
local function log()end
local function guard()guarded=guarded+1;assert(current,'lease closed')end
local pawn={AIControllerClass=nil,GetAddress=function()return 10 end,
 HasAuthority=function()return true end,GetController=function()return{}end,
 GetFullName=function()return'Target'end,K2_GetActorLocation=function()return{X=0,Y=0,Z=0}end}
local function isolate_initialization(value)assert(value==pawn)end
local function spawn_state()end
local extra_targets,target_actor={},nil
local spawn_side,spawn_attempts,heading=0,1,0
local layout={targets={{X=1},{X=2}}}
local pc,location,forward={},{X=0,Y=0,Z=0},{X=1,Y=0}
local fresh_controller=object('/PBZCombatAsset/Prototypes/AI/BP_PBZAIController.BP_PBZAIController_C')
function LoadAsset(path)
 if path~=target_profile.class_path then return fresh_controller end
 generation=generation+1
 local cls=object(path);local born=generation
 function cls:GetCDO()
  assert(born==generation)
  local config=object(target_profile.config_path)
  function config:GetCharacterName()return{ToString=function()return target_profile.display_name end}end
  return{['Actor Config']=config}
 end
 return cls
end
function StaticFindObject(path)
 if path:find('KismetMathLibrary',1,true)then return{MakeTransform=function(_,p)return p end}end
 return{BeginDeferredActorSpawnFromClass=function(_,owner,cls,transform,collision,unused,scale)
  assert(owner==pc and cls~=old and collision==3 and scale==0)
  spawned=spawned+1;return pawn
 end,FinishSpawningActor=function(_,actor)return actor end}
end
]]
local suffix=[[
spawn_training_target(1)
spawn_training_target(2)
assert(generation==2 and guarded==2 and spawned==2)
assert(target_actor==pawn and extra_targets[1].actor==pawn)
assert(pawn.AIControllerClass==fresh_controller)
current=false
assert(not pcall(spawn_training_target,1))
assert(generation==2 and spawned==2,'closed lease must reject before any asset resolution or spawn')
]]
-- The resolver closes over no native asset. All native objects come from the
-- new calls in each delayed invocation, with all original ownership checks.
assert(load(prefix..resolver..body..suffix,'generated-inventory-spawn-fixture'))()
print('PASS actual inventory target closure resolves fresh assets twice and rejects a closed lease')
