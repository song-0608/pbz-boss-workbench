-- A candidate is inert unless a dedicated online-research launcher supplies its host.
-- Never consume PBZBossControlLaunch or counterfeit an offline proof.
return function(api, directory)
    local launch=rawget(_G,'PBZBossOnlineResearchLaunch')
    _G.PBZBossOnlineResearchLaunch=nil
    if type(launch)~='table' then
        api.coop.net.enabled=false
        api.log('BWB online candidate DISABLED: dedicated research session required')
        return {disabled=true,allow_legacy_ghost=function() return false end,status='research launcher absent'}
    end
    local config=dofile(directory..'bwb_config.lua')
    assert(launch.mode=='two-player-online-research' and launch.upstream_commit==config.upstream_commit,
        'online research scope/upstream mismatch')
    assert(type(launch.expires_at)=='number' and launch.expires_at>os.time()
        and launch.expires_at<=os.time()+1200,'bounded online research lease required')
    assert(launch.exe_sha256==config.exe_sha256 and launch.catalog_sha256==config.catalog_sha256,
        'online research build/catalog mismatch')
    local supplied=launch.host
    if supplied==nil then supplied=dofile(directory..'bwb_host.lua').new(api,launch,_G) end
    assert(type(supplied)=='table','trusted research host required')
    local host={}; for key,value in pairs(supplied) do host[key]=value end
    config.session=launch.session
    local original_snapshot=host.snapshot
    host.snapshot=function()
        assert(os.time()<launch.expires_at,'online research session expired')
        return original_snapshot()
    end
    return dofile(directory..'bwb_adapter.lua').attach(api,config,host,dofile(directory..'bwb_protocol.lua'))
end
