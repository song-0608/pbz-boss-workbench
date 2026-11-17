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
print('PASS stale camera/skill observations and cleanup are cancelled and inert after assembly retirement')
