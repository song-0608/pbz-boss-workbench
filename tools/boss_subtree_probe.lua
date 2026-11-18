-- Read CDO subtree maps and their declared node relations. Never run a tree.
local deadline=os.time()+480
local index,busy,stopped,polls=1,false,false,0
local batch_nodes,batch_refs=0,0
local function emit(event,value)print('PBZ_SUBTREE_META:'..event..'='..value..'\n')end
local function valid(o)return o and o:IsValid()end
local function fullname(o)
 assert(valid(o),'object unavailable')
 local name=o:GetFullName()
 assert(type(name)=='string'and #name<=2048 and name:match('^[A-Za-z0-9_]+ /[A-Za-z0-9_/%.:]+$'),
  'bounded exact object name required')
 return name
end
local function path(o)return assert(fullname(o):match('^[^ ]+ (/.+)$'))end
local function stop(why)
 if not stopped then stopped=true;emit('STOP',why)end
 return true
end
emit('START',fingerprint)
LoopAsync(100,function()
 if stopped then return true end
 polls=polls+1
 if os.time()>=deadline or polls>4800 then return stop('deadline or polling budget')end
 if busy then return false end
 if index>#jobs then stopped=true;emit('END',fingerprint);return true end
 local job=jobs[index];index=index+1;busy=true
 ExecuteInGameThread(function()
  if stopped then return end
  if os.time()>=deadline then busy=false;stop('queued job expired');return end
  emit('JOB_BEGIN',job.key..'|'..job.id..'|'..job.path)
  local job_deadline=math.min(deadline,os.time()+4)
  local nodes,refs,trees=0,0,0
  local function guard()
   assert(not stopped and os.time()<job_deadline,'subtree inspection deadline')
  end
  local ok,why=pcall(function()
   local asset=LoadAsset(job.path);guard()
   assert(path(asset)==job.path and asset:IsA('/Script/CoreUObject.Class'),'exact ability class required')
   local defaults=asset:GetCDO()
   assert(valid(defaults)and defaults:IsA('/Script/SGameAI.RunSubtreeAbility'),'subtree CDO required')
   local tree_seen={}
   defaults.ComboTreeWithWeight:ForEach(function(key,value)
    guard();trees=trees+1;assert(trees<=32,'tree map bound exceeded')
    local tree=key:get();local tree_path=path(tree)
    assert(tree:IsA('/Script/AIModule.BehaviorTree'),'behavior tree required')
    assert(not tree_seen[tree_path],'duplicate tree map key');tree_seen[tree_path]=true
    local weight=value:get()
    assert(type(weight)=='number'and weight==weight and math.abs(weight)<math.huge,'finite map weight required')
    local tag=job.key..'|'..trees..'|'
    emit('TREE',tag..tree_path..'|'..tostring(weight))
    local seen,tn,tr,te={},0,0,0
    local function inspect(node)
     guard();assert(valid(node),'tree node unavailable')
     local name=fullname(node);local node_path=path(node)
     assert(node_path:sub(1,#tree_path+1)==tree_path..':','foreign tree node')
     if seen[name]then return end
     seen[name]=true;tn=tn+1;nodes=nodes+1;batch_nodes=batch_nodes+1
     assert(tn<=128 and nodes<=256 and batch_nodes<=4096,'tree node bound exceeded')
     emit('NODE',tag..name)
     local cls=node:GetClass();local depth,properties=0,0;local names={}
     while valid(cls)do
      guard();depth=depth+1;assert(depth<=16,'node lineage bound exceeded')
      cls:ForEachProperty(function(prop)
       guard();properties=properties+1;assert(properties<=128,'node property bound exceeded')
       local declaration=prop:GetFullName()
       if declaration:match('^ClassProperty ')then
        local property=prop:GetFName():ToString()
        if property=='AbilityToActivate'and not names[property]then
         names[property]=true;local object=node[property]
         if valid(object)then
          assert(object:IsA('/Script/CoreUObject.Class'),'ability reference must be a native class')
          tr=tr+1;refs=refs+1;batch_refs=batch_refs+1
          assert(refs<=1024 and batch_refs<=16384,'node reference bound exceeded')
          emit('REF',tag..name..'|'..property..'|'..fullname(object))
         end
        end
       end
      end)
      cls=cls:GetSuperStruct()
     end
     if node:IsA('/Script/AIModule.BTCompositeNode')then
      local child_index=0
      node.Children:ForEach(function(_,item)
       guard();child_index=child_index+1;assert(child_index<=128,'child list bound exceeded')
       local child=item:get()
       for _,kind in ipairs({'ChildTask','ChildComposite'})do
        local object=child[kind]
        if valid(object)then
         te=te+1;assert(te<=256,'tree edge bound exceeded')
         emit('EDGE',tag..name..'|'..fullname(object)..'|'..kind..'|'..child_index)
         inspect(object)
        end
       end
      end)
     end
    end
    inspect(tree.RootNode)
    emit('TREE_END',tag..tn..'|'..tr..'|'..te)
   end)
   guard();emit('JOB_END',job.key..'|'..trees)
  end)
  if not ok then emit('REJECTED',job.key..'|'..tostring(why):gsub('[%c|]',' '):sub(1,1024))end
  busy=false
 end)
 return false
end)
