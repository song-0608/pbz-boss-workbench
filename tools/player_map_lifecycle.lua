-- LoadMap pre/post is a transaction, including failed loads that retain UWorld.
-- Post observation only permits ordinary gameplay readiness; it is not success.
local Map={};Map.__index=Map
local function same(a,b)
    return a and b and a.name==b.name and a.address==b.address and a.class==b.class
end
local function reference(value)
    if value==nil then return nil end
    assert(type(value)=='table'and type(value.name)=='string'and type(value.class)=='string'
        and type(value.address)=='number'and value.address==value.address
        and math.abs(value.address)<math.huge,'map World identity unreadable')
    return {name=value.name,address=value.address,class=value.class}
end
function Map.new(api)
    for _,key in ipairs({'attest','suspend','invalidate','resume','log','reference'})do
        assert(type(api[key])=='function','map lifecycle API missing '..key)
    end
    return setmetatable({api=api,depth=0,phase='ready',blocked=false},Map)
end
function Map:before(world)
    self.depth=self.depth+1;self.phase='loading'
    local ok,why=pcall(function()
        self.api.attest()
        self.api.suspend(world)
        self.api.invalidate()
        self.api.log('MAP_TRAVEL_TRANSACTION_PRE',self.depth)
    end)
    if not ok then self.blocked=true;error(why,0)end
end
function Map:after(world,native_error)
    if self.depth==0 then return end -- no matching native pre: never start assembly
    local ok,why=pcall(function()
        self.api.attest()
        assert(type(native_error)=='string','LoadMap error result unreadable')
        self.depth=self.depth-1
        if self.depth>0 or self.blocked then return end
        self.expected=reference(self.api.reference(world))
        self.native_error=native_error
        self.api.invalidate()
        self.phase='waiting'
        self.api.log('MAP_TRAVEL_POST_OBSERVED',self.expected and self.expected.name or 'no current World')
        if native_error~=''then self.api.log('MAP_TRAVEL_NATIVE_ERROR',native_error)end
        self.api.resume()
    end)
    if not ok then self.blocked=true;error(why,0)end
end
function Map:suspended()return self.blocked or self.depth>0 end
function Map:ready(world)
    if self:suspended()then return false end
    if self.phase=='waiting'and self.expected then
        return same(reference(self.api.reference(world)),self.expected)==true
    end
    return true
end
function Map.attach(g,api)
    assert(type(g.RegisterLoadMapPreHook)=='function'and type(g.RegisterLoadMapPostHook)=='function',
        'current loader requires native LoadMap pre and post hooks')
    local self=Map.new(api)
    g.RegisterLoadMapPreHook(function(_,world)
        local ok,why=pcall(function()self:before(world:Get())end)
        if not ok then self.blocked=true;api.log('ISSUE_MAP_TRAVEL_GUARD',why)end
        -- nil preserves the engine result and original URL.
    end)
    g.RegisterLoadMapPostHook(function(_,world,_,_,native_error)
        local ok,why=pcall(function()self:after(world:Get(),native_error)end)
        if not ok then self.blocked=true;api.log('ISSUE_MAP_TRAVEL_POST',why)end
        -- The second parameter is the current UWorld RemoteUnrealParam.
    end)
    api.log('MAP_TRAVEL_GUARD_READY',true)
    return self
end
return Map
