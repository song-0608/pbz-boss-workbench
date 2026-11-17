-- Gameplay routes retain the native loader's focus and per-key edge checks.
-- Register bare and Shift variants explicitly; never treat Ctrl/Alt chords as skills.
local Input={};Input.__index=Input
local routers=setmetatable({},{__mode='k'})
function Input.new(g)
    assert(type(g.RegisterKeyBind)=='function'and type(g.Key)=='table','native key router required')
    local router=routers[g]
    if not router then router={registered={},routes={}};routers[g]=router end
    return setmetatable({g=g,router=router,owner={},closed=false},Input)
end
function Input:bind(key,fn)
    assert(not self.closed and type(fn)=='function'and self.g.Key[key]~=nil,'live native gameplay key required')
    assert(self.g.ModifierKey and self.g.ModifierKey.SHIFT,'native Shift modifier enum required')
    local native_key=self.g.Key[key]
    for _,variant in ipairs({'bare','shift'})do
        local id=tostring(native_key)..':'..variant
        assert(not(self.router.routes[id]and self.router.routes[id].owner==self.owner),'duplicate gameplay route')
        if not self.router.registered[id]then
            local router=self.router
            local function dispatch()
                local route=router.routes[id]
                if route then route.fn()end
            end
            if variant=='bare'then self.g.RegisterKeyBind(native_key,dispatch)
            else self.g.RegisterKeyBind(native_key,{self.g.ModifierKey.SHIFT},dispatch)end
            self.router.registered[id]=true
        end
        self.router.routes[id]={owner=self.owner,fn=fn}
    end
end
function Input:close()
    self.closed=true
    for key,route in pairs(self.router.routes)do
        if route.owner==self.owner then self.router.routes[key]=nil end
    end
end
return Input
