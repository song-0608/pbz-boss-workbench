local root,candidate=assert(arg[1]),assert(arg[2])
package.path=candidate..'/PBZBossControl/Scripts/?.lua;'..package.path
local Map=require('player_map_lifecycle')
local Tasks=require('player_assembly_tasks')
local function world(id)return{name='World /Map'..id,address=id,class='Class World'}end
local function fixture()
    local f={events={},timers={},serial=0,restored=0,cleaned=0,resumed=0,mutations=0}
    f.tasks=Tasks.new(function(_,fn)f.serial=f.serial+1;f.timers[f.serial]=fn;return f.serial end,function()end)
    f.api={attest=function()assert(not f.expired,'expired grant')end,
        reference=function(w)return w end,
        invalidate=function()f.events[#f.events+1]='invalidate'end,
        suspend=function()
            f.tasks:retire()
            if f.active then f.restored=f.restored+1;f.active=false end
            assert(not f.cleanup_failed,'cleanup not verified')
            f.cleaned=f.cleaned+1
        end,
        resume=function()
            f.resumed=f.resumed+1
            f.tasks:defer(1000,function()f.mutations=f.mutations+1 end)
        end,
        log=function(key)f.events[#f.events+1]=key end}
    f.map=Map.new(f.api)
    return f
end
local f=fixture();f.active=true
f.tasks:defer(250,function()error('old initialization callback ran')end)
local stale=f.timers[1]
f.map:before(world(1));stale()
assert(f.restored==1 and f.cleaned==1 and f.map:suspended()and not f.map:ready(world(2)))
assert(f.resumed==0,'a new World before post is not native load completion')
f.map:after(world(2),'')
assert(f.resumed==1 and not f.map:suspended()and not f.map:ready(world(1))and f.map:ready(world(2)))
stale();f.timers[2]();assert(f.mutations==1)

f=fixture();f.map:before(world(1));f.map:after(world(1),'native travel cancelled')
assert(f.map:ready(world(1))and f.resumed==1 and f.map.native_error~='',
    'cancelled travel must return to normal readiness in the unchanged World')
f=fixture();f.map:before(world(1));f.map:after(world(1),'')
assert(f.map:ready(world(1))and f.resumed==1,'same-address reload must not wait forever for a different World')

f=fixture();f.map:after(world(2),'');assert(f.resumed==0)
f.map:before(world(1));f.map:before(world(1));f.map:after(world(2),'')
assert(f.resumed==0 and f.map:suspended(),'nested loads cannot resume before the outer post')
f.map:after(world(3),'');assert(f.resumed==1 and f.map:ready(world(3)))
local old_resume=f.timers[1]
f.map:before(world(3));old_resume();assert(f.mutations==0,'second travel cancels queued reassembly')
f.map:after(nil,'');assert(f.resumed==2 and f.map:ready(world(4)))

f=fixture();f.cleanup_failed=true
assert(not pcall(f.map.before,f.map,world(1)))
f.map:after(world(2),'');assert(f.map:suspended()and f.resumed==0,'cleanup failure must never authorize reassembly')
f=fixture();f.map:before(world(1));f.expired=true
assert(not pcall(f.map.after,f.map,world(2),''));assert(f.resumed==0 and f.map:suspended())

f=fixture();local pre,post
local g={RegisterLoadMapPreHook=function(fn)pre=fn end,RegisterLoadMapPostHook=function(fn)post=fn end}
f.map=Map.attach(g,f.api)
assert(pre(nil,{Get=function()return world(1)end})==nil)
assert(post(nil,{Get=function()return world(2)end},nil,nil,'')==nil)
assert(f.map:ready(world(2))and f.resumed==1,'native hook adapters must preserve engine result')
assert(not pcall(Map.attach,{RegisterLoadMapPreHook=function()error('partial registration')end},f.api))
print('PASS pre/post World transaction, same-World cancellation, nested loads, old callbacks, cleanup/grant refusal and native hook signatures')
