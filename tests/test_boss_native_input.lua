local root=assert(arg[1]);package.path=root..'/tools/?.lua;'..package.path
local Input=require('boss_native_input')
local function fixture()
    local f={r={schema=1,pid=42,now=1,allowed=true,down=true},permitted=true}
    f.input=Input.new({PBZNativeCombatInputSnapshot=function()return f.r end},42,function()return f.permitted end)
    return f
end
local f=fixture();assert(f.input:read({},'RIGHT_MOUSE_BUTTON').down)
f.r.allowed=false;f.r.down=false;assert(not f.input:allowed({}))
assert(not f.input:read({},'RIGHT_MOUSE_BUTTON').down)
f.r.allowed=true;f.r.down=true;f.permitted=false;assert(not f.input:read({},'RIGHT_MOUSE_BUTTON').allowed)
assert(not pcall(f.input.read,f.input,{},'F1'))
for _,field in ipairs({'schema','pid','now','allowed','down'})do
    local x=fixture();x.r[field]=nil;assert(not pcall(x.input.snapshot,x.input))
end
local x=fixture();x.r.pid=43;assert(not pcall(x.input.snapshot,x.input))
x=fixture();x.r.allowed=false;assert(not pcall(x.input.snapshot,x.input))
x=fixture();assert(x.input:now()==1);x.r.now=.9;assert(not pcall(x.input.now,x.input))
print('PASS native helper ABI, fresh focus gating, fixed RMB, process identity and monotonic clock; no live key acceptance')
