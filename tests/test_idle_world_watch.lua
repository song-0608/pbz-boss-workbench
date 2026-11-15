local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Watch=require('idle_world_watch')
local clock,queries=100,0
local refs={world={name='World /Old',address=1,class='Class World'},
    player_controller={name='PC /Old.PC',address=2,class='Class PC'},
    owned_world_objects={{name='AI /Old.AI',address=3,class='Class AI'}}}
local world,pc,ai={},{},{}
local alive={[1]=world,[2]=pc,[3]=ai}
local calls={}
function calls:optional(ref)queries=queries+1;return alive[ref.address]end
function calls:world()return refs.world end
local watch=Watch.new(calls,refs,function()return clock end)
assert(watch:poll('ACTIVE')=='active'and queries==0)
assert(watch:poll('OFF')=='same');local count=queries
assert(watch:poll('OFF')=='same'and queries==count)
clock=101;alive[1],alive[2]=nil,nil
assert(watch:poll('OFF')=='pending','surviving owned controller must block reassembly')
clock=102;alive[3]=nil
assert(watch:poll('OFF')=='retired'and watch.finished)
count=queries;clock=103;assert(watch:poll('OFF')=='retired'and queries==count)
local bad=Watch.new({optional=function()error('identity reused')end},refs,function()return clock end)
assert(not pcall(bad.poll,bad,'OFF')and not bad.finished)
print('PASS idle scene disposal waits for all owned objects, bounds queries and rejects ambiguous identity')
