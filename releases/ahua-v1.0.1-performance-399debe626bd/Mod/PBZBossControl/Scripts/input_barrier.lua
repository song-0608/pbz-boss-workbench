-- 用途：在本Mod自建镜头Actor上压入空的高优先级输入层，阻止原主角同时出招。
-- 原主角的InputComponent和映射完全不改；退出只移除本Mod的输入层。
local Barrier={};Barrier.__index=Barrier
function Barrier.new(calls,native,binding)
    assert(binding and binding.binding_verified,'verified input barrier declarations required')
    for _,name in ipairs({'empty','enable','verify','disable'})do assert(type(native[name])=='function','barrier adapter missing '..name)end
    return setmetatable({calls=calls,native=native},Barrier)
end
function Barrier:attach(pc,owner,receipt)
    assert(not receipt.input_barrier,'input barrier already attached')
    assert(self.native.empty(owner),'only a fresh owned actor may receive a barrier')
    local t={pc=self.calls:reference(pc),owner=self.calls:reference(owner),mutated=true}
    receipt.input_barrier=t -- 用途：先记录清理句柄，即使EnableInput中途失败也可移除。
    self.native.enable(owner,pc)
    if owner.InputComponent and owner.InputComponent:IsValid()then t.component=self.calls:reference(owner.InputComponent)end
    assert(self:verify(t),'fresh input barrier did not verify');return true
end
function Barrier:verify(t)
    return t and t.mutated and not t.removed and self.native.verify(self.calls:resolve(t.owner))==true
end
function Barrier:detach(t)
    if not t or t.removed then return true end
    self.native.disable(self.calls:resolve(t.owner),self.calls:resolve(t.pc))
    t.removed=true;return true
end
return Barrier
