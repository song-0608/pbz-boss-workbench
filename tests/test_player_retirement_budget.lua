local root,candidate=assert(arg[1]),assert(arg[2])
package.path=candidate..'/PBZBossControl/Scripts/?.lua;'..package.path
local Calls,Boundary=require('ue_calls'),require('world_boundary')
local scans=0
local objects={}
local calls=Calls.new({find_exact=function()scans=scans+1;return nil end,
    find_all=function()scans=scans+1;return{}end,usable=function(o)return o.usable end})
local function object(index)
    local o={alive=true,usable=true}
    function o:IsValid()return self.alive end
    function o:GetFullName()return'Object /Old.'..index end
    function o:GetAddress()return index end
    function o:GetClass()return{GetFullName=function()return'Class /Fixture.Type'end}end
    objects[#objects+1]=o;return o
end
local world,pc=object(1),object(2)
function pc:GetWorld()return world end
local receipt={world=calls:reference(world),player_controller=calls:reference(pc),owned_world_objects={}}
for i=3,40 do receipt.owned_world_objects[#receipt.owned_world_objects+1]=calls:reference(object(i))end
assert(Boundary.inspect(calls,receipt,100)=='same'and scans==0)
pc.usable=false
assert(Boundary.inspect(calls,receipt,100)=='pending'and scans==0,
    'captured live wrappers and engine-invalid objects must not require global scans')
for _,o in ipairs(objects)do o.alive=false end
local baseline=scans
for _=1,1000 do assert(Boundary.inspect(calls,receipt,100.5)=='pending')end
assert(scans==baseline,'pending transition must not enumerate old objects every frame')
assert(Boundary.inspect(calls,receipt,101)=='retired')
-- Same-World results must never be cached as permission to continue playing.
local w,p={},{}
local valid=true
local immediate={optional=function(_,r)return valid and(r==receipt.world and w or p)or nil end,
    world=function()return receipt.world end}
assert(Boundary.inspect(immediate,receipt,200)=='same')
valid=false;assert(Boundary.inspect(immediate,receipt,200)=='retired')
-- A dead same-name replacement is not evidence that the old address is gone.
local original=object(99)
local exact=original
local collisions=Calls.new({find_exact=function()return exact end,
    find_all=function()return{original,exact}end,usable=function(o)return o.usable end})
local old=collisions:reference(original)
local replacement=object(99)
function replacement:GetAddress()return 100 end
exact=replacement;collisions:reference(replacement);replacement.alive=false
assert(collisions:retirement_optional(old)==original,'invalid replacement cannot dispose of a live old identity')
-- All cache reset paths must bound both registries across repeated assemblies.
for i=100,700 do collisions:reference(object(i))end
local cached=0;for _ in pairs(collisions.retirement_cache)do cached=cached+1 end
assert(cached<=256,'retirement wrapper registry must stay bounded')
print('PASS captured retirement avoids global scans; pending scans bounded to one per second; same state checked immediately')
