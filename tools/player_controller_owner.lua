-- Process engine -> current viewport -> GameInstance -> unique LocalPlayer.
-- This ownership chain is live on every read; only the process engine identity
-- is cached. Native declarations: player-controller-owner-contract.json.
local Owner={};Owner.__index=Owner
function Owner.new(calls,api)
    assert(type(api.find_all)=='function'and type(api.now)=='function','engine ownership API required')
    return setmetatable({calls=calls,api=api},Owner)
end
function Owner:valid(object,class)
    if not object then return false end
    local weak=object:IsValid();assert(type(weak)=='boolean','ownership weak validity unreadable')
    if not weak then return false end
    if self.api.usable then
        local usable=self.api.usable(object)
        assert(type(usable)=='boolean','ownership engine validity unreadable')
        if not usable then return false end
    end
    local matches=object:IsA(class);assert(type(matches)=='boolean','ownership class identity unreadable')
    return matches
end
function Owner:viewport(engine)
    local viewport=engine.GameViewport
    if not self:valid(viewport,'/Script/Engine.GameViewportClient')then return nil end
    local instance=engine.GameInstance
    if not self:valid(instance,'/Script/Engine.GameInstance')then return nil end
    assert(self.calls:same(viewport.GameInstance,instance),'engine/viewport GameInstance mismatch')
    return viewport,instance
end
function Owner:invalidate()
    self.checked_at=nil -- retain only the still identity-checked process engine
end
function Owner:engine()
    local now=self.api.now()
    assert(type(now)=='number'and now==now and math.abs(now)<math.huge,'engine ownership clock invalid')
    if self.reference then
        local engine=self.calls:optional(self.reference)
        if self:valid(engine,'/Script/Engine.GameEngine')then return engine,1 end
        self.reference=nil
    end
    if self.checked_at and now>=self.checked_at and now<self.checked_at+1 then return nil,self.count end
    self.checked_at=now;self.count=0
    local objects=self.api.find_all('GameEngine')or{}
    assert(type(objects)=='table'and #objects<=16,'engine census exceeded bound')
    local selected
    for _,engine in ipairs(objects)do
        if self:valid(engine,'/Script/Engine.GameEngine')and self:viewport(engine)then
            self.count=self.count+1;selected=engine
        end
    end
    if self.count~=1 then return nil,self.count end
    self.reference=self.calls:reference(selected)
    return selected,1
end
function Owner:get()
    local engine,count=self:engine()
    if not engine then return nil,count end
    local viewport,instance=self:viewport(engine)
    if not viewport then return nil,0 end
    local players=instance.LocalPlayers
    assert(players and type(players.GetArrayNum)=='function','local player array unreadable')
    local size=players:GetArrayNum()
    assert(math.type(size)=='integer'and size>=0 and size<=4,'local player count outside supported bound')
    if size~=1 then return nil,size end
    local player=players[1]
    if not self:valid(player,'/Script/Engine.LocalPlayer')then return nil,0 end
    assert(players:GetArrayNum()==size,'local player array changed during query')
    assert(self.calls:same(player.ViewportClient,viewport),'local player belongs to another viewport')
    local pc=player.PlayerController
    if not self:valid(pc,'/Script/ProjectPBZ.PBZPlayerController')then return nil,0 end
    assert(self.calls:same(pc.Player,player),'controller/local-player ownership mismatch')
    assert(self.calls:same(engine.GameViewport,viewport)and self.calls:same(engine.GameInstance,instance)
        and self.calls:same(viewport.GameInstance,instance)and self.calls:same(players[1],player)
        and players:GetArrayNum()==size and self.calls:same(player.PlayerController,pc),
        'engine player ownership changed during query')
    return pc,1
end
return Owner
