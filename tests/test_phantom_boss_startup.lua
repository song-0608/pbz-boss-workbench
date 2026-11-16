local root,candidate=assert(arg[1]),assert(arg[2])
local directory=candidate..'/PBZCoop/Scripts/'
local config=dofile(directory..'bwb_config.lua')
local checks=0
local function check(name,fn)fn();checks=checks+1;print('PASS '..name)end
local function setup()
    local s={now=1000,callbacks={},cancelled={},mounts=0,starts=0,stops=0,closes=0}
    local grant={mode='two-player-online-research',isolated=true,issued_at=999,expires_at=1300,
        session_id='bwb_test',role='host',exe_sha256=config.exe_sha256,
        catalog_sha256=config.catalog_sha256,upstream_commit=config.upstream_commit}
    local launch={};for k,v in pairs(grant)do launch[k]=v end
    launch.session=grant.session_id;launch.native_player_class='/Test/Player_C'
    launch.assembly={bindings={}};launch.boss_id='ahua_guitoudao'
    launch.lease_provider=function()return grant end
    local g={PBZBossOnlineResearchLaunch=launch}
    g.LoopInGameThreadWithDelay=function(ms,fn)assert(ms==250);s.callbacks[#s.callbacks+1]=fn;return #s.callbacks end
    g.CancelDelayedAction=function(handle)s.cancelled[handle]=true end
    local world
    local function object(address,path,name)
        local o={address=address,path=path,name=name or ('Object '..address)}
        function o:IsValid()return true end
        function o:GetAddress()return self.address end
        function o:GetFullName()return self.name end
        function o:GetClass()return {IsValid=function()return true end,GetFullName=function()return 'Class '..self.path end}end
        function o:GetWorld()return world end
        return o
    end
    world=object(1,'/Script/Engine.World')
    s.pc,s.pawn=object(2,'/Test/Controller_C'),object(3,'/Test/Player_C')
    function s.pc:K2_GetPawn()return s.pawn end
    function s.pawn:GetController()return s.pc end
    s.playing=false
    local api={coop={net={enabled=false}},log=function()end,
        getPlayer1=function()if s.playing then return s.pc,s.pawn end end}
    api.online={stop=function()s.stops=s.stops+1 end,settings=function()return {}end,
        connection=function(_,role)return {role=role}end,
        start=function()s.starts=s.starts+1;if s.start_error then error('start failed')end end}
    s.peer={close=function()s.closes=s.closes+1;if s.close_error then error('close failed')end;return not s.restore_pending end,
        network_body=function(self)assert(self==s.peer);return 'BOSS',42 end,
        select_boss=function(self,id)assert(self==s.peer);return id=='056_youlong' end}
    local environment=setmetatable({os={time=function()return s.now end},dofile=function(path)
        if path==directory..'bwb_entry.lua' then return function(a)
            assert(g.PBZBossOnlineResearchLaunch and a==api)
            g.PBZBossOnlineResearchLaunch=nil;s.mounts=s.mounts+1
            if s.mount_error then error('mount failed')end
            return s.peer
        end end
        return dofile(path)
    end},{__index=_G})
    local start=assert(loadfile(root..'/tools/phantom_boss_startup.lua','t',environment))()
    function s:begin()self.bridge=start(api,directory,g);return self.bridge end
    function s:tick(n)for _=1,n or 1 do self.callbacks[1]()end end
    function s:world(id)world.address=id end
    return s,launch,grant,api,g
end
check('menu remains inert and does not mount or start transport',function()
    local s,_,_,_,g=setup();local b=s:begin();s:tick(20)
    assert(b.startup_state=='WAITING' and s.mounts==0 and s.starts==0 and s.stops==0)
    assert(not b:transport_allowed() and not b:allow_legacy_ghost() and not b:network_body())
    assert(not b:allow_enemy_actor() and not b:allow_enemy_event() and not b:allow_enemy_name())
    assert(g.PBZBossOnlineResearchLaunch==nil)
end)
check('three stable gameplay observations mount and request transport exactly once',function()
    local s=setup();local b=s:begin();s.playing=true;s:tick(2);assert(s.mounts==0)
    s:tick();assert(b.startup_state=='READY' and s.mounts==1 and s.starts==1 and s.cancelled[1])
    s:tick(4);assert(s.mounts==1 and s.starts==1 and b:transport_allowed())
end)
check('changing World resets stability and never reuses previous observation',function()
    local s=setup();s:begin();s.playing=true;s:tick(2);s:world(5);s:tick(2);assert(s.mounts==0)
    s:tick();assert(s.mounts==1)
end)
check('temporary loading gap resets stability without revocation',function()
    local s=setup();s:begin();s.playing=true;s:tick(2);s.playing=false;s:tick();s.playing=true;s:tick(2)
    assert(s.mounts==0 and s.stops==0);s:tick();assert(s.mounts==1)
end)
check('controller ownership mismatch waits without touching gameplay',function()
    local s=setup();s:begin();s.playing=true;s.pc.K2_GetPawn=function()return s.pc end;s:tick(5)
    assert(s.mounts==0 and s.bridge.startup_state=='WAITING' and s.starts==0)
end)
check('unexpected Pawn class fails rather than capturing a replacement baseline',function()
    local s=setup();s:begin();s.playing=true;s.pawn.path='/Test/Other_C';s:tick()
    assert(s.mounts==0 and s.bridge.startup_state=='FAILED' and s.cancelled[1] and s.stops==1)
end)
check('invalid scope build role or missing assembly refuses scheduling',function()
    for _,change in ipairs({function(l)l.exe_sha256='wrong'end,function(l)l.role='other'end,
        function(l)l.assembly=nil end,function(l)l.issued_at=998 end})do
        local s,l=setup();change(l);assert(not pcall(s.begin,s) and #s.callbacks==0)
    end
end)
check('expiry while waiting cancels startup without mounting',function()
    local s=setup();s:begin();s.now=1300;s:tick()
    assert(s.bridge.startup_state=='FAILED' and s.mounts==0 and s.cancelled[1])
end)
check('lease mutation while waiting cannot change captured session',function()
    local s,_,grant=setup();s:begin();grant.session_id='another';s:tick()
    assert(s.bridge.startup_state=='FAILED' and s.mounts==0)
end)
check('stationary wall clock still has a finite polling budget',function()
    local s=setup();s:begin();s:tick(481)
    assert(s.bridge.startup_state=='FAILED' and s.mounts==0 and s.cancelled[1])
end)
check('entry failure stops transport and clears only its launch slot',function()
    local s,_,_,_,g=setup();s:begin();s.mount_error=true;s.playing=true;s:tick(3)
    assert(s.bridge.startup_state=='FAILED' and s.stops==1 and s.starts==0 and g.PBZBossOnlineResearchLaunch==nil)
end)
check('transport startup failure closes mounted peer and retains failed restoration',function()
    local s=setup();s:begin();s.start_error=true;s.restore_pending=true;s.playing=true;s:tick(3)
    assert(s.bridge.startup_state=='FAILED' and s.closes==1 and s.bridge.restore_pending)
end)
check('closing a waiting startup cancels stale callbacks and forbids later mounting',function()
    local s=setup();local b=s:begin();assert(b:close());s.playing=true;s:tick(4)
    assert(b.startup_state=='CLOSED' and s.mounts==0 and not b:transport_allowed())
end)
check('ready facade forwards methods with the real peer and preserves close failures',function()
    local s=setup();local b=s:begin();s.playing=true;s:tick(3)
    local body,address=b:network_body();assert(body=='BOSS' and address==42 and b:select_boss('056_youlong'))
    s.close_error=true;assert(not b:close() and b.restore_pending and not b:close())
end)
check('actual patched upstream start functions return before work when startup is waiting',function()
    for _,row in ipairs({{'coop.lua','    local function start(role)\n'},
        {'autostart.lua','    local function startRelay(c, s)\n'}})do
        local f=assert(io.open(candidate..'/upstream-local-patches/'..row[1],'r'));local text=f:read('a');f:close()
        local at=assert(text:find(row[2],1,true));local tail=text:sub(at+#row[2])
        local line=assert(tail:match('^([^\n]+)\n'))
        local executed=0;local api={bossWorkbench={transport_allowed=function()return false end}}
        local fn=assert(load('return function()\n'..line..'\nwork()\nend','patched guard','t',
            {api=api,work=function()executed=executed+1 end}))()
        assert(fn()==false and executed==0);api.bossWorkbench.transport_allowed=function()return true end
        fn();assert(executed==1)
    end
end)
check('revoked closed or restoring peer cannot reopen transport through ready facade',function()
    for _,key in ipairs({'closed','revoked_reason','revoking','restore_pending'})do
        local s=setup();local b=s:begin();s.playing=true;s:tick(3)
        assert(b:transport_allowed());s.peer[key]=true
        assert(not b:transport_allowed())
    end
end)
check('ready facade still rejects an expired or changed control lease',function()
    local s,_,grant=setup();local b=s:begin();s.playing=true;s:tick(3)
    grant.session_id='changed';assert(not b:transport_allowed())
    s=setup();b=s:begin();s.playing=true;s:tick(3);s.now=1300
    assert(not b:transport_allowed())
end)
print('PASS '..checks..' startup groups; simulated game-thread menu/loading, no game started')
