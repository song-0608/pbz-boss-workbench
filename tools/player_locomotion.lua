-- Reversible walking-only tuning. No position writes, time dilation, velocity
-- teleports, cooldown edits, or changes to another actor's movement component.
local Motion={};Motion.__index=Motion
local function finite(n)return type(n)=='number'and n==n and math.abs(n)<math.huge end
local function angle(n)return(n+180)%360-180 end
function Motion.new(calls,native,settings,log)
    assert(native.binding_verified==true,'current-process locomotion declarations required')
    for _,name in ipairs({'read','write','yaw','face','frame_seconds'})do
        assert(type(native[name])=='function','locomotion adapter missing '..name)
    end
    assert(log==nil or type(log)=='function','optional movement event sink required')
    return setmetatable({calls=calls,native=native,settings=settings,log=log},Motion)
end
function Motion:capture(boss)
    local state=self.native.read(boss)
    assert(finite(state.speed)and state.speed>0 and finite(state.acceleration)and state.acceleration>0,
        'native walking limits not ready')
    return{boss=self.calls:reference(boss),initial=state,applied=false,restored=false}
end
local function same(a,b)return math.abs(a.speed-b.speed)<0.01 and math.abs(a.acceleration-b.acceleration)<0.01 end
function Motion:suspend(ticket)
    assert(not ticket.restored,'locomotion ticket retired')
    if not ticket.applied then return true end
    local boss=self.calls:resolve(ticket.boss)
    local current=self.native.read(boss);local restore,contested={},{}
    -- A two-field native write may fail after changing only one field. Recover
    -- each owned value independently, and still reject any unrelated mutation.
    for _,field in ipairs({'speed','acceleration'})do
        if math.abs(current[field]-ticket.written[field])<0.01 then restore[field]=ticket.before[field]
        elseif math.abs(current[field]-ticket.before[field])>=0.01 then contested[#contested+1]=field end
    end
    if next(restore)then self.native.write(boss,restore)end
    assert(#contested==0,'walking limits changed outside owned override: '..table.concat(contested,','))
    assert(same(self.native.read(boss),ticket.before),'walking restoration mismatch')
    ticket.applied=false
    if self.log then self.log('WALK_RESTORED',ticket.before.speed..'|'..ticket.before.acceleration)end
    return true
end
function Motion:step(ticket,x,y,scale)
    assert(not ticket.restored,'locomotion ticket retired')
    local boss=self.calls:resolve(ticket.boss)
    if not ticket.applied then
        local before=self.native.read(boss)
        assert(finite(before.speed)and before.speed>0 and finite(before.acceleration)and before.acceleration>0,
            'native walking limits unavailable')
        local desired=math.max(before.speed,math.min(self.settings.walk_speed_cm_s,before.speed*3))
        ticket.before=before;ticket.written={speed=desired,
            acceleration=math.max(before.acceleration,math.min(desired*4,before.acceleration*4))}
        ticket.applied=true -- register recovery before the first native write
        self.native.write(boss,ticket.written)
        assert(same(self.native.read(boss),ticket.written),'native walking limit write did not verify')
        if self.log then self.log('WALK_LIMITS',before.speed..'->'..desired..'|acceleration='
            ..before.acceleration..'->'..ticket.written.acceleration..'|turn_rate='..self.settings.turn_rate_degrees_s)end
    end
    assert(same(self.native.read(boss),ticket.written),'native walking limit write contested')
    local dt=self.native.frame_seconds(boss)
    assert(finite(dt)and dt>=0 and dt<=1,'native frame duration unreadable')
    if x*x+y*y>0.000001 and scale~=0 and dt>0 then
        local yaw=self.native.yaw(boss);assert(finite(yaw),'native facing unreadable')
        local target=math.deg(math.atan(y,x))+(scale<0 and 180 or 0)
        local limit=self.settings.turn_rate_degrees_s*math.min(dt,1/15)
        local delta=math.max(-limit,math.min(limit,angle(target-yaw)))
        self.native.face(boss,angle(yaw+delta))
    end
    return true
end
function Motion:restore(ticket,disposed)
    if ticket.restored then return true end
    if disposed then assert(not self.calls:optional(ticket.boss),'disposed locomotion owner remains usable')
    else self:suspend(ticket)end
    ticket.restored=true;return true
end
return Motion
