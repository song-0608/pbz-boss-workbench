-- 用途：核对阵营事务、目标校验与精确组件恢复；夹具通过不代表实机伤害通过。
local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Combat=require('combat_identity');local count=0
local function fixture()
    local f={}
    f.player={tag='Faction.Player'};f.boss={tag='Faction.Enemy'};f.target={tag='Faction.Enemy'}
    f.mesh={owner=f.target};f.boss.target=f.target;f.boss.socket='head';f.boss.component=f.mesh
    local calls={reference=function(_,o)return o end,resolve=function(_,o)assert(not o.dead,'dead reference');return o end,
        same=function(_,a,b)return a==b end,world=function(_,o)return{name='world',address=o.other_world and 2 or 1}end}
    local n={faction_component=function(a)return a end,read_faction=function(a)return a.tag end,
        set_faction=function(a,tag)a.tag=tag;if f.fail_write then f.fail_write=false;error('partial native failure')end end,
        relation=function(a,b)return a.tag==b.tag and 0 or 2 end,target_component=function(a)return a end,
        read_target=function(a)return a.target,a.socket,a.component end,
        set_target=function(a,target,socket,component)a.target=target;a.socket=socket;a.component=component or target.root;return not f.reject end,
        clear_target=function(a)if f.fail_clear then error('injected clear failure')end;a.target=nil;a.component=nil end,target_actor=function(a)return f.wrong_query and f.player or a.target end}
    f.service=Combat.new(calls,n,{binding_verified=true,friendly=0,hostile=2})
    f.ticket=f.service:capture(f.player,f.boss)
    return f
end
local function test(name,fn)local ok,why=pcall(fn);assert(ok,name..': '..tostring(why));count=count+1;print('PASS '..name)end
test('capture does not mutate',function()local f=fixture();assert(f.boss.tag=='Faction.Enemy'and f.boss.component==f.mesh)end)
test('faction roundtrip and exact mesh snapshot',function()local f=fixture();f.service:apply(f.ticket);assert(f.service:verify(f.ticket));f.service:restore(f.ticket);assert(f.boss.tag=='Faction.Enemy'and f.boss.component==f.mesh and f.boss.socket=='head'and f.ticket.restored)end)
test('partial native write remains restorable',function()local f=fixture();f.fail_write=true;assert(not pcall(function()f.service:apply(f.ticket)end));assert(f.ticket.mutated);assert(f.service:restore(f.ticket))end)
test('self target rejected',function()local f=fixture();f.service:apply(f.ticket);assert(not pcall(function()f.service:set_target(f.ticket,f.boss)end))end)
test('saved player rejected',function()local f=fixture();f.service:apply(f.ticket);assert(not pcall(function()f.service:set_target(f.ticket,f.player)end))end)
test('cross world rejected',function()local f=fixture();f.service:apply(f.ticket);f.target.other_world=true;assert(not pcall(function()f.service:set_target(f.ticket,f.target)end))end)
test('friendly target rejected',function()local f=fixture();f.service:apply(f.ticket);f.target.tag='Faction.Player';assert(not pcall(function()f.service:set_target(f.ticket,f.target)end))end)
test('native lock refusal rejected',function()local f=fixture();f.service:apply(f.ticket);f.reject=true;assert(not pcall(function()f.service:set_target(f.ticket,f.target)end))end)
test('ability query disagreement blocks target',function()local f=fixture();f.service:apply(f.ticket);f.wrong_query=true;assert(not pcall(function()f.service:set_target(f.ticket,f.target)end));assert(not f.service:verify_target(f.ticket))end)
test('hostile selected target revalidated',function()local f=fixture();f.service:apply(f.ticket);assert(f.service:set_target(f.ticket,f.target));assert(f.service:verify_target(f.ticket));f.target.tag='Faction.Player';assert(not f.service:verify_target(f.ticket))end)
test('dead target rejected on revalidation',function()local f=fixture();f.service:apply(f.ticket);f.service:set_target(f.ticket,f.target);f.target.dead=true;assert(not pcall(function()f.service:verify_target(f.ticket)end))end)
test('failed target cleanup still attempts faction restoration',function()local f=fixture();f.service:apply(f.ticket);f.fail_clear=true;assert(not pcall(function()f.service:restore(f.ticket)end));assert(f.boss.tag=='Faction.Enemy'and not f.ticket.restored)end)
test('asynchronous request alone is not a verified ability target',function()local f=fixture();f.service:apply(f.ticket);f.wrong_query=true;assert(f.service:request_target(f.ticket,f.target));assert(not f.service:verify_target(f.ticket));f.wrong_query=false;assert(f.service:verify_target(f.ticket))end)
print('combat identity checks passed: '..count)
