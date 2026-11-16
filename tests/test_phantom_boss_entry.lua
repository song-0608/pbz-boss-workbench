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
print('PASS '..checks..' entry groups; mocked research lease, no launcher or game started')
