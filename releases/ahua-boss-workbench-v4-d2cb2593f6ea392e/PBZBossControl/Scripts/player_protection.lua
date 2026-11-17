-- 用途：遥控Boss时把原主角暂时隐藏、关闭碰撞和移动、关闭受伤标志；不写生命值或存档。
-- 只允许原主角静止且存活时进入。任一状态或生命值变动立即报告失败，不用补血掩盖伤害。
local Guard={};Guard.__index=Guard
function Guard.new(calls,binding)
    assert(binding and binding.binding_verified,'player protection declarations required')
    return setmetatable({calls=calls},Guard)
end
function Guard:capture(player)
    local velocity=player:GetVelocity()
    assert(velocity.X^2+velocity.Y^2+velocity.Z^2<4,string.format('stop moving before entering boss control; velocity=%.6f,%.6f,%.6f',velocity.X,velocity.Y,velocity.Z))
    local movement=player.CharacterMovement;local health=player.AttributeSetBase.Health.CurrentValue
    local position=player:K2_GetActorLocation()
    assert(type(health)=='number'and health>0,'living player required')
    return{player=self.calls:reference(player),movement=self.calls:reference(movement),
        health=health,position={X=position.X,Y=position.Y,Z=position.Z},hidden=player.bHidden,damage=player.bCanBeDamaged,collision=player:GetActorEnableCollision(),
        mode=movement.MovementMode,custom=movement.CustomMovementMode,mutations={}}
end
function Guard:apply(t)
    local p,m=self.calls:resolve(t.player),self.calls:resolve(t.movement)
    t.mutations.movement=true;m:DisableMovement();t.frozen_mode=m.MovementMode
    t.mutations.collision=true;p:SetActorEnableCollision(false)
    t.mutations.hidden=true;p:SetActorHiddenInGame(true)
    t.mutations.damage=true;p.bCanBeDamaged=false
    assert(self:verify(t),'player protection did not verify');return true
end
function Guard:verify(t)
    local p,m=self.calls:resolve(t.player),self.calls:resolve(t.movement)
    local pos=p:K2_GetActorLocation();local delta=(pos.X-t.position.X)^2+(pos.Y-t.position.Y)^2+(pos.Z-t.position.Z)^2
    if delta>4 then
        if not t.position_failure_logged then print('PBZ_PLAYER_PROTECTION:POSITION_CHANGED='..math.sqrt(delta)..'\n');t.position_failure_logged=true end
        return false
    end
    return p.bHidden==true and p.bCanBeDamaged==false and p:GetActorEnableCollision()==false
        and m.MovementMode==t.frozen_mode and p.AttributeSetBase.Health.CurrentValue==t.health
end
function Guard:restore(t)
    if t.restored then return true end
    local p,m=self.calls:resolve(t.player),self.calls:resolve(t.movement);local errors={}
    local function attempt(name,fn)
        local ok,why=pcall(fn);if ok then t.mutations[name]=nil else errors[#errors+1]=tostring(why)end
    end
    if t.mutations.collision then attempt('collision',function()p:SetActorEnableCollision(t.collision)end)end
    if t.mutations.hidden then attempt('hidden',function()p:SetActorHiddenInGame(t.hidden)end)end
    if t.mutations.damage then attempt('damage',function()p.bCanBeDamaged=t.damage end)end
    if t.mutations.movement then attempt('movement',function()m:SetMovementMode(t.mode,t.custom)end)end
    assert(#errors==0,table.concat(errors,'; '))
    assert(p.bHidden==t.hidden and p.bCanBeDamaged==t.damage and p:GetActorEnableCollision()==t.collision
        and m.MovementMode==t.mode and m.CustomMovementMode==t.custom,'player protection restoration mismatch')
    assert(p.AttributeSetBase.Health.CurrentValue==t.health,'player health changed; before='..tostring(t.health)
        ..'; after='..tostring(p.AttributeSetBase.Health.CurrentValue)..'; do not overwrite or conceal damage')
    local pos=p:K2_GetActorLocation()
    assert((pos.X-t.position.X)^2+(pos.Y-t.position.Y)^2+(pos.Z-t.position.Z)^2<=4,
        'player position changed; do not conceal it with teleport or save rollback')
    t.restored=true;return true
end
return Guard
