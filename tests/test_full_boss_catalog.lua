-- Run the sequential wrapper against two deterministic metadata batches.
local root=assert(arg[1]);local mode=arg[2]or'ok'
local stream=assert(io.open(root..'/tools/full_boss_catalog_probe.lua','rb'))
local body=stream:read('*a');stream:close()
local loops,queue,events,loads={}, {},{},{}
local clock=100
local env=setmetatable({}, {__index=_G})
env._G=env
env.os={time=function()return clock end}
env.print=function(value)events[#events+1]=value end
env.LoopAsync=function(ms,fn)assert(ms==100);loops[#loops+1]={fn=fn}end
env.ExecuteInGameThread=function(callback)queue[#queue+1]=callback end
env.LoadAsset=function(path)loads[#loads+1]=path;return{}end
local function source(key)
    return "print('PBZ_ADAPTER_META:START="..key.."');local sent=false;LoopAsync(100,function() "
        .."if sent then return true end;sent=true;ExecuteInGameThread(function() "
        .."LoadAsset('/Fixture/"..key..".Class');print('PBZ_ADAPTER_META:END="..key.."')end);return true end)"
end
local header="local fingerprint='outer';local budget_seconds=20;local batches={"
    .."{key='first',source="..string.format('%q',source('first')).."},"
    .."{key='second',source="..string.format('%q',source('second')).."}}\n"
assert(load(header..body,'catalog-fixture','t',env))()
local function tick()
    local count=#loops
    for i=1,count do local item=loops[i];if not item.done then item.done=item.fn()end end
end
tick();tick();assert(#queue==1 and #loads==0)
if mode=='expired'then
    clock=121;tick();queue[1]()
    assert(#loads==0 and table.concat(events):find('PBZ_FULL_CATALOG:STOP=',1,true))
    assert(not table.concat(events):find('PBZ_FULL_CATALOG:END=',1,true))
else
    for _=1,10 do
        if #queue>0 then table.remove(queue,1)()end
        tick()
    end
    local log=table.concat(events)
    assert(#loads==2 and loads[1]=='/Fixture/first.Class'and loads[2]=='/Fixture/second.Class')
    assert(log:find('PBZ_ADAPTER_META:END=first',1,true)<log:find('PBZ_ADAPTER_META:START=second',1,true))
    assert(log:find('PBZ_FULL_CATALOG:END=outer',1,true))
end
print('PASS sequential metadata collector: '..mode)
