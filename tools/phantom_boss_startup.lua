-- Delay assembly until a stable native player exists. Menu/loading is expected,
-- so it must not revoke control or reuse a cached Pawn from another World.
return function(api,directory,globals)
    local g=globals or _G
    local launch=rawget(g,'PBZBossOnlineResearchLaunch')
    g.PBZBossOnlineResearchLaunch=nil
    local config=dofile(directory..'bwb_config.lua')
    assert(type(launch)=='table' and launch.host==nil and type(launch.assembly)=='table',
        'cold startup requires dedicated native assembly')
    assert(type(launch.native_player_class)=='string'
        and launch.native_player_class:match('^/[A-Za-z0-9_/.]+_C$'),'captured native player class required')
    assert(launch.mode=='two-player-online-research' and launch.upstream_commit==config.upstream_commit
        and launch.exe_sha256==config.exe_sha256 and launch.catalog_sha256==config.catalog_sha256,
        'cold startup build/catalog mismatch')
    assert(type(g.LoopInGameThreadWithDelay)=='function' and type(g.CancelDelayedAction)=='function',
        'cancellable game-thread startup scheduler required')
    local scope=dofile(directory..'bwb_online_scope.lua').new(launch.lease_provider,{
        role=launch.role,session_id=launch.session,exe_sha256=config.exe_sha256,
        catalog_sha256=config.catalog_sha256,upstream_commit=config.upstream_commit},os.time)
    local grant=scope:attest(false)
    assert(grant.issued_at==launch.issued_at and grant.expires_at==launch.expires_at,
        'cold startup must share the issued native control lease')
    assert(type(launch.boss_id)=='string' and config.bosses[launch.boss_id],'unknown startup Boss')
    local captured={};for k,v in pairs(launch)do captured[k]=v end
    local self={startup_state='WAITING',status='waiting for native gameplay',closed=false}
    local peer,handle,stable,last_key,polls=nil,nil,0,nil,0
    local transport_requested,transport_stopped,peer_clean=false,false,false
    local deadline=math.min(os.time()+120,grant.expires_at)
    local function cancel()
        local old=handle
        if old~=nil then g.CancelDelayedAction(old);if handle==old then handle=nil end end
    end
    local function stop_transport()
        api.coop.net.enabled=false
        local stop=api.online and api.online.stop
        if type(stop)~='function'then stop=api.link and api.link.stop end
        if type(stop)~='function'then return not transport_requested,'transport stop binding unavailable'end
        local ok,result=pcall(stop)
        return ok and result~=false,result
    end
    local function cleanup()
        -- No one cleanup failure may skip another owner. Keep only unfinished
        -- responsibilities for explicit retries; no automatic reactivation.
        local errors={}
        local cancelled,why=pcall(cancel)
        self.scheduler_restore_pending=not cancelled
        if not cancelled then errors[#errors+1]='startup scheduler recovery: '..tostring(why)end
        if not transport_stopped then
            local stopped,problem=stop_transport();transport_stopped=stopped
            if not stopped then errors[#errors+1]='transport recovery: '..tostring(problem)end
        end
        self.transport_restore_pending=not transport_stopped
        if peer and not peer_clean then
            local ok,clean=pcall(peer.close,peer);peer_clean=ok and clean==true
            if not peer_clean then errors[#errors+1]='peer recovery: '..tostring(clean)end
        end
        self.peer_restore_pending=peer~=nil and not peer_clean
        self.restore_pending=self.scheduler_restore_pending or self.transport_restore_pending or self.peer_restore_pending
        self.cleanup_error=#errors>0 and table.concat(errors,'; ')or nil
        return not self.restore_pending
    end
    local function fail(reason)
        self.startup_state,self.status='FAILED',tostring(reason)
        cleanup()
        pcall(api.log,'[BWB] startup stopped: '..self.status)
    end
    local function ref(o)
        if not o or o:IsValid()~=true then return nil end
        local c=o:GetClass();if not c or c:IsValid()~=true then return nil end
        local address,name,path=o:GetAddress(),o:GetFullName(),c:GetFullName():match('^[^ ]+ (/.+)$')
        if type(address)~='number' or address<=0 or address~=math.floor(address)
            or type(name)~='string' or #name==0 or not path then return nil end
        return name..'|'..string.format('%.0f',address)..'|'..path,path
    end
    local function observed()
        local pc,pawn=api.getPlayer1()
        local pc_key=ref(pc);local pawn_key,path=ref(pawn)
        if not pc_key or not pawn_key then return nil end
        assert(path==captured.native_player_class,'unexpected startup Pawn class')
        if ref(pc:K2_GetPawn())~=pawn_key or ref(pawn:GetController())~=pc_key then return nil end
        local world=ref(pc:GetWorld())
        if not world or ref(pawn:GetWorld())~=world then return nil end
        return world..'|'..pc_key..'|'..pawn_key
    end
    function self:transport_allowed()
        if self.closed or self.startup_state~='READY' or not peer
            or peer.closed or peer.revoked_reason or peer.revoking or peer.restore_pending then return false end
        local ok=pcall(scope.attest,scope,false)
        return ok
    end
    local defaults={network_body=function()return nil end,allow_legacy_ghost=function()return false end,
        allow_enemy_name=function()return false end,allow_enemy_event=function()return false end,
        allow_enemy_actor=function()return false end,exclude=function()return true end,
        select_boss=function()return false,'native gameplay is not ready' end,
        assembly_status=function()return {state=self.startup_state,reason=self.status}end}
    setmetatable(self,{__index=function(_,key)
        local value=peer and peer[key] or defaults[key]
        if type(value)=='function' then return function(_,...)return value(peer,...)end end
        return value
    end})
    function self:close()
        if self.closed and not self.restore_pending then return true end
        self.closed=true
        self.startup_state='CLOSED'
        return cleanup()
    end
    local function tick()
        if self.closed or self.startup_state~='WAITING' then return end
        local ok,why=pcall(function()
            scope:attest(false)
            polls=polls+1
            assert(os.time()<deadline and polls<=480,'native gameplay startup timed out')
            local seen,key=pcall(observed)
            if not seen then
                -- Native lookup can fail normally during map construction. An
                -- existing, wrong Pawn must never be accepted as a new baseline.
                if tostring(key):find('unexpected startup Pawn class',1,true) then error(key) end
                key=nil
            end
            if not key then stable,last_key=0,nil;return end
            stable=key==last_key and stable+1 or 1;last_key=key
            if stable<3 then return end
            assert(g.PBZBossOnlineResearchLaunch==nil,'another startup owns the launch slot')
            -- The normal entry consumes this exact captured launch once.
            g.PBZBossOnlineResearchLaunch=captured
            local function remember(owner)
                assert(type(owner)=='table' and type(owner.close)=='function','invalid online recovery owner')
                assert(peer==nil or peer==owner,'online recovery owner cannot be replaced')
                peer=owner
                return true
            end
            local mounted,result=pcall(dofile(directory..'bwb_entry.lua'),api,directory,remember)
            if g.PBZBossOnlineResearchLaunch==captured then g.PBZBossOnlineResearchLaunch=nil end
            assert(mounted,result)
            assert(remember(result),'invalid online entry result')
            self.startup_state,self.status='READY','native gameplay assembly mounted'
            assert(api.online and type(api.online.settings)=='function'
                and type(api.online.connection)=='function' and type(api.online.start)=='function',
                'pinned online transport lifecycle unavailable')
            local settings=assert(api.online.settings(),'online settings unavailable')
            local connection,reason=api.online.connection(settings,captured.role)
            assert(connection,reason)
            transport_requested=true
            api.online.start(connection,settings)
            cancel()
            api.log('[BWB] native gameplay ready; assembly and same-PC relay requested')
        end)
        if not ok then fail(why) end
    end
    api.coop.net.enabled=false
    handle=g.LoopInGameThreadWithDelay(250,tick)
    assert(handle~=nil,'startup scheduler did not return a cancellation handle')
    api.log('[BWB] waiting for a stable native gameplay player; relay remains off')
    return self
end
