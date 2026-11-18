-- Delayed observations may outlive LoadMap or role selection. Each callback
-- belongs to the current assembly epoch, even if native cancellation raced it.
local Tasks={};Tasks.__index=Tasks
function Tasks.new(defer,cancel)
    assert(type(defer)=='function'and type(cancel)=='function','assembly scheduler required')
    return setmetatable({schedule=defer,cancel=cancel,epoch=0,pending={}},Tasks)
end
function Tasks:defer(milliseconds,fn)
    assert(type(milliseconds)=='number'and milliseconds>=0 and milliseconds<math.huge
        and type(fn)=='function','delayed assembly task required')
    local epoch=self.epoch
    local token={}
    self.pending[token]=true
    local ok,handle=pcall(self.schedule,milliseconds,function()
        if epoch~=self.epoch or not self.pending[token]then return end
        self.pending[token]=nil
        token.completed=true
        fn()
    end)
    if not ok then self.pending[token]=nil;error(handle,0)end
    if handle==nil then self.pending[token]=nil;error('native timer handle missing',0)end
    token.handle=handle
    -- Retirement can occur while the native scheduler is returning its handle.
    -- A failed registration must never leave a nil handle in the cancel set.
    if epoch~=self.epoch and not token.completed then self.cancel(handle)end
    return handle
end
function Tasks:retire()
    self.epoch=self.epoch+1
    local previous=self.pending
    self.pending={}
    -- Mark all callbacks inert before requesting native cancellation.
    local errors={}
    for token in pairs(previous)do
        if token.handle~=nil then
            local ok,why=pcall(self.cancel,token.handle)
            if not ok then errors[#errors+1]=tostring(why)end
        end
    end
    assert(#errors==0,table.concat(errors,'; '))
end
return Tasks
