local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Guard=require('map_travel_guard')
local function fixture()
    local f={events={},allowed=true,same=true};local s={state='ACTIVE',receipt={world={name='old',address=1}},current_skill='skill'}
    f.runtime={session=s,running=true}
    function s:restore(reason)f.events[#f.events+1]='restore:'..reason;self.state='OFF';self.receipt=nil;self.current_skill=nil;return true end
    function f.runtime:report(label,ok,why)f.events[#f.events+1]=label..':'..tostring(ok)..':'..why end
    f.guard=Guard.new({runtime=function()return f.runtime end,attest=function()assert(f.allowed,'expired')end,
        same_world=function()return f.same end,log=function(k,v)f.events[#f.events+1]=k..':'..tostring(v)end})
    return f
end
local f=fixture();assert(f.guard:before({})==nil);assert(f.runtime.session.state=='OFF')
assert(f.events[2]=='restore:map travel'and f.events[3]=='auto_exit:true:map travel'and f.events[4]=='MAP_TRAVEL_RESTORED_BEFORE_LOAD:true')
f=fixture();f.same=false;assert(not pcall(f.guard.before,f.guard,{}));assert(f.runtime.session.receipt and #f.events==0)
f=fixture();f.allowed=false;assert(not pcall(f.guard.before,f.guard,{}));assert(#f.events==0)
f=fixture();f.runtime.session.receipt=nil;assert(f.guard:before({})==nil and #f.events==0)
f=fixture();f.runtime.running=false;assert(f.guard:before({})==nil and #f.events==0)
f=fixture();function f.runtime.session:restore()return false,'cancel rejected'end
assert(not pcall(f.guard.before,f.guard,{}));assert(f.events[#f.events]=='auto_exit:false:cancel rejected')
print('PASS travel pre-hook synchronous restoration, current World, lease, idle, stopped runtime and restoration failures')
