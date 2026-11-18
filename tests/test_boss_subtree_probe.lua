-- Exercise the actual generated probe against native-object doubles.
local script,mode=assert(arg[1]),arg[2]or'ok'
local file=assert(io.open(script,'rb'));local raw=file:read('*a');file:close()
local encoded=assert(raw:match('local jobs=(.-)\nlocal fingerprint='))
local jobs=assert(load('return '..encoded))();assert(#jobs>0)
local logs,queue,loaded={},{},0
local old_print,old_time=print,os.time
local clock=100;os.time=function()return clock end
print=function(value)logs[#logs+1]=value end
local loop
LoopAsync=function(ms,fn)assert(ms==100);assert(not loop);loop=fn end
ExecuteInGameThread=function(fn)queue[#queue+1]=fn end
local function object(path,kind)
 local o={}
 function o:IsValid()return true end
 function o:GetFullName()return kind..' '..path end
 function o:IsA(wanted)
  return (kind=='BlueprintGeneratedClass'or kind=='LegoAbilityBlueprintGeneratedClass')and wanted=='/Script/CoreUObject.Class'
   or kind=='BehaviorTree'and wanted=='/Script/AIModule.BehaviorTree'
 end
 return o
end
local function wrapped(value)return {get=function()return value end}end
LoadAsset=function(path)
 loaded=loaded+1
 local cls=object(mode=='wrong_identity'and'/Other.Wrong_C'or path,'BlueprintGeneratedClass')
 function cls:GetCDO()
  local defaults={IsValid=function()return true end,IsA=function(_,kind)
   return kind=='/Script/SGameAI.RunSubtreeAbility'and mode~='wrong_cdo'end}
  defaults.ComboTreeWithWeight={ForEach=function(_,callback)
   if mode=='map_unavailable'then error('TrivialObject map access unavailable')end
   if mode=='empty'then return end
   local package=assert(path:match('^(.+)%.'))
   local tree_path=package..'_Tree.Tree'
   local tree=object(tree_path,'BehaviorTree')
   local function node(index)
    local name=(mode=='foreign_node'and'/Other.Tree'or tree_path)..':Node_'..index
    local n=object(name,'BTTask_ActivateAbility')
    local composite=index==1 or mode=='node_bound'and index<=129
    function n:IsA(kind)return kind=='/Script/AIModule.BTCompositeNode'and composite end
    function n:GetClass()
     local c={IsValid=function()return true end,GetSuperStruct=function()return nil end}
     function c:ForEachProperty(callback)
      if mode=='property_timeout'then clock=105 end
      for _,entry in ipairs({{'ObjectProperty','TreeAsset'},{'ObjectProperty','ParentNode'},
       {'ObjectProperty','非ASCII 属性'},{'ClassProperty','无关 类属性'}})do
       callback({GetFullName=function()return entry[1]..' /Script/Fixture.Node:Unrelated'end,
        GetFName=function()return {ToString=function()return entry[2]end}end})
      end
      if not composite then
       local p={GetFullName=function()return 'ClassProperty /Script/Fixture.Node:AbilityToActivate'end,
        GetFName=function()return {ToString=function()return 'AbilityToActivate'end}end}
       callback(p)
      end
     end
     return c
    end
    n.AbilityToActivate=object(package..'_Leaf.GA_Fixture_Leaf_C',mode=='lego_class'and
     'LegoAbilityBlueprintGeneratedClass'or mode=='nonclass_reference'and'Actor'or'BlueprintGeneratedClass')
    setmetatable(n,{__index=function(_,property)
     if property=='TreeAsset'or property=='ParentNode'or property=='非ASCII 属性'or property=='无关 类属性'then
      error('unrelated native property was read')
     end
    end})
    n.Children={ForEach=function(_,callback)
     callback(0,wrapped({ChildTask=node(index+1)}))
    end}
    return n
   end
   tree.RootNode=node(1)
   callback(wrapped(tree),wrapped(mode=='nonfinite_weight'and math.huge or 1))
  end}
  return defaults
 end
 return cls
end
assert(loadfile(script))();assert(loaded==0)
local stopped=false
if mode=='busy_timeout'or mode=='poll_budget'then
 assert(not loop()and #queue==1)
 if mode=='busy_timeout'then clock=581 end
 for _=1,4802 do if loop()then stopped=true;break end end
 assert(stopped and loaded==0 and #queue==1)
 table.remove(queue,1)();assert(loaded==0,'queued callback loaded after timeout')
else
 for _=1,#jobs+2 do
  if loop()then stopped=true;break end
  assert(#queue==1 and not loop()and #queue==1,'more than one pending query')
  table.remove(queue,1)()
 end
 assert(stopped and #queue==0)
end
local joined=table.concat(logs,'\n')
local _,completed=joined:gsub('PBZ_SUBTREE_META:JOB_END=','')
local _,rejected=joined:gsub('PBZ_SUBTREE_META:REJECTED=','')
if mode=='busy_timeout'or mode=='poll_budget'then
 assert(joined:find('PBZ_SUBTREE_META:STOP=',1,true)and not joined:find('PBZ_SUBTREE_META:END=',1,true))
else
 assert(joined:find('PBZ_SUBTREE_META:END=',1,true)and loaded==#jobs)
 if mode=='ok'or mode=='empty'or mode=='lego_class'then assert(completed==#jobs and rejected==0)
 else assert(completed==0 and rejected==#jobs)end
end
print=old_print;os.time=old_time
if arg[3]=='emit'then print(joined)end
print('PASS actual subtree query: '..mode)
