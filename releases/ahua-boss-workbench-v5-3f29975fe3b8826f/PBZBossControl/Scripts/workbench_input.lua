-- Owns only the temporary menu input Actor; never changes the player's input mappings.
local Layer={};Layer.__index=Layer
function Layer.new(calls,barrier,native)
    assert(calls and barrier and type(native.create)=='function'and type(native.finish)=='function'
        and type(native.destroy)=='function','workbench input adapter required')
    return setmetatable({calls=calls,barrier=barrier,native=native},Layer)
end
function Layer:lock(pc)
    assert(not self.ticket,'workbench already owns an input layer')
    local owner=self.native.create()
    self.ticket={owner=self.calls:reference(owner)}
    assert(self.native.finish(owner)==true,'workbench input owner construction failed')
    assert(self.barrier:attach(pc,owner,self.ticket)==true,'workbench barrier unavailable')
    return true
end
function Layer:unlock()
    local ticket=self.ticket;if not ticket then return true end
    local owner=self.calls:retirement_optional(ticket.owner)
    -- UE4SS userdata reflects unknown member names. Only our Lua sentinel denotes ambiguity.
    assert(not(type(owner)=='table'and rawget(owner,'retirement_ambiguous')==true),'workbench owner identity ambiguous')
    if owner then
        assert(self.barrier:detach(ticket.input_barrier)==true,'workbench input detach failed')
        assert(self.native.destroy(owner)==true,'workbench owner retirement failed')
        assert(not self.calls:retirement_optional(ticket.owner),'workbench owner still engine-usable')
    elseif ticket.input_barrier then
        local component=ticket.input_barrier.component
        assert(not component or not self.calls:retirement_optional(component),'workbench input component still alive')
        ticket.input_barrier.removed=true
    end
    self.ticket=nil;return true
end
return Layer
