-- Pure Lua control plane. No UObject calls, file I/O, damage or ability activation.
-- The transport authenticates the sender slot; payload roles are checked again here.
local M = { VERSION = 1, EVENT = 'BWB1' }
local MAX_INT = 2147483647
local function integer(n, minimum)
    return type(n) == 'number' and n == math.floor(n) and n >= minimum and n <= MAX_INT
end
local function token(s, max)
    return type(s) == 'string' and #s > 0 and #s <= max and s:match('^[%w_%-]+$') ~= nil
end
local function digest(s)
    return type(s) == 'string' and #s == 64 and s:match('^[0-9a-f]+$') ~= nil
end
local function clock_value(now)
    assert(type(now) == 'number' and now == now and now >= 0 and now < math.huge, 'invalid clock')
end

function M.new(options)
    assert(options.role == 'host' or options.role == 'guest', 'two-player role required')
    assert(token(options.session, 48), 'explicit research session required')
    assert(digest(options.catalog) and digest(options.build), 'pinned catalog/build required')
    assert(type(options.bosses) == 'table' and type(options.send) == 'function')
    local self = { role = options.role, session = options.session, generation = 0,
        sequence = 0, remote = nil, remote_floor = 0, remote_sequence = 0,
        connected = false, ready = false, boss = 'native', last_send = -math.huge,
        last_receive = nil, sent_ack = 0, now = 0, counters = {}, stopped = false }
    local peer_role = options.role == 'host' and 'guest' or 'host'
    local bosses = {}
    for id, row in pairs(options.bosses) do
        assert(token(id, 48) and type(row) == 'table' and type(row.actions) == 'table')
        local actions = {}
        for action, path in pairs(row.actions) do
            assert(token(action, 48) and type(path) == 'string')
            actions[action] = path
        end
        bosses[id] = { class_path = row.class_path, actions = actions }
    end
    local function count(reason)
        self.counters[reason] = (self.counters[reason] or 0) + 1
        return false, reason
    end
    local function set_ready(on, reason)
        if self.ready == on then return end
        self.ready = on
        if options.on_ready then options.on_ready(on, reason) end
    end
    local function clear_peer(reason)
        set_ready(false, reason)
        if self.remote and options.on_clear then options.on_clear(reason) end
        self.remote, self.last_receive, self.sent_ack = nil, nil, 0
    end
    local function advance(reason)
        assert(self.generation < MAX_INT, 'generation exhausted: start a new research session')
        self.generation, self.sequence = self.generation + 1, 0
        self.last_send, self.sent_ack = -math.huge, 0
        set_ready(false, reason)
    end
    local function transmit(op, action)
        if not self.connected or self.stopped then return false end
        assert(self.sequence < MAX_INT, 'sequence exhausted')
        self.sequence = self.sequence + 1
        local ack = self.remote and self.remote.generation or 0
        local payload = table.concat({ M.VERSION, op, self.session, self.generation,
            self.sequence, self.role, self.boss, options.catalog, options.build, ack, action or '-' }, ' ')
        assert(#payload + #M.EVENT + 4 < 900, 'native relay MAX_TEXT exceeded')
        options.send(M.EVENT, payload)
        if op == 'H' then self.last_send, self.sent_ack = self.now, ack end
        return true
    end
    local function refresh_ready()
        local r = self.remote
        set_ready(self.connected and r ~= nil and r.ack == self.generation
            and self.sent_ack == r.generation, 'mutual identity acknowledgement')
    end
    function self:set_link(connected, now)
        clock_value(now); self.now = now
        assert(type(connected) == 'boolean')
        if self.stopped or self.connected == connected then return end
        self.connected = connected
        clear_peer(connected and 'transport connected' or 'transport disconnected')
        if connected then advance('transport connected') end
    end
    function self:select(boss, now)
        clock_value(now); self.now = now
        assert(boss == 'native' or bosses[boss], 'Boss absent from pinned catalog')
        if self.stopped or self.boss == boss then return false end
        self.boss = boss
        advance('local body changed')
        return true
    end
    function self:world_changed(now)
        clock_value(now); self.now = now
        clear_peer('world changed')
        advance('world changed')
    end
    function self:body_changed(now)
        clock_value(now); self.now = now
        advance('local body identity changed')
    end
    function self:tick(now)
        clock_value(now)
        assert(now >= self.now, 'clock moved backwards')
        self.now = now
        if self.stopped or not self.connected then return end
        if self.last_receive and now - self.last_receive >= 3 then
            clear_peer('peer timeout')
            advance('peer timeout')
        end
        if now - self.last_send >= 0.5 then transmit('H'); refresh_ready() end
    end
    function self:receive(payload, sender_role, now)
        clock_value(now); self.now = now
        if self.stopped or not self.connected then return count('not_connected') end
        if self.last_receive and now-self.last_receive>=3 then
            clear_peer('peer timeout'); advance('peer timeout')
        end
        if sender_role ~= peer_role then return count('sender_role') end
        if type(payload) ~= 'string' or #payload > 850 or payload:find('[\r\n\t]') then
            return count('malformed')
        end
        local t = {}; for part in payload:gmatch('%S+') do t[#t + 1] = part end
        if #t ~= 11 then return count('malformed') end
        local version, op, session = tonumber(t[1]), t[2], t[3]
        local gen, seq, role, boss = tonumber(t[4]), tonumber(t[5]), t[6], t[7]
        local catalog, build, ack, action = t[8], t[9], tonumber(t[10]), t[11]
        if version ~= M.VERSION or (op ~= 'H' and op ~= 'A')
            or not integer(gen, 1) or not integer(seq, 1) or not integer(ack, 0)
            or not token(boss, 48) or not token(action, 48) then return count('malformed') end
        if session ~= self.session then return count('session') end
        if role ~= peer_role then return count('payload_role') end
        if catalog ~= options.catalog or build ~= options.build then
            clear_peer('catalog or game build mismatch'); return count('incompatible')
        end
        if boss ~= 'native' and not bosses[boss] then return count('unknown_boss') end
        if ack > self.generation then return count('future_ack') end
        if gen < self.remote_floor or (gen == self.remote_floor and seq <= self.remote_sequence) then
            return count('stale')
        end
        if op == 'A' and (not self.ready or not self.remote or gen ~= self.remote.generation
            or boss ~= self.remote.boss or ack ~= self.generation
            or not bosses[boss] or not bosses[boss].actions[action]) then return count('action_not_ready') end
        if op == 'H' and action ~= '-' then return count('malformed') end
        if op == 'H' and self.remote and gen == self.remote.generation and boss ~= self.remote.boss then
            return count('identity_changed_without_generation')
        end
        local changed = not self.remote or gen ~= self.remote.generation
        if changed then
            clear_peer('remote body or world changed')
            self.remote = { generation = gen, boss = boss, ack = ack }
        end
        self.remote_floor, self.remote_sequence, self.last_receive = gen, seq, now
        self.remote.ack = ack
        if changed and options.on_identity then options.on_identity(boss, gen) end
        refresh_ready()
        if op == 'A' and options.on_action then
            -- This is a visual request, never authority to apply damage or grant abilities.
            options.on_action(boss, action, bosses[boss].actions[action], gen, seq)
        end
        return true
    end
    function self:action(action)
        if not self.ready then return count('local_not_ready') end
        if not bosses[self.boss] or not bosses[self.boss].actions[action] then return count('unknown_action') end
        return transmit('A', action)
    end
    function self:remote_class()
        if not self.ready or not self.remote then return nil end
        local row = bosses[self.remote.boss]
        return row and row.class_path or nil
    end
    function self:close()
        clear_peer('bridge closed'); self.connected, self.stopped = false, true
    end
    return self
end
return M
