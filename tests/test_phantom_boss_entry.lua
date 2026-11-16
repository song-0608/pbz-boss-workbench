local candidate=assert(arg[1])
local directory=candidate..'/PBZCoop/Scripts/'
local entry=dofile(directory..'bwb_entry.lua')
local config=dofile(directory..'bwb_config.lua')
local checks=0
local function check(name,fn)
    _G.PBZBossOnlineResearchLaunch=nil
    fn();_G.PBZBossOnlineResearchLaunch=nil;checks=checks+1;print('PASS '..name)
end
local function setup()
    local now=100
    local api={version='1.7.3',log=function()end,game={},coop={net={enabled=false,role='host'},handlers={}}}
    api.coop.sendEvent=function()end;api.coop.linked=function()return false end
    api.coop.isHost=function()return true end;api.coop.retireWorkbenchGhosts=function()end
    api.coop.workbenchEnemyState=function()return {}end
    api.game.listEnemies=function()return {},{}end;api.game.enemiesSoFar=api.game.listEnemies
    local original_snapshot=function()return nil end
    local launch={mode='two-player-online-research',upstream_commit=config.upstream_commit,
        expires_at=os.time()+300,exe_sha256=config.exe_sha256,catalog_sha256=config.catalog_sha256,
        role='host',session='test_online_lease',host={now=function()return now end,snapshot=original_snapshot,
        identify=function()end,log=function()end,on_revoke=function()end,
        schedule=function()return function()end end}}
    return api,launch,original_snapshot
end
check('missing online launcher remains inert',function()
    local api=setup();local result=entry(api,directory)
    assert(result.disabled and not result:allow_legacy_ghost() and not api.coop.net.enabled)
    assert(api.coop.handlers.BWB1==nil)
end)
check('offline grant cannot launch online adapter',function()
    local api,launch=setup();launch.mode='offline';_G.PBZBossOnlineResearchLaunch=launch
    assert(not pcall(entry,api,directory) and api.coop.handlers.BWB1==nil)
end)
check('expired, excessive and infinite research leases are refused',function()
    for _,value in ipairs({os.time()-1,os.time()+1250,math.huge})do
        local api,launch=setup();launch.expires_at=value;_G.PBZBossOnlineResearchLaunch=launch
        assert(not pcall(entry,api,directory) and api.coop.handlers.BWB1==nil)
    end
end)
check('build, whitelist and upstream drift refuse attachment',function()
    for _,name in ipairs({'exe_sha256','catalog_sha256','upstream_commit'})do
        local api,launch=setup();launch[name]='drift';_G.PBZBossOnlineResearchLaunch=launch
        assert(not pcall(entry,api,directory) and api.coop.handlers.BWB1==nil)
    end
end)
check('valid explicit online lease attaches control plane without mutating supplied host',function()
    local api,launch,snapshot=setup();_G.PBZBossOnlineResearchLaunch=launch
    local bridge=entry(api,directory)
    assert(api.coop.handlers.BWB1 and not bridge.protocol.ready and launch.host.snapshot==snapshot)
    assert(rawget(_G,'PBZBossOnlineResearchLaunch')==nil);bridge:close()
end)
check('ordinary offline launch variable is not consumed',function()
    _G.PBZBossControlLaunch={untouched=true};local api=setup();entry(api,directory)
    assert(_G.PBZBossControlLaunch.untouched);_G.PBZBossControlLaunch=nil
end)
check('guest role is bound before upstream autostart and cannot be inferred as host',function()
    local api,launch=setup();launch.role='guest';_G.PBZBossOnlineResearchLaunch=launch
    local bridge=entry(api,directory)
    assert(api.coop.net.role=='client' and bridge.protocol.role=='guest');bridge:close()
end)
check('missing or changed active instance role refuses attachment',function()
    local api,launch=setup();launch.role=nil;_G.PBZBossOnlineResearchLaunch=launch
    assert(not pcall(entry,api,directory) and api.coop.handlers.BWB1==nil)
    api,launch=setup();api.coop.net.enabled=true;launch.role='guest';_G.PBZBossOnlineResearchLaunch=launch
    assert(not pcall(entry,api,directory) and api.coop.handlers.BWB1==nil and api.coop.net.role=='host')
end)
check('owned assembly refuses supplied host, absent lease provider and unknown Boss selection',function()
    for _,change in ipairs({function(l)l.host=nil end,function(l)l.boss_id='unknown';l.lease_provider=function()end end,
        function(l)l.lease_provider=function()end end})do
        local api,launch=setup();launch.assembly={};change(launch);_G.PBZBossOnlineResearchLaunch=launch
        assert(not pcall(entry,api,directory) and api.coop.handlers.BWB1==nil)
    end
end)
local function assembly_entry(fail)
    local api,launch=setup();local supplied=launch.host;launch.host=nil
    launch.assembly={};launch.boss_id='ahua_guitoudao';launch.lease_provider=function()return {}end
    local assembled,revoked=0,0
    local environment=setmetatable({dofile=function(path)
        if path==directory..'bwb_host.lua' then return {new=function(_,l)
            supplied.on_revoke=function(reason)return l.revoke_control(reason)end;return supplied
        end} end
        if path==directory..'bwb_online_session.lua' then return {new=function(_,l,c,peer)
            function peer:select_boss(id)assert(id==launch.boss_id);assembled=assembled+1;return not fail,'start rejected'end
            return {state=fail=='clean'and'REJECTED'or'FAULTED',revoke=function()revoked=revoked+1;return true end}
        end} end
        return dofile(path)
    end},{__index=_G})
    local run=assert(loadfile(directory..'bwb_entry.lua','t',environment))()
    _G.PBZBossOnlineResearchLaunch=launch
    local ok,result=pcall(run,api,directory)
    return ok,result,api,function()return assembled,revoked end
end
check('dedicated assembly attaches its own recovery callback before native control starts',function()
    local ok,peer,api,counts=assembly_entry(false);assert(ok and api.coop.handlers.BWB1)
    local started,revoked=counts();assert(started==1 and revoked==0)
    assert(peer:close());started,revoked=counts();assert(revoked==1 and api.coop.handlers.BWB1==nil)
end)
check('assembly startup rejection rolls back transport wrappers and observer through recovery',function()
    local ok,why,api,counts=assembly_entry(true);assert(not ok and why:find('cleanup=true',1,true))
    local started,revoked=counts();assert(started==1 and revoked==1 and api.coop.handlers.BWB1==nil and not api.coop.net.enabled)
end)
check('clean initial rejection preserves the adapter for an explicit workbench retry',function()
    local ok,peer,api,counts=assembly_entry('clean');assert(ok and api.coop.handlers.BWB1)
    local started,revoked=counts();assert(started==1 and revoked==0 and not peer.closed)
    assert(peer:close());started,revoked=counts();assert(revoked==1 and api.coop.handlers.BWB1==nil)
end)
print('PASS '..checks..' entry groups; mocked research lease, no launcher or game started')
