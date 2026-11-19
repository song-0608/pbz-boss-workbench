-- Fixed native helper ABI. The helper only observes this process's game window/RMB.
local Input={};Input.__index=Input
function Input.new(g,pid,gate)
    assert(type(g.PBZNativeCombatInputSnapshot)=='function'and math.type(pid)=='integer'and pid>0
        and type(gate)=='function','verified native helper, PID and session gate required')
    return setmetatable({read_native=g.PBZNativeCombatInputSnapshot,pid=pid,gate=gate,last_time=nil},Input)
end
function Input:snapshot()
    local r=self.read_native()
    assert(type(r)=='table'and r.schema==1 and r.pid==self.pid and type(r.allowed)=='boolean'
        and type(r.down)=='boolean'and type(r.now)=='number'and r.now==r.now
        and r.now>=0 and r.now<math.huge,'native input snapshot ABI or process mismatch')
    assert(not r.down or r.allowed,'background native key rejected')
    if self.last_time then assert(r.now>=self.last_time,'native monotonic clock moved backwards')end
    self.last_time=r.now
    return r
end
function Input:read(receipt,key)
    assert(key=='RIGHT_MOUSE_BUTTON','native defense helper supports only the fixed RMB binding')
    local r=self:snapshot()
    local allowed=r.allowed and self.gate(receipt)==true
    return{allowed=allowed,down=allowed and r.down,now=r.now}
end
function Input:allowed(receipt)
    local r=self:snapshot();return r.allowed and self.gate(receipt)==true
end
function Input:now()return self:snapshot().now end
return Input
