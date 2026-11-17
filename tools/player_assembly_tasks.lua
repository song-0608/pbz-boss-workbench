-- Delayed observations may outlive LoadMap or role selection. Each callback
-- belongs to the current assembly epoch, even if native cancellation raced it.
local Tasks={};Tasks.__index=Tasks
function Tasks.new(defer,cancel)
    assert(type(defer)=='function'and type(cancel)=='function','assembly scheduler required')
    return setmetatable({schedule=defer,cancel=cancel,epoch=0,pending={}},Tasks)
end
function Tasks:defer(milliseconds,fn)
    assert(type(milliseconds)=='number'and milliseconds>=0 and type(fn)=='function','delayed assembly task required')
    local epoch=self.epoch
    local token={}
    self.pending[token]=true
    token.handle=self.schedule(milliseconds,function()
        if epoch~=self.epoch or not self.pending[token]then return end
        self.pending[token]=nil
        fn()
    end)
    return token.handle
end
function Tasks:retire()
    self.epoch=self.epoch+1
    local previous=self.pending
    self.pending={}
    -- Mark all callbacks inert before requesting native cancellation.
    for token in pairs(previous)do self.cancel(token.handle)end
end
return Tasks
