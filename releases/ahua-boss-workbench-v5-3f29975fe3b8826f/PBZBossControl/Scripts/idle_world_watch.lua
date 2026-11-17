-- 用途：退出接管后仍观察已登记World的退役；只读身份核验，不向新场景套用旧凭据。
local Watch={};Watch.__index=Watch
function Watch.new(calls,receipt,now)
    assert(type(now)=='function'and receipt.world and receipt.player_controller,'captured idle World required')
    return setmetatable({calls=calls,receipt=receipt,now=now,status='same'},Watch)
end
function Watch:poll(state)
    if state~='OFF'then return 'active'end
    if self.finished then return 'retired'end
    local now=self.now();assert(type(now)=='number'and now==now and math.abs(now)<math.huge,'idle clock unreadable')
    if self.checked_at and now<self.checked_at+1 then return self.status end
    self.checked_at=now
    self.status=require('world_boundary').inspect(self.calls,self.receipt)
    if self.status=='retired'then self.finished=true end
    return self.status
end
return Watch
