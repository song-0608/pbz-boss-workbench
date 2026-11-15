local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Isolation=require('owned_initialization');local total=0
local function fixture()
    local function pawn(tag)
        local p={faction={tag=tag},controller={SGameAIComponent={bAIStarted=false},BrainComponent={tick=false},tick=false}}
        function p:IsValid()return not self.invalid end
        function p.faction:IsValid()return not self.invalid end
        function p.controller:IsValid()return true end
        function p.controller:IsActorTickEnabled()return self.tick end
        function p.controller.BrainComponent:IsComponentTickEnabled()return self.tick end
        function p:GetController()return self.controller end
        function p:GetFullName()return 'owned fixture'end
        return p
    end
    local player,boss,target=pawn('player'),pawn('boss'),pawn('target')
    local native={faction_component=function(p)return p.faction end,read_faction=function(c)return c.tag end,
        set_faction=function(c,t)c.tag=t end,relation=function(a,b)return a.faction.tag==b.faction.tag and 0 or 2 end}
    return Isolation.new(native,0),player,boss,target,native
end
local function test(name,fn)local ok,why=pcall(fn);assert(ok,name..': '..tostring(why));total=total+1;print('PASS '..name)end
test('three-party initialization preserves player and restores distinct native tags',function()
    local g,p,b,t=fixture();g:hold(b,p);g:hold(t,p)
    assert(g:verify()and b.faction.tag=='player'and t.faction.tag=='player'and p.faction.tag=='player')
    g:release();assert(b.faction.tag=='boss'and t.faction.tag=='target'and p.faction.tag=='player'and #g.rows==0)
end)
test('no faction restoration until every controller is stopped',function()
    for _,kind in ipairs({'ai','brain','controller'})do
        local g,p,b,t=fixture();g:hold(b,p);g:hold(t,p)
        if kind=='ai'then t.controller.SGameAIComponent.bAIStarted=true
        elseif kind=='brain'then t.controller.BrainComponent.tick=true else t.controller.tick=true end
        assert(not pcall(g.release,g)and b.faction.tag=='player'and t.faction.tag=='player')
    end
end)
test('original player duplicate subject ignored writes and hostile reverse relation reject',function()
    local g,p,b,t,n=fixture();assert(not pcall(g.hold,g,p,p));g:hold(b,p);assert(not pcall(g.hold,g,b,p))
    g,p,b,t,n=fixture();n.set_faction=function()end;assert(not pcall(g.hold,g,b,p))
    g,p,b,t,n=fixture();n.relation=function(a)return a==p and 2 or 0 end;assert(not pcall(g.hold,g,b,p))
end)
test('asynchronous faction changes expired subjects and failed native release cannot pass',function()
    local g,p,b=fixture();g:hold(b,p);b.faction.tag='changed';assert(not g:verify()and not pcall(g.release,g))
    local t,n;g,p,b,t,n=fixture();g:hold(b,p);b.invalid=true;assert(not g:verify())
    g,p,b,t,n=fixture();g:hold(b,p);n.set_faction=function()end;assert(not pcall(g.release,g))
end)
print('Owned initialization fixtures passed: '..total)
