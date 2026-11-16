local root=assert(arg[1]);local module=dofile(root..'/tools/phantom_boss_host.lua')
local checks=0
local function check(name,fn) fn();checks=checks+1;print('PASS '..name) end
local function engine()
    local e={now=1,handles={},cancelled={},revokes={},started=0}
    local function obj(address,name,path)
        local o={address=address,name=name,path=path,valid=true}
        function o:IsValid()return self.valid end
        function o:GetAddress()return self.address end
        function o:GetFullName()return self.name end
        function o:GetClass()return {IsValid=function()return true end,GetFullName=function()return 'BlueprintGeneratedClass '..self.path end}end
        function o:GetWorld()return self.world end
        return o
    end
    e.world=obj(100,'World /Game/Map.Map','/Script/Engine.World')
    e.pc=obj(1,'PC /Game/Map.Map:PersistentLevel.PC_0','/Game/PC.PC_C')
    e.pawn=obj(2,'Player /Game/Map.Map:PersistentLevel.Player_0','/Game/Player.Player_C')
    e.pc.world,e.pawn.world=e.world,e.world
    function e.pc:K2_GetPawn()return e.pawn end
    function e.pawn:GetController()return e.pc end
    e.api={getPlayer1=function()return e.pc,e.pawn end,link={now=function()return e.now end},log=function()end,
        coop={net={enabled=true}}}
    e.launch={mode='two-player-online-research',session='research',exe_sha256=string.rep('a',64),
        catalog_sha256=string.rep('b',64),expires_at=os.time()+300,native_player_class=e.pawn.path,
        revoke_control=function(why)e.revokes[#e.revokes+1]=why end}
    e.g={LoopInGameThreadWithDelay=function(ms,fn)
        assert(ms==100);e.started=e.started+1;e.handles[e.started]=fn;return e.started
    end,CancelDelayedAction=function(handle)e.cancelled[handle]=(e.cancelled[handle]or 0)+1 end}
    e.host=module.new(e.api,e.launch,e.g)
    return e
end
check('engine snapshot binds local controller, Pawn and actual UWorld identity',function()
    local e=engine();local snapshot=e.host.snapshot()
    assert(snapshot.body.address==2 and snapshot.controller.address==1 and snapshot.native_player)
    assert(snapshot.body.class=='/Game/Player.Player_C' and snapshot.world:find('|100|',1,true))
    assert(e.started==0)
end)
check('Boss class snapshot is not incorrectly marked native player',function()
    local e=engine();e.pawn.path='/Boss/Ahua.Ahua_C'
    assert(not e.host.snapshot().native_player)
end)
check('Pawn and controller readback mismatch are rejected',function()
    local e=engine();e.pawn.GetController=function()return e.pawn end
    assert(not pcall(e.host.snapshot))
    e=engine();e.pc.K2_GetPawn=function()return e.pc end;assert(not pcall(e.host.snapshot))
end)
check('invalid UObject, class and world mismatch are rejected',function()
    local e=engine();e.pawn.valid=false;assert(not pcall(e.host.snapshot))
    e=engine();e.pawn.GetClass=function()return nil end;assert(not pcall(e.host.snapshot))
    e=engine();e.pawn.world=e.pc;assert(not pcall(e.host.snapshot))
end)
check('world streaming name changes keep identity explicit and same-address new worlds differ',function()
    local e=engine();local old=e.host.snapshot().world;e.world.name='World /Game/NewMap.NewMap'
    assert(e.host.snapshot().world~=old)
end)
check('lease mutation and expired lease stop snapshots but permit restoration callback',function()
    local e=engine();e.launch.expires_at=e.launch.expires_at+100;assert(not pcall(e.host.snapshot))
    e.host.on_revoke('expired');assert(#e.revokes==1)
    e=engine();e.launch.session='another';assert(not pcall(e.host.snapshot))
end)
check('game-thread timer is explicitly cancelled once on stop and on user cancellation',function()
    local e=engine();local n=0
    local cancel=e.host.schedule(100,function()n=n+1;return true end)
    e.handles[1]();e.handles[1]();cancel();assert(n==1 and e.cancelled[1]==1)
    e=engine();cancel=e.host.schedule(100,function()error('should not run')end)
    cancel();e.handles[1]();assert(e.cancelled[1]==1 and #e.revokes==0)
end)
check('callback failure cancels the timer and requests restoration',function()
    local e=engine();e.host.schedule(100,function()error('callback failed')end)
    e.handles[1]();e.handles[1]();assert(e.cancelled[1]==1 and #e.revokes==1 and not e.api.coop.net.enabled)
end)
check('nonfinite native clock and missing restoration contract are rejected',function()
    local e=engine();e.now=math.huge;assert(not pcall(e.host.now))
    e=engine();e.launch.revoke_control=nil;assert(not pcall(module.new,e.api,e.launch,e.g))
    e=engine();e.launch.native_player_class=nil;assert(not pcall(module.new,e.api,e.launch,e.g))
end)
print('PASS '..checks..' host groups; fake UObjects and scheduler, no engine execution')
