-- A candidate is inert unless a dedicated online-research launcher supplies its host.
-- Never consume PBZBossControlLaunch or counterfeit an offline proof.
return function(api, directory, remember)
    assert(remember==nil or type(remember)=='function','recovery owner callback required')
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
    -- Publish the recovery owner before optional/native construction can fail.
    -- Once accepted, the outer startup retains it and owns cleanup retries.
    local published=false
    if remember then
        local ok,accepted=pcall(remember,peer)
        if not ok or accepted~=true then
            local closed,clean=pcall(peer.close,peer)
            error('recovery owner publication rejected; cleanup='..tostring(closed and clean==true)..': '..tostring(accepted))
        end
        published=true
    end
    if launch.assembly~=nil then
        local ok,why=pcall(function()
            local mounted=dofile(directory..'bwb_online_session.lua').new(api,launch,config,peer,host,directory,_G,function(owner)
                assert(type(owner)=='table' and type(owner.revoke)=='function','invalid assembly recovery owner')
                assert(assembly==nil or assembly==owner,'assembly recovery owner cannot be replaced')
                assembly=owner
                return true
            end)
            assert(mounted==assembly,'assembly recovery owner was not published')
            local started,reason=peer:select_boss(launch.boss_id)
            if not started then
                assert(assembly.state=='REJECTED',reason)
                api.log('[BWB] initial assembly rejected; original player restored, retry from workbench: '..tostring(reason))
            end
        end)
        if not ok then
            if published then error('online assembly mount rejected; outer recovery retained: '..tostring(why))end
            local closed,clean=pcall(peer.close,peer)
            error('online assembly mount rejected; cleanup='..tostring(closed and clean==true)..': '..tostring(why)
                ..(closed and ''or '; cleanup error='..tostring(clean)))
        end
    end
    return peer
end
