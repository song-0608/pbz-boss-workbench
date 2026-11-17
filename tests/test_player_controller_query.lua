local root,candidate=assert(arg[1]),assert(arg[2])
package.path=candidate..'/PBZBossControl/Scripts/?.lua;'..package.path
local Query=require('player_controller_query')
local Calls=require('ue_calls')
local now,scans=100,0
local function object(name,address,class)
    local o={name=name,address=address,class=class,alive=true}
    function o:IsValid()return self.alive end
    function o:GetFullName()return self.name end
    function o:GetAddress()return self.address end
    function o:GetClass()return{GetFullName=function()return self.class end}end
    return o
end
local world=object('World /Old.Old',1,'Class World')
local pc=object('PC /Old.Old:PersistentLevel.PC',2,'Class PC')
local pawn=object('Pawn /Old.Old:PersistentLevel.Pawn',3,'Class Pawn')
pc.Pawn=pawn
function pc:K2_GetPawn()return self.Pawn end
function pc:GetWorld()return world end
function pawn:GetController()return pc end
local objects={pc}
local api={now=function()return now end,find_all=function(class)
    assert(class=='PBZPlayerController');scans=scans+1;return objects end,
    find_exact=function(path)if path==pc.name:match('^[^ ]+ (.+)$')then return pc end end,
    usable=function(o)return o.alive end}
local q=Query.new(Calls.new(api),api)
for _=1,1000 do assert(q:get()==pc)end
assert(scans==1,'HUD, idle and key-release reads must share one census per second')
now=101;assert(q:get()==pc and scans==2)
pc.Pawn=nil;assert(q:get()==nil and scans==2,'invalid pawn must never escape cached controller validation')
pc.Pawn=pawn;assert(q:get()==nil and scans==2,'negative results must also be throttled')
now=102;assert(q:get()==pc and scans==3)
local original_name=pc.name;pc.name='PC /Reused:PersistentLevel.PC'
assert(not pcall(q.get,q),'cached name/address/class reuse must fail closed');pc.name=original_name
now=103;objects={pc,pc};local got,count=q:get()
assert(not got and count==2,'ambiguous gameplay controllers must not be selected')
now=104;objects={};got,count=q:get();assert(not got and count==0)
for _=1,1000 do assert(q:get()==nil)end
assert(scans==5,'loading without a controller must not scan every readiness/frame callback')
now=105;objects={pc};assert(q:get()==pc)
world=object('World /New.New',4,'Class World')
assert(q:get()==nil,'a cached controller with a changed World must not be reused')
now=106;assert(q:get()==pc)
print('PASS controller census shared and bounded; negative loading cache; full identity and possession validation; World change rejection')
