-- Time-based camera following for the developer 3C candidate. The accepted
-- release keeps its own frozen implementation. No scene-wide target search.
local Lock={};Lock.__index=Lock
local function finite(n)return type(n)=='number'and n==n and math.abs(n)<math.huge end
local function vector(p)return p and finite(p.X)and finite(p.Y)and finite(p.Z)end
local function angle(n)return(n+180)%360-180 end
function Lock.new(native)
    for _,name in ipairs({'target','eligible','position','rotation','set_rotation','same','frame_seconds'})do
        assert(type(native[name])=='function','target-lock adapter missing '..name)
    end
    return setmetatable({native=native,enabled=false,since_check=0},Lock)
end
function Lock:clear(reason)
    self.enabled=false;self.target=nil;self.since_check=0;self.reason=reason or'manual'
    return true
end
function Lock:toggle()
    if self.enabled then return self:clear('manual')end
    local ok,target=pcall(self.native.target)
    if not ok or not target then return false,'no verified combat target'end
    local eligible,allowed=pcall(self.native.eligible,target)
    if not eligible or allowed~=true then return false,'target is not eligible'end
    self.enabled=true;self.target=target;self.since_check=0;self.reason=nil
    return true
end
function Lock:update()
    if not self.enabled then return true end
    local ok,why=pcall(function()
        local dt=self.native.frame_seconds()
        assert(finite(dt)and dt>=0 and dt<=1,'target-lock frame duration unreadable')
        local target=assert(self.native.target(),'combat target unavailable')
        local changed=not self.native.same(target,self.target)
        self.since_check=self.since_check+dt
        if changed or self.since_check>=0.1-1e-9 then
            assert(self.native.eligible(target)==true,'target lost, dead, occluded or out of range')
            self.since_check=changed and 0 or self.since_check%0.1
            -- Floating-point rounding near exactly 100 ms must not cause an
            -- immediate second expensive eligibility check in the next frame.
            if self.since_check>0.1-1e-9 then self.since_check=0 end
        end
        local source,destination=self.native.position(target)
        assert(vector(source)and vector(destination),'target-lock position unreadable')
        local x,y,z=destination.X-source.X,destination.Y-source.Y,destination.Z-source.Z
        local horizontal=math.sqrt(x*x+y*y)
        assert(horizontal>1 and x*x+y*y+z*z<=3000^2,'target-lock distance rejected')
        local current=self.native.rotation()
        assert(current and finite(current.Yaw)and finite(current.Pitch),'target-lock rotation unreadable')
        if dt==0 then self.target=target;return end
        local desired_yaw=math.deg(math.atan(y,x))
        local desired_pitch=math.max(-60,math.min(20,math.deg(math.atan(z,horizontal))-8))
        -- Preserve the old 60 Hz response (25% correction, 8-degree cap),
        -- expressed per second so 30/60/120 Hz do not change its feel.
        local bounded_dt=math.min(dt,1/15)
        local alpha=1-0.75^(bounded_dt*60)
        local limit=480*bounded_dt
        local function approach(a,b)
            local delta=angle(b-a)*alpha
            return angle(a+math.max(-limit,math.min(limit,delta)))
        end
        local rotation={Yaw=approach(current.Yaw,desired_yaw),Pitch=approach(current.Pitch,desired_pitch),Roll=0}
        self.native.set_rotation(rotation);self.target=target
    end)
    if not ok then self:clear(tostring(why));return false,self.reason end
    return true
end
return Lock
