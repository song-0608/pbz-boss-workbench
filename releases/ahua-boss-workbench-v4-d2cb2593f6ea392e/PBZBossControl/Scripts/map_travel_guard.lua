-- 用途：引擎LoadMap开始前同步恢复本轮接管；不能把异步按键队列当作旅行前恢复。
local Guard={};Guard.__index=Guard
function Guard.new(api)
    for _,key in ipairs({'runtime','attest','same_world','log'})do assert(type(api[key])=='function','travel guard API missing '..key)end
    return setmetatable({api=api},Guard)
end
function Guard:before(world)
    local runtime=self.api.runtime()
    if not runtime or not runtime.running or not runtime.session.receipt then return end
    self.api.attest()
    local session=runtime.session
    assert(session.state=='ACTIVE','travel requires current active receipt')
    local receipt=session.receipt
    assert(self.api.same_world(world,receipt.world),'LoadMap current World differs from captured receipt')
    self.api.log('MAP_TRAVEL_PRE_ACTIVE',receipt.world.name..'|address='..receipt.world.address..'|skill='..tostring(session.current_skill))
    local restored,why=session:restore('map travel')
    runtime:report('auto_exit',restored,restored and'map travel'or why)
    assert(restored and session.state=='OFF'and not session.receipt,'travel restoration not verified')
    self.api.log('MAP_TRAVEL_RESTORED_BEFORE_LOAD',true)
end
return Guard
