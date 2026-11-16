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
    assert(launch.role=='host' or launch.role=='guest','explicit online instance role required')
    local assembly
    if launch.assembly~=nil then
        assert(launch.host==nil and type(launch.lease_provider)=='function'
            and type(launch.boss_id)=='string' and config.bosses[launch.boss_id],
            'dedicated native online assembly launch required')
        assert(launch.revoke_control==nil,'assembly owns its native recovery callback')
        launch.revoke_control=function(reason)
            return not assembly or assembly:revoke(reason)
        end
    end
    local supplied=launch.host
    if supplied==nil then supplied=dofile(directory..'bwb_host.lua').new(api,launch,_G) end
    assert(type(supplied)=='table','trusted research host required')
    local host={}; for key,value in pairs(supplied) do host[key]=value end
    config.session=launch.session
    config.role=launch.role
    local original_snapshot=host.snapshot
    host.snapshot=function()
        assert(os.time()<launch.expires_at,'online research session expired')
        return original_snapshot()
    end
    -- Upstream starts with net.role='host', including on a guest, and autostart runs
    -- later. Bind the instance role before installing the observer/handler.
    local expected_role=launch.role=='host' and 'host' or 'client'
    assert(not api.coop.net.enabled or api.coop.net.role==expected_role,'active relay role mismatch')
    if not api.coop.net.enabled then api.coop.net.role=expected_role end
    local peer=dofile(directory..'bwb_adapter.lua').attach(api,config,host,
        dofile(directory..'bwb_protocol.lua'),dofile(directory..'bwb_enemy_fence.lua'))
    if launch.assembly~=nil then
        local ok,why=pcall(function()
            assembly=dofile(directory..'bwb_online_session.lua').new(api,launch,config,peer,host,directory,_G)
            local started,reason=peer:select_boss(launch.boss_id)
            assert(started,reason)
        end)
        if not ok then
            local clean=peer:close()
            error('online assembly mount rejected; cleanup='..tostring(clean)..': '..tostring(why))
        end
    end
    return peer
end
