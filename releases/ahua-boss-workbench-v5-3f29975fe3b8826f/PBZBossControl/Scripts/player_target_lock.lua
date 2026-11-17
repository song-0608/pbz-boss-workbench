-- Camera lock follows only the already verified combat target; no scene-wide scan.
local Lock={};Lock.__index=Lock
local function finite(n)return type(n)=='number'and n==n and math.abs(n)<math.huge end
local function vector(p)return p and finite(p.X)and finite(p.Y)and finite(p.Z)end
local function angle(n)return(n+180)%360-180 end
function Lock.new(native)
    for _,name in ipairs({'target','eligible','position','rotation','set_rotation','same'})do
        assert(type(native[name])=='function','target-lock adapter missing '..name)
    end
    return setmetatable({native=native,enabled=false,checks=0},Lock)
end
function Lock:clear(reason)
    self.enabled=false;self.target=nil;self.checks=0;self.reason=reason or'manual'
    return true
end
function Lock:toggle()
    if self.enabled then return self:clear('manual')end
    local ok,target=pcall(self.native.target)
    if not ok or not target then return false,'no verified combat target'end
    local eligible,allowed=pcall(self.native.eligible,target)
    if not eligible or allowed~=true then return false,'target is not eligible'end
    self.enabled=true;self.target=target;self.checks=0;self.reason=nil
    return true
end
function Lock:update()
    if not self.enabled then return true end
    local ok,why=pcall(function()
        local target=assert(self.native.target(),'combat target unavailable')
        local changed=not self.native.same(target,self.target)
        self.checks=self.checks+1
        if changed or self.checks>=6 then
            assert(self.native.eligible(target)==true,'target lost, dead, occluded or out of range')
            self.checks=0
        end
        local source,destination=self.native.position(target)
        assert(vector(source)and vector(destination),'target-lock position unreadable')
        local x,y,z=destination.X-source.X,destination.Y-source.Y,destination.Z-source.Z
        local horizontal=math.sqrt(x*x+y*y)
        assert(horizontal>1 and x*x+y*y+z*z<=3000^2,'target-lock distance rejected')
        local current=self.native.rotation()
        assert(current and finite(current.Yaw)and finite(current.Pitch),'target-lock rotation unreadable')
        local desired_yaw=math.deg(math.atan(y,x))
        local desired_pitch=math.max(-60,math.min(20,math.deg(math.atan(z,horizontal))-8))
        local function approach(a,b)
            local delta=angle(b-a)
            return angle(a+math.max(-8,math.min(8,delta*0.25)))
        end
        local rotation={Yaw=approach(current.Yaw,desired_yaw),Pitch=approach(current.Pitch,desired_pitch),Roll=0}
        self.native.set_rotation(rotation);self.target=target
    end)
    if not ok then self:clear(tostring(why));return false,self.reason end
    return true
end
return Lock
