-- 用途：直接执行真实训练脚本的前置等待部分，确认走动、死亡、重复控制器时不生成Boss。
local root=assert(arg[1])
local file=assert(io.open(root..'/mod/PBZBossControl/Experiments/spawn_lifecycle.lua','rb'))
local source=file:read('*a');file:close()
local module_file=assert(io.open(root..'/mod/PBZBossControl/Scripts/owned_arena.lua','rb'))
local module_source=module_file:read('*a');module_file:close()
local passed=0
local function fixture(velocity,health,ambiguous,options)
    options=options or{}
    local f={queue={},logs={},loads=0,polls=0,missing=options.missing}
    local player={AttributeSetBase={Health={CurrentValue=health or 100}}}
    f.player=player
    function player:IsValid()return true end
    function player:GetFullName()return 'Player /Game/Test:PersistentLevel.Player'end
    function player:GetAddress()return 100 end
    function player:GetVelocity()f.polls=f.polls+1;return{X=velocity(f.polls),Y=0,Z=0}end
    local pc={Pawn=player}
    function pc:IsValid()return true end
    function pc:GetFullName()return 'Controller /Game/Test:PersistentLevel.Player'end
    local env=setmetatable({
        print=function(s)f.logs[#f.logs+1]=s end,
        FindAllOf=function()return f.missing and{}or(ambiguous and{pc,pc}or{pc})end,
        TEST_EXPIRES_AT=os.time()+(options.ttl or 60),
        ExecuteWithDelay=function(_,fn)f.queue[#f.queue+1]=fn end,
        ExecuteInGameThread=function(fn)fn()end,
        ExecuteInGameThreadWithDelay=function(_,fn)f.queue[#f.queue+1]=fn end,
        LoadAsset=function()f.loads=f.loads+1;error('fixture reached asset loading after readiness')end,
    },{__index=_G})
    env.require=function(name)
        if name=='owned_arena'then
            local arena=assert(load(module_source,'@owned_arena_readiness','t',env))()
            local start=arena.start
            arena.start=function(o)o.player_entry=options.player_entry;o.boss_id='ahua_guitoudao';return start(o)end
            return arena
        end
        if name=='boss_catalog'then return{profile=function(id)
            assert(id=='ahua_guitoudao');return{identity_verified=true,exe_sha256='fixture',class_path='fixture-class'}
        end}end
        if name=='profiles.ahua'then return{identity_verified=true,exe_sha256='fixture',class_path='fixture-class'}end
        return require(name)
    end
    local prefix='local function experiment_attest()return{offline=true,isolated=true,exe_sha256="fixture",expires_at=TEST_EXPIRES_AT}end\n'
    assert(load(prefix..source,'@spawn_lifecycle_readiness','t',env))()
    function f:step()
        local next=table.remove(self.queue,1);if next then next()end
        return next~=nil
    end
    function f:drain()local count=0;while self:step()do count=count+1;assert(count<250,'unbounded readiness loop')end end
    return f
end
local function test(name,fn)fn();passed=passed+1;print('PASS '..name)end
test('player entry waits at title beyond the initial twenty second window within the same lease',function()
    local f=fixture(function()return 0 end,100,false,{missing=true,player_entry=true,ttl=600})
    for _=1,205 do assert(f:step())end
    assert(f.loads==0 and table.concat(f.logs):find('WORLD_REASSEMBLY_AWAITING_GAMEPLAY=true',1,true))
    f.missing=false;f:drain();assert(f.loads==1)
end)
test('title wait stops with cleanup margin and does not extend the lease',function()
    local f=fixture(function()return 0 end,100,false,{missing=true,player_entry=true,ttl=60})
    f:drain();assert(f.loads==0 and #f.queue==0)
    assert(table.concat(f.logs):find('PREREQUISITE_RETRY_SAFE=true',1,true))
end)

test('gameplay arriving near title poll limit receives its full stable observation window',function()
    local f=fixture(function()return 0 end,100,false,{missing=true,player_entry=true,ttl=600})
    for _=1,185 do assert(f:step())end
    f.missing=false
    for _=1,45 do assert(f:step())end
    assert(f.loads==0)
    f.player.AttributeSetBase.Health.CurrentValue=180
    for _=1,45 do assert(f:step())end
    assert(f.loads==0)
    f:drain();assert(f.loads==1)
    assert(not table.concat(f.logs):find('PREREQUISITE_NOT_READY=',1,true))
end)

test('health changes on the same player do not renew the bounded readiness budget',function()
    local f=fixture(function()return 0 end,100,false,{player_entry=true,ttl=600})
    for n=1,199 do
        f.player.AttributeSetBase.Health.CurrentValue=100+n
        assert(f:step())
    end
    f:drain();assert(f.loads==0 and #f.queue==0)
    assert(table.concat(f.logs):find('PREREQUISITE_NOT_READY=',1,true))
end)
test('moving player never reaches asset loading and allows same-process retry',function()
    local f=fixture(function()return 10 end);f:drain()
    assert(f.loads==0)
    assert(table.concat(f.logs):find('PREREQUISITE_RETRY_SAFE=true',1,true))
end)
test('stable interval is required before any asset loading',function()
    local f=fixture(function(n)return n<=5 and 10 or 0 end)
    for _=1,16 do f:step()end
    assert(f.loads==0)
    f:drain();assert(f.loads==1)
    assert(table.concat(f.logs):find('PLAYER_READY_STABLE=true',1,true))
end)

test('health restored by loading must settle before any spawn mutation',function()
    local f=fixture(function(n)return 0 end)
    for _=1,45 do assert(f:step())end
    assert(f.loads==0)
    f.player.AttributeSetBase.Health.CurrentValue=180
    for _=1,45 do assert(f:step())end
    assert(f.loads==0)
    f:drain();assert(f.loads==1)
end)
test('dead original player does not generate a boss',function()
    local f=fixture(function()return 0 end,0);f:drain();assert(f.loads==0)
end)
test('ambiguous local controller does not generate a boss',function()
    local f=fixture(function()return 0 end,100,true);f:drain();assert(f.loads==0)
end)
print('Practice readiness fixtures: '..passed..' passed; no game process or save access.')
