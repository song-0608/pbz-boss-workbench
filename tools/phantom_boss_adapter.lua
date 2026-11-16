-- Phantom Pact 1.7.3 adapter. The pure protocol is injected by the pinned builder.
-- Owns only its BWB1 handler and a bounded identity registry, never player inventory.
local M = {}
-- The Boss session shares combat and identity only. Upstream inventory, loot,
-- currency, appearance, rest and story messages are outside this session.
local combat_events={BWB1=true,BWV1=true,Y=true,S=true,J=true,LOAD=true,BYE=true,F=true,
    N=true,NQ=true,D=true,K=true,GK=true,LR=true,RUN=true,B=true,BEATEN=true,
    HAS=true,NOT=true,A=true,HX=true}
local function identity(row)
    return type(row)=='table' and type(row.address)=='number' and row.address>0
        and type(row.name)=='string' and #row.name>0 and type(row.class)=='string'
        and type(row.world)=='string' and #row.world>0
end
local function same(a,b)
    return identity(a) and identity(b) and a.address==b.address and a.name==b.name
        and a.class==b.class and a.world==b.world
end

function M.attach(api, config, host, protocol, enemy_fence)
    assert(api.version=='1.7.3','unsupported Phantom Pact API')
    local coop, net, game = assert(api.coop), assert(api.coop.net), assert(api.game)
    assert(type(coop.handlers)=='table' and type(coop.sendEvent)=='function')
    assert(type(coop.linked)=='function' and type(coop.isHost)=='function')
    assert(type(coop.retireWorkbenchGhosts)=='function','pinned ghost retirement patch required')
    assert(not coop.handlers[protocol.EVENT], 'BWB handler already installed')
    assert(type(host.now)=='function' and type(host.snapshot)=='function')
    assert(type(host.identify)=='function' and type(host.schedule)=='function')
    assert(type(host.log)=='function' and type(host.on_revoke)=='function')
    assert(type(config.bosses)=='table' and config.runtime_acceptance_current==false)
    local original_list,original_cached=game.listEnemies,game.enemiesSoFar
    assert(type(original_list)=='function' and type(original_cached)=='function')
    local self = { closed=false, owned={}, owned_count=0, local_body=nil, world=nil,
        last_poll=-math.huge, status='awaiting transport', remote_body_pending=true }
    assert(type(enemy_fence)=='table' and type(enemy_fence.new)=='function','enemy isolation module required')
    local fence=enemy_fence.new(coop,game,function(actor,addr) return self:exclude(actor,addr) end)
    local role=assert(config.role,'explicit instance role required')
    assert(role=='host' or role=='guest','invalid instance role')
    local function invalidate(reason)
        self.status=reason
        if self.invalidated_reason==reason then return end
        self.invalidated_reason=reason
        coop.retireWorkbenchGhosts() -- park old native clones before accepting another identity
    end
    local function revoke(reason)
        invalidate(reason)
        if self.revoked_reason==reason then return end
        self.revoked_reason=reason
        net.enabled=false
        self.revoking=true
        local ok,result=pcall(host.on_revoke,reason)
        self.revoking=false
        self.restore_pending=not ok or result~=true
        if self.restore_pending then host.log('BWB possession restoration unverified: '..tostring(reason)) end
    end
    local function protocol_invalidated(reason)
        invalidate(reason)
        if reason=='transport disconnected' or reason=='peer timeout'
            or reason=='catalog or game build mismatch' or reason=='bridge closed' then revoke(reason) end
    end
    local state = protocol.new { role=role, session=config.session, catalog=config.catalog_sha256,
        build=config.exe_sha256, bosses=config.bosses,
        send=function(kind,line) coop.sendEvent(kind,line) end,
        on_ready=function(on,reason)
            self.status=on and 'identity ready; Boss ghost assembly unaccepted' or reason
            if on then self.revoked_reason,self.invalidated_reason=nil,nil end
            if not on then protocol_invalidated(reason) end
        end,
        on_clear=protocol_invalidated,
        on_identity=function() self.remote_body_pending=true end,
        -- Explicitly no on_action: the control plane cannot grant an ability or apply a hit.
    }
    self.protocol=state
    local class_to_boss,class_actions={},{}
    for id,row in pairs(config.bosses) do
        class_to_boss[row.class_path]=id
        local actions={};for key,path in pairs(row.actions) do actions[key]=path end
        class_actions[row.class_path]=actions
    end
    function self:is_boss_class(path) return class_to_boss[path]~=nil end
    function self:resolve_local_action(path,id)
        return class_actions[path] and class_actions[path][id] or nil
    end
    function self:register(row,kind)
        assert(not self.closed and identity(row),'valid current-world identity required')
        assert(row.world==self.world,'cannot own another world actor')
        assert(kind=='local_body' or kind=='remote_ghost' or kind=='training_target' or kind=='controller')
        local old=self.owned[row.address]
        if not old then assert(self.owned_count<32,'owned actor limit'); self.owned_count=self.owned_count+1 end
        self.owned[row.address]={address=row.address,name=row.name,class=row.class,world=row.world,kind=kind}
        fence:purge(row)
    end
    -- Reclaim a registry slot only after the native owner synchronously proves
    -- that exact identity is no longer usable. Never evict a live body to make
    -- room; enemy aliases stay quarantined against late network messages.
    function self:retire_owned(row,kind,verify_retired)
        assert(identity(row)and type(verify_retired)=='function','native retirement identity/probe required')
        assert(kind=='local_body'or kind=='controller'or kind=='remote_ghost'or kind=='training_target',
            'unknown retirement kind')
        local registered=self.owned[row.address]
        assert(not registered or(same(registered,row)and registered.kind==kind),'owned retirement identity changed')
        assert(self.closed or not self.local_transition or self.local_transition.address~=row.address,
            'local ownership transition is still pending')
        local world=self.world
        assert(verify_retired()==true,'native Actor retirement not acknowledged')
        assert(self.world==world and self.owned[row.address]==registered,'ownership changed during retirement readback')
        if not registered then return true end
        self.owned[row.address]=nil;self.owned_count=self.owned_count-1
        assert(self.owned_count>=0,'owned retirement count underflow')
        if same(self.local_body,row)then
            self.local_body,self.body_actor,self.snapshot_current=nil,nil,false
            if not self.closed then state:body_changed(host.now())end
        end
        return true
    end
    function self:exclude(actor,addr)
        local owned=self.owned[addr]
        if not owned then return false end
        -- Address reuse is not ownership. Re-read only matching addresses, not every NPC.
        local ok,current=pcall(host.identify,actor,self.world)
        return ok and same(owned,current)
    end
    function self:filter(actors,addresses)
        assert(type(actors)=='table' and type(addresses)=='table' and #actors==#addresses,'parallel enemy arrays required')
        if self.owned_count==0 then return actors,addresses end
        local out,addrs={},{}
        for index,actor in ipairs(actors) do
            if not self:exclude(actor,addresses[index]) then
                out[#out+1],addrs[#addrs+1]=actor,addresses[index]
            end
        end
        return out,addrs
    end
    function self:allow_enemy_name(name) return fence:allow_name(name) end
    function self:allow_enemy_event(kind,...) return combat_events[kind]==true and fence:allow_event(kind,...) end
    function self:allow_enemy_actor(actor,addr)
        if actor==nil then return true end
        if addr==nil then
            local ok,value=pcall(function() return actor:GetAddress() end)
            if not ok then return false end
            addr=value
        end
        return not self:exclude(actor,addr)
    end
    function self:allow_legacy_ghost()
        -- Boss classes cannot fall through to the receiver's own Pawn class.
        return not self.closed and not self.local_transition and state.ready and state.boss=='native'
            and state.remote and state.remote.boss=='native'
    end
    function self:remote_body_request()
        if self.local_transition or not state.ready then return nil,'identity handshake incomplete' end
        local path=state:remote_class()
        if path then return path,'Boss ghost assembly contract pending' end
        return nil,'native body'
    end
    function self:network_body()
        -- The observer verifies ownership at 10 Hz. Per-frame state sends resolve
        -- only that actor, never enumerate NPCs or fall back to a hidden player.
        if self.closed or self.local_transition or not self.snapshot_current or not state.ready
            or not self.body_actor or not self.local_body then return nil end
        local ok,current=pcall(host.identify,self.body_actor,self.world)
        if not ok or not same(current,self.local_body) then return nil end
        return self.body_actor,current.address
    end
    function self:begin_local_transition(row)
        assert(not self.closed and not self.local_transition,'local body transition already pending or closed')
        assert(identity(row) and self.owned[row.address]==row and row.kind=='local_body'
            and row.world==self.world and class_to_boss[row.class],'registered same-World local Boss required')
        local token={world=self.world,address=row.address}
        self.local_transition=token
        state:body_changed(host.now())
        return token
    end
    function self:refresh_local_body()
        if self.closed then return false end
        if self.revoking then self.refresh_pending=true;return true end
        self.last_poll=-math.huge
        local ok,why=pcall(self.poll,self)
        if not ok then state:set_link(false,host.now());revoke('body observation failed: '..tostring(why));return false end
        return self.snapshot_current==true and self.local_body~=nil and not self.restore_pending
    end
    function self:finish_local_transition(token)
        assert(token~=nil and self.local_transition==token,'stale local body transition token')
        self.local_transition=nil
        return self:refresh_local_body()
    end
    local handler=function(line,from)
        if self.closed or not net.enabled or not coop.linked() or net.party or net.pvp or net.role=='local' then return false end
        -- Native two-player relay has no @slot; accept @2 only on host for forwarded input.
        if from~=nil and not (role=='host' and from==2) then return false end
        return state:receive(line,role=='host' and 'guest' or 'host',host.now())
    end
    coop.handlers[protocol.EVENT]=handler
    local wrapped_list=function(...) return self:filter(original_list(...)) end
    local wrapped_cached=function(...) return self:filter(original_cached(...)) end
    game.listEnemies,game.enemiesSoFar=wrapped_list,wrapped_cached
    function self:poll()
        if self.closed then return end
        local now=host.now()
        if now-self.last_poll<0.1 then return end
        self.last_poll=now
        self.refresh_pending=false
        self.snapshot_current=false
        self.body_actor=nil
        local ok,snapshot=pcall(host.snapshot)
        if not ok or type(snapshot)~='table' or not identity(snapshot.body)
            or type(snapshot.world)~='string' or snapshot.body.world~=snapshot.world then
            state:set_link(false,now); revoke('no valid local world/body'); return
        end
        if net.party or net.pvp or net.role=='local' or (coop.isHost() and 'host' or 'guest')~=role then
            state:set_link(false,now); revoke('only fixed-role two-player online co-op supported'); return
        end
        if self.world~=snapshot.world then
            state:world_changed(now)
            self.owned,self.owned_count,self.local_body={},0,nil
            self.local_transition=nil
            fence:reset()
            self.world=snapshot.world
        end
        local boss=class_to_boss[snapshot.body.class]
        if not boss and snapshot.native_player~=true then
            state:set_link(false,now); revoke('unknown local Pawn class'); return
        end
        if not same(self.local_body,snapshot.body) then
            -- Retired same-world bodies remain excluded until the world retires.
            self:register(snapshot.body,'local_body')
            self.local_body=snapshot.body
            if not state:select(boss or 'native',now) then state:body_changed(now) end
        end
        self.snapshot_current=true
        self.body_actor=snapshot.body_actor
        state:set_link(net.enabled==true and coop.linked()==true,now)
        state:tick(now)
    end
    function self:close()
        if self.closed then return not self.restore_pending end
        self.closed=true
        revoke('bridge closed')
        if coop.handlers[protocol.EVENT]==handler then coop.handlers[protocol.EVENT]=nil end
        if game.listEnemies==wrapped_list then game.listEnemies=original_list end
        if game.enemiesSoFar==wrapped_cached then game.enemiesSoFar=original_cached end
        state:close()
        self.owned,self.owned_count={},0
        if self.cancel then self.cancel() end
        return not self.restore_pending
    end
    local scheduled,cancel=pcall(host.schedule,100,function()
        local ok,why=pcall(self.poll,self)
        if not ok then
            -- A failed observer must not leave the previous handshake ready.
            state:set_link(false,host.now()); revoke('adapter exception: '..tostring(why))
        end
        return self.closed
    end)
    if not scheduled or type(cancel)~='function' then
        self:close()
        error('cancellable scheduler required: '..tostring(cancel))
    end
    self.cancel=cancel
    host.log('BWB control plane attached; Boss body/ability execution remains unaccepted')
    return self
end
return M
