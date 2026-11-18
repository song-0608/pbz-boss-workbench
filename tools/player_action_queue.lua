-- Native key edges can wait for the game thread after focus/freshness checks.
-- Bound that second queue and discard expired work before any game mutation.
local Queue={};Queue.__index=Queue
local urgent={exit=true,menu_exit=true}
local function clock(api)
    local ok,now=pcall(api.now)
    if not ok or type(now)~='number'or now~=now or math.abs(now)==math.huge then return nil end
    return now
end
function Queue.new(api)
    for _,key in ipairs({'now','schedule','live'})do assert(type(api[key])=='function','action queue API missing '..key)end
    return setmetatable({api=api,pending={},count=0,epoch=0},Queue)
end
function Queue:retire()
    self.epoch=self.epoch+1;self.pending={};self.count=0;self.urgent_pending=false
end
function Queue:dispatch(label,fn)
    assert(type(label)=='string'and type(fn)=='function','named action required')
    if not self.api.live()then return false,'runtime stopped'end
    local at=clock(self.api)
    if not at then return false,'action clock unreadable'end
    if self.urgent_pending then return false,'restore already queued'end
    if urgent[label]then
        -- One restore may supersede up to 64 pending gameplay/menu actions.
        -- No further actions are admitted until it runs or the runtime retires.
        self:retire();self.urgent_pending=true
    elseif self.count>=64 then return false,'action queue full'end
    local epoch=self.epoch;local token={urgent=urgent[label]}
    self.pending[token]=true;self.count=self.count+1
    local function remove()
        if not self.pending[token]then return false end
        self.pending[token]=nil;self.count=self.count-1
        if token.urgent then self.urgent_pending=false end
        return true
    end
    local ok,why=pcall(self.api.schedule,function()
        if epoch~=self.epoch or not remove()then return end
        if not self.api.live()then return end
        local now=clock(self.api)
        -- os.time has whole-second resolution: accepted callbacks are younger
        -- than two wall-clock seconds. Backwards clock steps also reject input.
        if not now or now<at or now-at>=2 then return end
        fn()
    end)
    if not ok then remove();error(why,0)end
    return true
end
return Queue
