local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Layer=require('workbench_input')
local function fixture()
    local f={alive={},removed=0,destroyed=0}
    local calls={reference=function(_,o)return o end,retirement_optional=function(_,o)return f.alive[o]and o or nil end}
    local native={create=function()local owner={};f.alive[owner]=true;return owner end,
        finish=function()return true end,destroy=function(o)f.alive[o]=nil;f.destroyed=f.destroyed+1;return true end}
    local barrier={attach=function(_,pc,o,t)t.input_barrier={component={}};f.alive[t.input_barrier.component]=true;return true end,
        detach=function(_,t)if t then f.alive[t.component]=nil;f.removed=f.removed+1 end;return true end}
    f.layer=Layer.new(calls,barrier,native);f.native=native;return f
end
local f=fixture();assert(f.layer:lock({}));assert(not pcall(f.layer.lock,f.layer,{}))
assert(f.layer:unlock()and f.removed==1 and f.destroyed==1);assert(f.layer:unlock()and f.destroyed==1)
f=fixture();f.native.finish=function()error('partial spawn')end
assert(not pcall(f.layer.lock,f.layer,{}));assert(f.layer:unlock()and f.destroyed==1)
f=fixture();f.layer:lock({});local t=f.layer.ticket;f.alive[t.owner]=nil
assert(not pcall(f.layer.unlock,f.layer),'a surviving input component must prevent a retirement claim')
f.alive[t.input_barrier.component]=nil;assert(f.layer:unlock()and t.input_barrier.removed and f.removed==0)
f=fixture();f.layer:lock({});f.layer.ticket.owner.retirement_ambiguous=true
assert(not pcall(f.layer.unlock,f.layer)and f.destroyed==0,'ambiguous identity must not be destroyed')
f=fixture();f.layer:lock({});setmetatable(f.layer.ticket.owner,{__index=function()return function()end end})
assert(f.layer:unlock()and f.destroyed==1,'unknown reflected member must not be read as a Lua ambiguity sentinel')
print('PASS workbench input ownership, rollback, retirement and identity guards')
