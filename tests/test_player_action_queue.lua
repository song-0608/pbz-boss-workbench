local root,candidate=assert(arg[1]),assert(arg[2])
package.path=candidate..'/PBZBossControl/Scripts/?.lua;'..package.path
local Queue=require('player_action_queue')
local function fixture()
    local f={now=100,live=true,queued={},runs=0}
    f.queue=Queue.new({now=function()return f.now end,live=function()return f.live end,
        schedule=function(fn)f.queued[#f.queued+1]=fn end})
    f.run=function()f.runs=f.runs+1 end
    return f
end
local f=fixture()
assert(f.queue:dispatch('attack',f.run));f.queued[1]();f.queued[1]()
assert(f.runs==1 and f.queue.count==0,'one native callback cannot repeat its action')
for _,now in ipairs({102,200,99,0/0,math.huge})do
    f=fixture();assert(f.queue:dispatch('attack',f.run));f.now=now
    f.queued[1]();assert(f.runs==0 and f.queue.count==0,'expired or uncertain clock must discard the queued action')
end
f=fixture();assert(f.queue:dispatch('attack',f.run));f.now=101.99;f.queued[1]();assert(f.runs==1)
f=fixture();f.now=0/0;assert(not f.queue:dispatch('attack',f.run)and #f.queued==0)
f=fixture();f.live=false;assert(not f.queue:dispatch('attack',f.run)and #f.queued==0)
f=fixture();f.queue:dispatch('attack',f.run);f.live=false;f.queued[1]();assert(f.runs==0)
f=fixture()
for _=1,10000 do f.queue:dispatch('attack',f.run)end
assert(#f.queued==64 and f.queue.count==64,'a stalled game thread must have a bounded input queue')
local restored=0
assert(f.queue:dispatch('exit',function()restored=restored+1 end))
for _=1,1000 do
    assert(not f.queue:dispatch('attack',f.run))
    assert(not f.queue:dispatch('exit',f.run))
    assert(not f.queue:dispatch('menu_exit',f.run))
end
assert(#f.queued==65 and f.queue.count==1,'one restore supersedes gameplay without building another backlog')
for _,callback in ipairs(f.queued)do callback()end
assert(f.runs==0 and restored==1 and f.queue.count==0 and not f.queue.urgent_pending)
assert(f.queue:dispatch('attack',f.run));f.queued[66]();assert(f.runs==1)

f=fixture();f.queue:dispatch('attack',f.run);f.queue:retire()
f.queue:dispatch('attack',f.run);f.queued[1]();f.queued[2]()
assert(f.runs==1 and f.queue.count==0,'retired runtime work must not run if the same runtime starts again')
local failed_callback
f=fixture();f.queue.api.schedule=function(fn)failed_callback=fn;error('native dispatch rejected')end
assert(not pcall(f.queue.dispatch,f.queue,'attack',f.run))
failed_callback();assert(f.queue.count==0 and f.runs==0,'failed native registration must leave an inert closure')

-- Execute the real patched Runtime rather than only testing its helper.
local Runtime=require('runtime')
local function runtime_fixture(implementation)
    local r={now=100,keys={},queued={},mutations=0}
    local b={context=function()return{isolated=true,offline=true,exe_sha256='fixture',world_id='one',boss_available=true}end,
        capture=function()return{}end,take_control=function()r.mutations=r.mutations+1;return true end,
        verify_control=function()return true end,can_start_skill=function()return true end,
        start_skill=function()return'token'end,is_skill_finished=function()return true end,
        cancel_skills=function()return true end,restore=function()return true end,verify_restored=function()return true end}
    local host={action_time=function()return r.now end,on_game_thread=function(fn)r.queued[#r.queued+1]=fn end,
        bind_key=function(key,fn)r.keys[key]=fn end,every_frame=function()return 1 end,
        cancel_frame=function()end,read_input=function()return{}end,log=function()end}
    r.runtime=(implementation or Runtime).new(b,{expected_exe_sha256='fixture',controls={enter='F6',exit='F10'},skills={}},host)
    r.runtime:start();return r
end
local r=runtime_fixture();r.keys.F6();r.now=103;r.queued[1]()
assert(r.mutations==0 and r.runtime.session.state=='OFF','real runtime must discard stale takeover before capture/possession')
local original=assert(loadfile(root..'/releases/ahua-boss-workbench-v5-3f29975fe3b8826f/PBZBossControl/Scripts/runtime.lua'))()
local baseline=runtime_fixture(original);baseline.keys.F6();baseline.now=103;baseline.queued[1]()
assert(baseline.mutations==1 and baseline.runtime.session.state=='ACTIVE',
    'negative control must reproduce stale takeover in the unchanged original runtime')
r=runtime_fixture();r.keys.F6();r.keys.F10()
for _,callback in ipairs(r.queued)do callback()end
assert(r.mutations==0 and r.runtime.session.state=='OFF','restore pressed during a stall must supersede an earlier queued takeover')
r=runtime_fixture();r.keys.F6();r.runtime:stop('test');r.runtime:start();r.queued[1]()
assert(r.mutations==0,'stop/start cannot revive an old input action')
r.keys.F6();r.queued[2]();assert(r.mutations==1 and r.runtime.session.state=='ACTIVE')
print('PASS bounded pending input, stale/backwards/unreadable clock, restore priority, epoch retirement and failed registration')
print('PASS actual Runtime rejects stale takeover, superseded enter and callbacks queued before stop/start')
