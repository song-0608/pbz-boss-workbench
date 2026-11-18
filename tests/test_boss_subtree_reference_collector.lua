-- Execute the actual generated outer collector and every inner probe offline.
local script,jobs_file,mode=assert(arg[1]),assert(arg[2]),arg[3]or'ok'
local jobs=assert(loadfile(jobs_file))();local paths={}
for _,job in ipairs(jobs)do paths[job.lookup_path]=true end
local loops,queue,events,loaded={},{},{},{}
local clock,max_pending=100,0
local env=setmetatable({}, {__index=_G});env._G=env
env.os={time=function()return clock end}
env.print=function(value)events[#events+1]=value end
env.LoopAsync=function(ms,fn)assert(ms==100);loops[#loops+1]={fn=fn}end
env.ExecuteInGameThread=function(fn)
    queue[#queue+1]=fn;max_pending=math.max(max_pending,#queue)
    assert(#queue==1,'multiple native metadata callbacks pending')
end
env.LoadAsset=function(path)
    assert(paths[path],'unrequested class load');loaded[#loaded+1]=path
    if mode=='unavailable'then return nil end
    local asset={}
    function asset:IsValid()return true end
    function asset:GetFullName()return 'Class '..(mode=='wrong_identity'and'/Wrong.Class'or path)end
    function asset:IsA(kind)return kind=='/Script/CoreUObject.Class'end
    function asset:GetCDO()return {
        IsValid=function()return true end,
        IsA=function(_,kind)return kind=='/Script/GameplayAbilities.GameplayAbility'
            or kind=='/Script/SGameAI.RunSubtreeAbility'and mode=='subtree'end}
    end
    return asset
end
-- Any gameplay action accidentally added to the collector must fail the fixture.
for _,name in ipairs({'SpawnActor','Possess','TryActivateAbilityByClass','GiveAbility','FindAllOf'})do
    env[name]=function()error('unexpected gameplay operation: '..name)end
end
local file=assert(io.open(script,'rb'));local body=file:read('*a');file:close()
assert(load(body,'exact-reference-fixture','t',env))()
assert(#loaded==0 and #queue==0,'query must wait for the scheduler')
local function tick()
    local count=#loops
    for i=1,count do local item=loops[i];if not item.done then item.done=item.fn()end end
end
if mode=='expired'or mode=='frozen_clock'then
    tick();tick();assert(#queue==1 and #loaded==0)
    if mode=='expired'then clock=581 end
    for _=1,4802 do tick()end
    for _,callback in ipairs(queue)do callback()end
    assert(#loaded==0,'late native callback ran after stop')
    local log=table.concat(events,'\n')
    assert(log:find('PBZ_FULL_CATALOG:STOP=',1,true))
    assert(not log:find('PBZ_FULL_CATALOG:END=',1,true))
else
    for _=1,#jobs*4+20 do
        if #queue>0 then table.remove(queue,1)()end
        tick()
    end
    assert(#loaded==#jobs and #queue==0)
    for i,path in ipairs(loaded)do assert(path==jobs[i].lookup_path,'native query order changed')end
    assert(table.concat(events):find('PBZ_FULL_CATALOG:END=',1,true))
end
assert(max_pending==1)
for _,event in ipairs(events)do print(event)end
print('PASS generated reference collector: '..mode)
