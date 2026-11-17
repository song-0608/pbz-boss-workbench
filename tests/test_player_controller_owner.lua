local root,candidate=assert(arg[1]),assert(arg[2])
package.path=root..'/tools/?.lua;'..candidate..'/PBZBossControl/Scripts/?.lua;'..package.path
local Owner=require('player_controller_owner');local Calls=require('ue_calls')
local function fixture()
    local f={now=100,scans=0,objects={},serial=0}
    function f:object(class)
        self.serial=self.serial+1;local address=self.serial
        local o={alive=true,name=class..' /Fixture.'..address}
        function o:IsValid()return self.alive end
        function o:GetFullName()return self.name end
        function o:GetAddress()return address end
        function o:GetClass()return{GetFullName=function()return'Class '..class end}end
        function o:IsA(expected)return expected==class end
        self.objects[o.name:match('^[^ ]+ (.+)$')]=o
        return o
    end
    f.engine=f:object('/Script/Engine.GameEngine');f.viewport=f:object('/Script/Engine.GameViewportClient')
    f.instance=f:object('/Script/Engine.GameInstance');f.player=f:object('/Script/Engine.LocalPlayer')
    f.pc=f:object('/Script/ProjectPBZ.PBZPlayerController')
    f.world=f:object('/Script/Engine.World');f.pawn=f:object('/Script/Engine.Pawn')
    function f:set_pc(pc)
        self.pc=pc;self.pc.Pawn=self.pawn;self.pc.Player=self.player
        self.pc.name='/Script/ProjectPBZ.PBZPlayerController /Fixture:PersistentLevel.PC'..self.serial
        self.objects[self.pc.name:match('^[^ ]+ (.+)$')]=self.pc
        self.pc.K2_GetPawn=function()return self.pawn end
        self.pc.GetWorld=function()return self.world end
        self.pawn.GetWorld=function()return self.world end
        self.pawn.GetController=function()return self.pc end
        self.player.PlayerController=self.pc
    end
    f:set_pc(f.pc)
    f.players={f.player};function f.players:GetArrayNum()return #self end
    f.engine.GameViewport=f.viewport;f.engine.GameInstance=f.instance;f.viewport.GameInstance=f.instance
    f.instance.LocalPlayers=f.players;f.player.ViewportClient=f.viewport;f.player.PlayerController=f.pc;f.pc.Player=f.player
    f.engines={f.engine}
    f.api={now=function()return f.now end,usable=function(o)return o.alive end,
        find_exact=function(path)return f.objects[path]end,
        find_all=function(class)assert(class=='GameEngine','must not enumerate world controllers');f.scans=f.scans+1;return f.engines end}
    f.owner=Owner.new(Calls.new(f.api),f.api)
    return f
end
local f=fixture()
for _=1,1000 do assert(f.owner:get()==f.pc);f.now=f.now+1 end
assert(f.scans==1,'steady gameplay must not perform a global census once a second')
local old=f.pc;f:set_pc(f:object('/Script/ProjectPBZ.PBZPlayerController'))
assert(old.alive and f.owner:get()==f.pc and f.scans==1,'travel must follow live LocalPlayer, even while old PC survives')
f.players[2]=f.player;local pc,count=f.owner:get();assert(not pc and count==2,'ambiguous local players must be refused')
f.players[2]=nil;f.pc.Player=nil;assert(not pcall(f.owner.get,f.owner),'broken reciprocal ownership must fail closed')
f.pc.Player=f.player
f.player.ViewportClient=f:object('/Script/Engine.GameViewportClient');assert(not pcall(f.owner.get,f.owner))
f.player.ViewportClient=f.viewport;f.viewport.GameInstance=f:object('/Script/Engine.GameInstance')
assert(not pcall(f.owner.get,f.owner));f.viewport.GameInstance=f.instance
f.pc.alive=false;assert(f.owner:get()==nil);f.pc.alive=true
f.owner:invalidate();assert(f.owner:get()==f.pc and f.scans==1,'pre/post invalidation retains only checked engine identity')
f.engine.name='Engine /Reused';assert(not pcall(f.owner.get,f.owner),'cached process engine identity reuse must be refused')
f=fixture();f.engines={}
for _=1,1000 do assert(f.owner:get()==nil)end
assert(f.scans==1,'startup negative engine census must be bounded')
f.engines={f.engine};assert(f.owner:get()==nil)
f.owner:invalidate();assert(f.owner:get()==f.pc and f.scans==2)
f=fixture();f.engines={f.engine,f.engine};pc,count=f.owner:get();assert(not pc and count==2)
f=fixture();f.players.GetArrayNum=function()return 5 end;assert(not pcall(f.owner.get,f.owner))
f=fixture();f.api.usable=function()return 'unknown'end;assert(not pcall(f.owner.get,f.owner))
f=fixture();f.engine.IsA=function()return 'unknown'end;assert(not pcall(f.owner.get,f.owner))
-- Production Query wiring keeps reciprocal possession and World validation.
f=fixture();local query=require('player_controller_query').new(Calls.new(f.api),f.api,true)
for _=1,1000 do assert(query:get()==f.pc);f.now=f.now+1 end
assert(f.scans==1)
old=f.pc;f:set_pc(f:object('/Script/ProjectPBZ.PBZPlayerController'))
f.world=f:object('/Script/Engine.World');assert(old.alive and query:get()==f.pc and f.scans==1)
f.pawn.GetWorld=function()return f:object('/Script/Engine.World')end
assert(not pcall(query.get,query),'owner lookup cannot skip pawn/controller World equality')
print('PASS current engine/viewport/local-player ownership, no recurring global census, live PC replacement and ambiguity/identity refusals')
