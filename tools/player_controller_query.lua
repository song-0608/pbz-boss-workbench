-- Share a bounded gameplay-controller census across HUD, idle World checks and
-- release waits. Cached objects still pass identity, World and possession checks.
local Query={};Query.__index=Query
local function same(a,b)
    return a and b and a.name==b.name and a.address==b.address and a.class==b.class
end
function Query.new(calls,api)
    assert(type(api.now)=='function'and type(api.find_all)=='function','controller query API required')
    return setmetatable({calls=calls,api=api},Query)
end
function Query:usable(pc)
    if not pc or not pc:IsValid()then return false end
    if self.api.usable and not self.api.usable(pc)then return false end
    local pawn=pc.Pawn
    if not pawn or not pawn:IsValid()then return false end
    if self.api.usable and not self.api.usable(pawn)then return false end
    assert(self.calls:same(pc:K2_GetPawn(),pawn),'controller query mismatch')
    assert(self.calls:same(pawn:GetController(),pc),'pawn controller mismatch')
    return true
end
function Query:get()
    local now=self.api.now()
    assert(type(now)=='number'and now==now and math.abs(now)<math.huge,'controller query clock invalid')
    if self.checked_at and now>=self.checked_at and now<self.checked_at+1 then
        if not self.reference then return nil,self.count end
        local pc=self.calls:optional(self.reference)
        if self:usable(pc)and same(self.calls:world(pc),self.world)then return pc,1 end
        self.reference=nil;self.world=nil;self.count=0
        return nil,0
    end
    self.checked_at=now;self.reference=nil;self.world=nil;self.count=0
    local selected
    local objects=self.api.find_all('PBZPlayerController')or{}
    assert(type(objects)=='table'and #objects<=64,'controller census exceeded bound')
    for _,pc in ipairs(objects)do
        if pc and pc:IsValid()and pc:GetFullName():find(':PersistentLevel.',1,true)and self:usable(pc)then
            self.count=self.count+1;selected=pc
        end
    end
    if self.count~=1 then return nil,self.count end
    self.reference=self.calls:reference(selected);self.world=self.calls:world(selected)
    return selected,1
end
return Query
