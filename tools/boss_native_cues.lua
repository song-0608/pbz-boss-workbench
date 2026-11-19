-- Runs after the original cue action begin. Conditions/timing/colors stay owned by that action.
-- The adapter must resolve current-session action references; no particles are fabricated here.
local Cues={};Cues.__index=Cues
function Cues.new(adapter)
    for _,name in ipairs({'owner','eligible','reference','resolve','count','spawn','finish'})do
        assert(type(adapter[name])=='function','native cue adapter missing '..name)
    end
    return setmetatable({adapter=adapter,pending={},size=0},Cues)
end
local function key(ref)
    assert(type(ref)=='table'and type(ref.name)=='string'and ref.address~=nil
        and type(ref.class)=='string','exact cue action reference required')
    return ref.name..'|'..tostring(ref.address)..'|'..ref.class
end
function Cues:count(action)
    local count=self.adapter.count(action)
    assert(math.type(count)=='integer'and count>=0 and count<=128,'bounded native cue components required')
    return count
end
function Cues:on_begin(action)
    local owner=self.adapter.owner(action)
    if not owner or self.adapter.eligible(action,owner)~=true then return false,'unowned action'end
    local ref=self.adapter.reference(action);local id=key(ref)
    if self.pending[id]then return false,'begin already observed'end
    if self:count(action)>0 then return false,'original cue already present'end
    assert(self.size<128,'native cue lifecycle bound reached')
    local item={reference=ref,owner=owner}
    self.pending[id]=item;self.size=self.size+1 -- Cleanup owns even a partially failed spawn.
    assert(self.adapter.spawn(action,owner)==true,'native cue spawn rejected')
    local shown=self:count(action)>0
    item.components_observed=shown
    return shown,shown and'native components observed'or'native action produced no components'
end
function Cues:on_end(action)
    local id=key(self.adapter.reference(action))
    local item=self.pending[id]
    if item then
        -- Normally the original End Particles has already run. Keep ownership
        -- if native end failed rather than losing the cleanup receipt.
        if self:count(action)>0 then
            assert(self.adapter.eligible(action,item.owner)==true,'cue owner or world changed')
            assert(self.adapter.finish(action)==true,'native cue end rejected')
            assert(self:count(action)==0,'native cue components remain after end')
        end
        self.pending[id]=nil;self.size=self.size-1
    end
    return true
end
function Cues:cleanup()
    local failures={}
    for id,item in pairs(self.pending)do
        local ok,why=pcall(function()
            local action=self.adapter.resolve(item.reference)
            if action then
                -- Refuse a new World/owner even when an action address was reused.
                assert(key(self.adapter.reference(action))==id,'cue identity changed')
                assert(self.adapter.eligible(action,item.owner)==true,'cue owner or world changed')
                assert(self.adapter.finish(action)==true,'native cue end rejected')
                assert(self:count(action)==0,'native cue components remain after cleanup')
            end
        end)
        if ok then self.pending[id]=nil;self.size=self.size-1
        else failures[#failures+1]=tostring(why)end
    end
    return #failures==0,failures
end
return Cues
