-- Execute the generated Arena entry: hooks precede its first timer, and native
-- load cancels a begin call already queued after stationary-health readiness.
local root,candidate=assert(arg[1]),assert(arg[2])
package.path=candidate..'/PBZBossControl/Scripts/?.lua;'..package.path
local file=assert(io.open(candidate..'/PBZBossControl/Scripts/owned_arena.lua','rb'))
local source=file:read('*a');file:close()
assert(not source:find('ExecuteInGameThreadWithDelay%('),'all setup/settle/retry observations must use the epoch')
local f={now=100000,queue={},cancelled={},serial=0,loads=0,logs={},pre_count=0,post_count=0}
local function object(name,address,class)
    local o={}
    function o:IsValid()return true end
    function o:GetFullName()return name end
    function o:GetAddress()return address end
    function o:GetClass()return{GetFullName=function()return class end}end
    function o:IsA(expected)return self.native_class==expected end
    return o
end
local world=object('World /Old.Old',1,'Class World')
local pc=object('PC /Old.Old:PersistentLevel.PC',2,'Class PC')
local player=object('Pawn /Old.Old:PersistentLevel.Player',3,'Class Pawn')
player.AttributeSetBase={Health={CurrentValue=100}}
function player:GetWorld()return world end
function player:GetVelocity()return{X=0,Y=0,Z=0}end
function player:GetController()return pc end
pc.Pawn=player
function pc:GetWorld()return world end
function pc:K2_GetPawn()return player end
pc.native_class='/Script/ProjectPBZ.PBZPlayerController'
local engine=object('Engine /Transient.Engine',4,'Class GameEngine');engine.native_class='/Script/Engine.GameEngine'
local viewport=object('Viewport /Transient.Viewport',5,'Class Viewport');viewport.native_class='/Script/Engine.GameViewportClient'
local instance=object('GI /Transient.Instance',6,'Class GI');instance.native_class='/Script/Engine.GameInstance'
local local_player=object('LP /Transient.LocalPlayer',7,'Class LP');local_player.native_class='/Script/Engine.LocalPlayer'
engine.GameViewport=viewport;engine.GameInstance=instance;viewport.GameInstance=instance
instance.LocalPlayers={local_player};function instance.LocalPlayers:GetArrayNum()return #self end
local_player.ViewportClient=viewport;local_player.PlayerController=pc;pc.Player=local_player
local function schedule(ms,fn)
    f.serial=f.serial+1;f.queue[#f.queue+1]={id=f.serial,ms=ms,fn=fn};return f.serial
end
local env=setmetatable({
    os={time=function()return math.floor(f.now)end},
    print=function(s)f.logs[#f.logs+1]=s end,
    ExecuteInGameThreadWithDelay=schedule,CancelDelayedAction=function(id)f.cancelled[id]=true end,
    RegisterLoadMapPreHook=function(fn)f.pre=fn;f.pre_count=f.pre_count+1 end,
    RegisterLoadMapPostHook=function(fn)f.post=fn;f.post_count=f.post_count+1 end,
    FindAllOf=function(class)assert(class=='GameEngine','must not enumerate world controllers');return{engine}end,
    StaticFindObject=function()error('unexpected global lookup')end,
    LoadAsset=function()f.loads=f.loads+1;error('fixture stops before asset mutation')end,
},{__index=_G})
env._G=env
local arena=assert(load(source,'@candidate_owned_arena','t',env))()
local profile=require('boss_catalog').profile('057_wanjun')
arena.start({player_entry=true,boss_id='057_wanjun',attest=function()
    return{offline=true,isolated=true,expires_at=100600,exe_sha256=profile.exe_sha256}
end})
assert(f.pre and f.post and f.pre_count==1 and f.post_count==1 and #f.queue==1,
    'travel hooks must exist before the first readiness callback')
local steps=0
while f.queue[1]and f.queue[1].ms~=0 do
    local item=table.remove(f.queue,1);steps=steps+1;assert(steps<100)
    f.now=f.now+item.ms/1000;item.fn()
end
assert(f.queue[1]and f.queue[1].ms==0 and f.loads==0,'queued initialization must remain scoped')
local old_begin=table.remove(f.queue,1)
assert(f.pre(nil,{Get=function()return world end})==nil)
old_begin.fn();assert(f.loads==0 and f.cancelled[old_begin.id],
    'begin queued in old World must become inert before native loading')
assert(#f.queue==0,'pre-load must not poll/reassemble while the engine loads')
world=object('World /New.New',4,'Class World')
assert(f.post(nil,{Get=function()return world end},nil,nil,'')==nil)
assert(#f.queue==1 and f.queue[1].ms==1000)
steps=0
while #f.queue>0 do
    local item=table.remove(f.queue,1);steps=steps+1;assert(steps<100)
    f.now=f.now+item.ms/1000;item.fn()
end
assert(f.loads==1,'post-load still requires complete new gameplay readiness before assets')
assert(f.pre_count==1 and f.post_count==1,'reassembly must not accumulate native hooks')
print('PASS generated Arena installs hooks before readiness, cancels queued begin, waits for post and rechecks gameplay')
