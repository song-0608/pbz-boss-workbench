local root,candidate=assert(arg[1]),assert(arg[2])
package.path=candidate..'/PBZBossControl/Scripts/?.lua;'..package.path
local callbacks,cancelled,serial={},{},0
local scope=require('player_assembly_tasks').new(function(_,fn)
    serial=serial+1;callbacks[serial]=fn;return serial
end,function(handle)cancelled[handle]=true end)
local old,new,cleanup=0,0,0
scope:defer(100,function()old=old+1;scope:defer(100,function()old=old+1 end)end)
scope:defer(600000,function()cleanup=cleanup+1;scope:retire()end)
callbacks[1]();assert(old==1)
local queued=callbacks[3]
scope:retire()
scope:defer(100,function()new=new+1 end)
callbacks[1]();callbacks[2]();queued()
assert(old==1 and cleanup==0 and new==0 and cancelled[2]and cancelled[3],
    'old observations and cleanup must not touch the next assembly')
callbacks[4]();callbacks[4]();assert(new==1,'completed observations must not repeat')
scope:defer(100,function()scope:retire();cleanup=cleanup+1 end)
callbacks[5]();assert(cleanup==1,'a cleanup callback can retire its own scope')

local failed_callback,cancels
cancels=0
local failed=require('player_assembly_tasks').new(function(_,fn)
    failed_callback=fn;error('native scheduling failed')
end,function(handle)assert(handle~=nil);cancels=cancels+1 end)
assert(not pcall(failed.defer,failed,100,function()error('failed registration must remain inert')end))
assert(next(failed.pending)==nil,'registration failure must not retain a nil-handle token')
failed_callback();failed:retire();assert(cancels==0)
local missing=require('player_assembly_tasks').new(function(_,fn)failed_callback=fn end,
    function()error('missing handle must not be cancelled')end)
assert(not pcall(missing.defer,missing,100,function()error('missing-handle callback must remain inert')end))
failed_callback();missing:retire();assert(next(missing.pending)==nil)

local waiting,cancelled_all={},{}
local cancel_failure=require('player_assembly_tasks').new(function(_,fn)
    waiting[#waiting+1]=fn;return #waiting
end,function(handle)
    cancelled_all[handle]=true
    error('native cancellation failed for '..handle)
end)
for _=1,3 do cancel_failure:defer(100,function()error('retired callback must be inert even if cancel failed')end)end
assert(not pcall(cancel_failure.retire,cancel_failure),'cancellation errors must remain visible')
assert(cancelled_all[1]and cancelled_all[2]and cancelled_all[3],
    'one cancellation failure must not skip the remaining native handles')
for _,callback in ipairs(waiting)do callback()end
assert(next(cancel_failure.pending)==nil)

local racing,raced,race_cancelled
racing=require('player_assembly_tasks').new(function(_,fn)
    raced=fn;racing:retire();return 99
end,function(handle)assert(handle==99);race_cancelled=true end)
racing:defer(100,function()error('retirement during registration must stay inert')end)
raced();assert(race_cancelled and next(racing.pending)==nil)
for _,delay in ipairs({0/0,math.huge,-1})do
    assert(not pcall(scope.defer,scope,delay,function()end),'invalid timer delay must be refused')
end
print('PASS stale camera/skill observations and cleanup are cancelled and inert after assembly retirement')
print('PASS failed registration, reentrant retirement and cancellation failure cannot strand live callbacks')
