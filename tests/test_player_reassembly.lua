local root,candidate=assert(arg[1]),assert(arg[2])
package.path=candidate..'/PBZBossControl/Scripts/?.lua;'..package.path
local Reassembly=require('player_reassembly')
local old={running=true};local current=old
local queue={};local writes=0
local api={current=function()return current end,defer=function(delay,fn)
    assert(delay==250);queue[#queue+1]=fn;return #queue end}
local function replace()
    -- This stands for restoring/stopping the old runtime and destroying its actors.
    assert(current==old and old.running)
    writes=writes+1;old.running=false;current={running=true}
end
Reassembly.schedule(api,old,replace)
-- A synchronous pre-LoadMap cleanup runs before the queued selection callback.
old.running=false;local next_runtime={running=true};current=next_runtime
queue[1]()
assert(writes==0 and current==next_runtime and current.running,
    'queued old-World selection must not touch new assembly')
old.running=true;current=old
Reassembly.schedule(api,old,replace)
old.running=false;queue[2]()
assert(writes==0,'retired runtime must remain inert even before pointer replacement')
old.running=true
Reassembly.schedule(api,old,replace);queue[3]()
assert(writes==1 and current~=old,'current live selection must still reassemble once')
queue[3]()
assert(writes==1,'already executed selection must not retire its replacement')
assert(not pcall(Reassembly.schedule,api,old,replace),'stale requests must fail before scheduling')
print('PASS queued selection vs synchronous map cleanup; stopped owner; live switch; duplicate delivery')
