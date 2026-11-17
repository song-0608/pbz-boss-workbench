-- Poll once per second. Detect the current gameplay World before reading old actors.
-- A changed World requests cleanup; it never declares old objects disposed.
local Watch={};Watch.__index=Watch
local function same(a,b)
    return a and b and a.name==b.name and a.address==b.address and a.class==b.class
end
function Watch.new(calls,receipt,now,current_world)
    assert(type(now)=='function'and receipt.world and receipt.player_controller,'captured idle World required')
    assert(current_world==nil or type(current_world)=='function','current World reader required')
    return setmetatable({calls=calls,receipt=receipt,now=now,current_world=current_world,status='same'},Watch)
end
function Watch:poll(state)
    if state~='OFF'then return 'active'end
    if self.finished then return 'retired'end
    local now=self.now();assert(type(now)=='number'and now==now and math.abs(now)<math.huge,'idle clock unreadable')
    if self.checked_at and now<self.checked_at+1 then return self.status end
    self.checked_at=now
    if self.current_world then
        local ok,current=pcall(self.current_world)
        if not ok or not current then self.status='pending';return self.status end
        assert(type(current.name)=='string'and type(current.address)=='number'and type(current.class)=='string',
            'current World identity unreadable')
        if not same(current,self.receipt.world)then self.status='changed';return self.status end
    end
    self.status=require('world_boundary').inspect(self.calls,self.receipt)
    if self.status=='retired'then self.finished=true end
    return self.status
end
return Watch
