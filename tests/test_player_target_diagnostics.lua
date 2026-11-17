local root,candidate=assert(arg[1]),assert(arg[2])
package.path=candidate..'/PBZBossControl/Scripts/?.lua;'..package.path
local old_print=print
local events={}
print=function(line)events[#events+1]=line end
local function target(name,address)
    return{IsValid=function()return true end,GetFullName=function()return name end,
        GetAddress=function()return address end}
end
local soft,hard=target('Pawn /Target',1),target('Pawn /Hard',2)
local reads=0
local actor={GetLockingTarget=function(_,ignore_soft)
    reads=reads+1;if ignore_soft then return hard else return soft end
end}
local g={StaticFindObject=function()return{IsValid=function()return true end}end}
local native=require('ue_combat').new(g,{binding_verified=true,diagnostic=true})
for _=1,1000 do assert(native.target_actor(actor)==soft)end
assert(reads==2000 and #events==1,'log suppression must never replace native live target reads')
soft=target('Pawn /Target',3);native.target_actor(actor)
assert(#events==2,'same name with changed address must produce a fresh diagnostic')
soft=nil;native.target_actor(actor);native.target_actor(actor);assert(#events==3)
hard=nil;native.target_actor(actor);assert(#events==4,'hard-target change must not be hidden')
local other={GetLockingTarget=actor.GetLockingTarget};native.target_actor(other);assert(#events==5)
native=require('ue_combat').new(g,{binding_verified=true,diagnostic=false})
local before=reads;native.target_actor(actor)
assert(reads==before+1 and #events==5,'ordinary control must not add diagnostic reads or writes')
print=old_print
print('PASS repeated target diagnostics deduplicated; live reads, identity changes and independent actors preserved')
