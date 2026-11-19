-- Native stance lifecycle for development assemblies. No grants, tag edits or damage overrides.
-- An NPC counter stance may end after each impact. Re-arm only while held, with native checks.
local Defense={};Defense.__index=Defense
local function finite(v)return type(v)=='number'and v==v and math.abs(v)<math.huge end
function Defense.new(adapter,options)
    assert(type(adapter)=='table','defense adapter required')
    for _,name in ipairs({'context','active','activate','release','cancel'})do
        assert(type(adapter[name])=='function','defense adapter missing '..name)
    end
    options=options or{}
    local interval=options.retry_seconds or .1
    assert(finite(interval)and interval>=.05 and interval<=.5,'bounded defense retry interval required')
    return setmetatable({adapter=adapter,interval=interval,held=false,armed=false,owned=false,
        release_pending=false,release_notified=false,next_try=0,last_time=nil,identity=nil,attempts=0},Defense)
end
function Defense:context()
    local c=self.adapter.context()
    assert(type(c)=='table'and finite(c.now)and type(c.identity)=='string'and c.identity~='',
        'current defense context required')
    assert(c.same_world==true,'stale defense world rejected')
    if self.identity then assert(c.identity==self.identity,'defense participant changed')end
    if self.last_time then assert(c.now>=self.last_time,'defense clock moved backwards')end
    self.last_time=c.now
    return c
end
function Defense:idle()
    local active=self.adapter.active()
    assert(type(active)=='boolean','native stance activity unreadable')
    return not active
end
function Defense:release(reason)
    self.held=false;self.armed=false
    if not self.owned then self.identity=nil;return true end
    self:context() -- Never use a previous World or participant's release receipt.
    self.release_pending=true -- Preserve cleanup responsibility if native release raises.
    if not self.release_notified then
        assert(self.adapter.release(reason)==true,'native stance release rejected')
        self.release_notified=true
    end
    if not self:idle()then assert(self.adapter.cancel(reason)==true,'native stance cancellation rejected')end
    assert(self:idle(),'stance remains active after release')
    self.owned=false;self.release_pending=false;self.release_notified=false;self.identity=nil
    return true
end
function Defense:step(input)
    assert(type(input)=='table'and type(input.down)=='boolean','sampled defense key required')
    local c=self:context()
    if input.allowed~=true or c.allowed~=true then
        self:release('input suspended');return false,'suspended'
    end
    if not input.down then self:release('key released');self.armed=true;return true,'idle'end
    if not self.held then
        self.held=true
        -- Focus recovery / takeover while RMB is held must wait for an observed release.
        if not self.armed then return false,'release key to arm'end
        self.identity=c.identity;self.next_try=c.now
    end
    if not self.armed then return false,'release key to arm'end
    if self.release_pending then self:release('cleanup retry');return false,'cleanup pending'end
    if not self:idle()then
        return true,self.owned and'holding'or'pre-existing stance untouched'
    end
    -- A natural native end is not a stuck key. Holding permits the next native check.
    self.owned=false
    if c.busy==true then return false,'combat action active'end
    if c.now<self.next_try then return true,'waiting'end
    self.next_try=c.now+self.interval;self.attempts=self.attempts+1
    -- Record responsibility before activation: exceptions may occur after native mutation.
    self.owned=true
    local accepted=self.adapter.activate()
    assert(type(accepted)=='boolean','native stance activation unreadable')
    if not accepted then
        assert(self:idle(),'rejected activation changed native stance activity')
        self.owned=false;return false,'native conditions rejected'
    end
    return true,'activation requested'
end
function Defense:blocks_action()
    -- Held input takes priority even when the native counter window has not opened yet.
    return self.held and self.armed or self.owned or self.release_pending
end
return Defense
