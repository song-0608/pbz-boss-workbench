-- One short input request, scoped to the exact live control receipt. Never
-- finishes/cancels an ability, ignores cooldowns, or retries a native rejection.
local Buffer={}
local function finite(n)return type(n)=='number'and n==n and math.abs(n)<math.huge end
function Buffer.attach(session,options)
    assert(type(options.now)=='function'and finite(options.ttl)and options.ttl>=0 and options.ttl<=0.25,
        'bounded input buffer clock required')
    function session:clear_buffered_skill()self.buffered_skill=nil end
    local restore,boundary=session.restore,session.world_boundary
    function session:restore(...)self:clear_buffered_skill();return restore(self,...)end
    function session:world_boundary(...)
        local status,why=boundary(self,...)
        if status~='same'then self:clear_buffered_skill()end
        return status,why
    end
    function session:request_skill(slot)
        self:clear_buffered_skill() -- a fresh key replaces, never duplicates, a queued request
        if self.state~='ACTIVE'or not self.receipt then return false,'not controlling a boss'end
        if not self.current_skill or options.ttl==0 then return self:skill(slot)end
        local definition=(self.config.skills or{})[slot]
        if not definition or definition.verified~=true or self.pending_target then return false,'skill not bufferable'end
        if self:world_boundary()~='same'then return false,'world transition'end
        local now=options.now();if not finite(now)then return false,'input clock unreadable'end
        self.buffered_skill={slot=slot,receipt=self.receipt,world=self.world_id,at=now,expires=now+options.ttl}
        self:record('input buffered: '..slot)
        return false,'input buffered; waiting for native completion'
    end
    function session:flush_buffered_skill()
        local item=self.buffered_skill;if not item then return true end
        local now=options.now()
        if not finite(now)or now<item.at or now>=item.expires or self.state~='ACTIVE'
            or self.receipt~=item.receipt or self.world_id~=item.world or self.pending_target then
            self:clear_buffered_skill();return true
        end
        if self.current_skill then return true end
        self:clear_buffered_skill() -- one attempt; native rejection is never automatically retried
        local ok,why=self:skill(item.slot)
        self:record('buffered input '..(ok and'started: 'or'rejected: ')..item.slot..'|'..tostring(why or''))
        if options.on_result then options.on_result(item.slot,ok,why)end
        return true
    end
    return session
end
return Buffer
