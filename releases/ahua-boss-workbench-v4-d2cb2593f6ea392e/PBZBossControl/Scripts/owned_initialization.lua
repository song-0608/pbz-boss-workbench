-- Temporary faction isolation applies only to callers' newly spawned instances.
local Isolation={};Isolation.__index=Isolation
function Isolation.new(native,friendly)
    for _,key in ipairs({'faction_component','read_faction','set_faction','relation'})do
        assert(type(native[key])=='function','initialization faction adapter missing '..key)
    end
    return setmetatable({native=native,friendly=friendly,rows={}},Isolation)
end
function Isolation:hold(pawn,player)
    assert(pawn~=player,'original player cannot be an initialization subject')
    for _,row in ipairs(self.rows)do assert(row.pawn~=pawn,'duplicate initialization subject')end
    local n=self.native;local component=n.faction_component(pawn)
    local desired=n.read_faction(n.faction_component(player))
    self.rows[#self.rows+1]={pawn=pawn,component=component,original=n.read_faction(component),desired=desired,player=player}
    n.set_faction(component,desired)
    assert(self:verify(),'owned initialization faction isolation failed')
end
function Isolation:verify()
    local n=self.native
    for _,row in ipairs(self.rows)do
        if not(row.pawn:IsValid()and row.component:IsValid()
            and n.read_faction(row.component)==row.desired
            and n.relation(row.pawn,row.player)==self.friendly
            and n.relation(row.player,row.pawn)==self.friendly)then return false end
    end
    return true
end
function Isolation:release(log)
    assert(self:verify(),'owned initialization isolation changed before release')
    for _,row in ipairs(self.rows)do
        local controller=row.pawn:GetController()
        assert(controller and controller:IsValid()and controller.SGameAIComponent.bAIStarted==false
            and not controller.BrainComponent:IsComponentTickEnabled()and not controller:IsActorTickEnabled(),
            'owned controller restarted before initialization release')
    end
    for _,row in ipairs(self.rows)do
        self.native.set_faction(row.component,row.original)
        assert(self.native.read_faction(row.component)==row.original,'owned initialization faction restoration failed')
        if log then log('OWNED_INITIALIZATION_RELEASED',row.pawn:GetFullName())end
    end
    self.rows={}
end
return Isolation
