-- Phantom Pact 1.7.3 adapter. The pure protocol is injected by the pinned builder.
-- Owns only its BWB1 handler and a bounded identity registry, never player inventory.
local M = {}
local function identity(row)
    return type(row)=='table' and type(row.address)=='number' and row.address>0
        and type(row.name)=='string' and #row.name>0 and type(row.class)=='string'
        and type(row.world)=='string' and #row.world>0
end
local function same(a,b)
    return identity(a) and identity(b) and a.address==b.address and a.name==b.name
        and a.class==b.class and a.world==b.world
end

function M.attach(api, config, host, protocol)
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
    local role=coop.isHost() and 'host' or 'guest'
    local function revoke(reason)
        self.status=reason
        if self.revoked_reason==reason then return end
        self.revoked_reason=reason
        coop.retireWorkbenchGhosts() -- park old native clones before accepting another identity
        host.on_revoke(reason) -- launcher/controller must revoke its research possession lease
    end
    local state = protocol.new { role=role, session=config.session, catalog=config.catalog_sha256,
        build=config.exe_sha256, bosses=config.bosses,
        send=function(kind,line) coop.sendEvent(kind,line) end,
        on_ready=function(on,reason)
            self.status=on and 'identity ready; Boss ghost assembly unaccepted' or reason
            if on then self.revoked_reason=nil end
            if not on then revoke(reason) end
        end,
        on_clear=function(reason) revoke(reason) end,
        on_identity=function() self.remote_body_pending=true end,
        -- Explicitly no on_action: the control plane cannot grant an ability or apply a hit.
    }
    self.protocol=state
    local class_to_boss={}
    for id,row in pairs(config.bosses) do class_to_boss[row.class_path]=id end
    function self:register(row,kind)
        assert(not self.closed and identity(row),'valid current-world identity required')
        assert(row.world==self.world,'cannot own another world actor')
        assert(kind=='local_body' or kind=='remote_ghost' or kind=='training_target' or kind=='controller')
        local old=self.owned[row.address]
        if not old then assert(self.owned_count<32,'owned actor limit'); self.owned_count=self.owned_count+1 end
        self.owned[row.address]={address=row.address,name=row.name,class=row.class,world=row.world,kind=kind}
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
    function self:allow_legacy_ghost()
        -- Boss classes cannot fall through to the receiver's own Pawn class.
        return not self.closed and state.ready and state.boss=='native'
            and state.remote and state.remote.boss=='native'
    end
    function self:remote_body_request()
        if not state.ready then return nil,'identity handshake incomplete' end
        local path=state:remote_class()
        if path then return path,'Boss ghost assembly contract pending' end
        return nil,'native body'
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
        state:set_link(net.enabled==true and coop.linked()==true,now)
        state:tick(now)
    end
    function self:close()
        if self.closed then return end
        self.closed=true
        if coop.handlers[protocol.EVENT]==handler then coop.handlers[protocol.EVENT]=nil end
        if game.listEnemies==wrapped_list then game.listEnemies=original_list end
        if game.enemiesSoFar==wrapped_cached then game.enemiesSoFar=original_cached end
        state:close()
        self.owned,self.owned_count={},0
        if self.cancel then self.cancel() end
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
