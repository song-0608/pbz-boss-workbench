-- 用途：验证原主角临时保护与逐项恢复；生命值永远只读，不补血掩盖失败。
local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local G=require('player_protection');local count=0
local function fixture()
    local p={bHidden=false,bCanBeDamaged=true,collision=true,AttributeSetBase={Health={CurrentValue=500}}}
    local m={MovementMode=1,CustomMovementMode=0}
    function m:DisableMovement()self.MovementMode=0 end
    function m:SetMovementMode(mode,custom)self.MovementMode=mode;self.CustomMovementMode=custom end
    p.CharacterMovement=m
    p.position={X=0,Y=0,Z=0}
    function p:K2_GetActorLocation()return self.position end
    function p:GetVelocity()return{X=self.speed or 0,Y=0,Z=0}end
    function p:GetActorEnableCollision()return self.collision end
    function p:SetActorEnableCollision(value)self.collision=value;if self.fail then self.fail=false;error('partial collision failure')end end
    function p:SetActorHiddenInGame(value)self.bHidden=value end
    local calls={reference=function(_,x)return x end,resolve=function(_,x)return x end}
    return{player=p,movement=m,guard=G.new(calls,{binding_verified=true})}
end
local function test(name,fn)local ok,why=pcall(fn);assert(ok,name..':'..tostring(why));count=count+1;print('PASS '..name)end
test('protect and restore exact original states',function()local f=fixture();local t=f.guard:capture(f.player);f.guard:apply(t);assert(f.guard:verify(t));assert(f.movement.MovementMode==0 and not f.player.collision);f.guard:restore(t);assert(f.player.collision and not f.player.bHidden and f.player.bCanBeDamaged and f.movement.MovementMode==1)end)
test('partial protection remains restorable',function()local f=fixture();local t=f.guard:capture(f.player);f.player.fail=true;assert(not pcall(function()f.guard:apply(t)end));assert(f.guard:restore(t));assert(f.player.collision and f.movement.MovementMode==1)end)
test('moving original player rejected before mutation',function()local f=fixture();f.player.speed=20;assert(not pcall(function()f.guard:capture(f.player)end));assert(f.player.collision and f.movement.MovementMode==1)end)
test('dead original player rejected',function()local f=fixture();f.player.AttributeSetBase.Health.CurrentValue=0;assert(not pcall(function()f.guard:capture(f.player)end))end)
test('preexisting hidden state preserved',function()local f=fixture();f.player.bHidden=true;local t=f.guard:capture(f.player);f.guard:apply(t);f.guard:restore(t);assert(f.player.bHidden)end)
test('health change rejected without writing health',function()local f=fixture();local t=f.guard:capture(f.player);f.guard:apply(t);f.player.AttributeSetBase.Health.CurrentValue=400;assert(not f.guard:verify(t));assert(not pcall(function()f.guard:restore(t)end));assert(f.player.AttributeSetBase.Health.CurrentValue==400 and f.player.collision)end)
test('position drift is detected and never teleported back',function()
    local f=fixture();local t=f.guard:capture(f.player);f.guard:apply(t);f.player.position.X=20
    assert(not f.guard:verify(t));assert(not pcall(f.guard.restore,f.guard,t));assert(f.player.position.X==20 and f.player.collision)
end)
print('Player protection fixtures: '..count..' passed; game damage handling requires runtime evidence.')
