-- Generation-bound cosmetic frames. No ability execution or hit authority.
local M={EVENT='BWV1'}
local LIMIT=2147483647
local function number(n,lo,hi)return type(n)=='number' and n==n and n>-math.huge and n<math.huge and n>=lo and n<=hi end
local function integer(n,lo)return number(n,lo,LIMIT) and n==math.floor(n)end
local function path(s)return type(s)=='string' and #s<=256 and s:match('^/[%w_/%-]+%.[%w_%-]+$')end
function M.new(o)
    assert(o.role=='host' or o.role=='guest')
    assert(type(o.session)=='string' and o.session:match('^[%w_%-]+$') and #o.session<=48)
    for _,name in ipairs({'now','send','snapshot','world','attest','log'})do assert(type(o[name])=='function',name)end
    for _,name in ipairs({'mount','update','destroy'})do assert(type(o.native[name])=='function',name)end
    local catalog={}
    for boss,sequences in pairs(o.animations)do
        assert(o.bosses[boss]);catalog[boss]={}
        for asset,duration in pairs(sequences)do
            assert(path(asset) and number(duration,.001,600));catalog[boss][asset]=duration
        end
    end
    local peer=o.protocol
    local self={closed=false,last_send=-math.huge,sequence=0,remote_sequence=0,counters={}}
    local function count(key)self.counters[key]=(self.counters[key] or 0)+1;return false,key end
    local function ready()
        return not self.closed and peer.ready and peer.connected and peer.remote
            and o.bosses[peer.boss] and o.bosses[peer.remote.boss]
    end
    local function pose(frame,boss)
        if frame.animation=='-' then return frame.time==0 end
        local duration=catalog[boss] and catalog[boss][frame.animation]
        return duration and number(frame.time,0,duration)
    end
    local function valid(frame,boss)
        return integer(frame.map,1) and number(frame.x,-20000000,20000000)
            and number(frame.y,-20000000,20000000) and number(frame.z,-20000000,20000000)
            and number(frame.yaw,-360,360) and pose(frame,boss)
    end
    local function recovery_clock()
        local ok,now=pcall(o.now)
        if ok and number(now,0,math.huge-1) then return now end
    end
    function self:invalidate(reason,automatic)
        self.pending=nil
        self.applied_frame=nil
        if automatic and self.restore_pending then
            local now=recovery_clock()
            if not now or (self.retry_after and now<self.retry_after) then return false end
        end
        if self.record then
            local ok,clean=pcall(o.native.destroy,self.record)
            self.restore_pending=not ok or clean~=true
            if not self.restore_pending then self.record=nil end
        end
        if self.restore_pending then
            local now=recovery_clock();self.retry_after=now and now+.25 or nil
        else self.retry_after=nil end
        self.reason=reason
        return not self.restore_pending
    end
    function self:receive(line,sender)
        if not ready() then return count('not_ready')end
        if sender~=(o.role=='host' and 'guest' or 'host') then return count('sender')end
        if type(line)~='string' or #line>850 or line:find('[\r\n\t]') then return count('malformed')end
        local t={};for word in line:gmatch('%S+')do t[#t+1]=word end
        if #t~=14 or t[1]~='1' then return count('malformed')end
        local gen,sequence,ack=tonumber(t[3]),tonumber(t[4]),tonumber(t[7])
        if t[2]~=o.session or t[5]~=sender or t[6]~=peer.remote.boss
            or gen~=peer.remote.generation or ack~=peer.generation
            or not integer(gen,1) or not integer(ack,1) or not integer(sequence,1) then return count('identity')end
        local key=gen..'|'..ack..'|'..t[6]
        if key==self.remote_key and sequence<=self.remote_sequence then return count('stale')end
        local frame={map=tonumber(t[8]),x=tonumber(t[9]),y=tonumber(t[10]),z=tonumber(t[11]),
            yaw=tonumber(t[12]),animation=t[13],time=tonumber(t[14]),boss=t[6],key=key,received=o.now()}
        if not valid(frame,t[6]) then return count('pose')end
        -- No remote asset load or native operation runs in the network handler.
        self.remote_key,self.remote_sequence,self.pending=key,sequence,frame
        return true
    end
    local function update()
        o.attest(false)
        if not ready() then self:invalidate('identity not ready',true);return end
        local world,map,local_position=o.world()
        assert(type(world)=='string' and #world>0 and integer(map,1),'current visual World/map required')
        if world~=self.world then
            local clean=self:invalidate('local World changed',true);self.world=world
            if not clean then return end
        end
        local now=o.now();assert(number(now,0,math.huge-1),'invalid visual clock')
        local local_key=peer.generation..'|'..peer.remote.generation..'|'..peer.boss
        if local_key~=self.local_key then self.local_key=local_key;self.sequence=0;self.last_send=-math.huge end
        if now-self.last_send>=.05 then
            self.last_send=now
            local frame=o.snapshot(peer.boss)
            if frame and frame.world==world and frame.map==map and valid(frame,peer.boss) then
                assert(self.sequence<LIMIT,'visual sequence exhausted');self.sequence=self.sequence+1
                local line=table.concat({'1',o.session,peer.generation,self.sequence,o.role,peer.boss,
                    peer.remote.generation,map,string.format('%.3f',frame.x),string.format('%.3f',frame.y),
                    string.format('%.3f',frame.z),string.format('%.3f',frame.yaw),frame.animation,
                    string.format('%.6f',frame.time)},' ')
                assert(#line<850,'visual packet exceeds relay bound');o.send(M.EVENT,line)
            end
        end
        -- Keep publishing the local pose while a failing remote renderer cools
        -- down. A valid packet alone cannot authorize frame-rate reconstruction.
        if self.pose_retry_at and now<self.pose_retry_at then return end
        local frame=self.pending
        local expected=peer.remote.generation..'|'..peer.generation..'|'..peer.remote.boss
        if not frame or frame.key~=expected or frame.map~=map or now-frame.received>.3 then
            self:invalidate('remote pose absent stale or on another map',true);return
        end
        assert(type(local_position)=='table' and number(local_position.x,-20000000,20000000)
            and number(local_position.y,-20000000,20000000) and number(local_position.z,-20000000,20000000))
        local dx,dy,dz=frame.x-local_position.x,frame.y-local_position.y,frame.z-local_position.z
        if dx*dx+dy*dy+dz*dz>50000^2 then self:invalidate('remote pose outside visual range',true);return end
        if self.record and self.record_key~=world..'|'..expected then
            if not self:invalidate('remote generation changed',true) then return end
            self.pending=frame
        end
        if self.restore_pending then return end
        -- One buffered packet owns one pose application. Timer jitter and relay
        -- gaps must not repeat native transforms/skeleton work for that packet.
        -- Freshness, World and generation checks still run before this shortcut.
        if self.record and self.applied_frame==frame then return end
        if not self.record then
            local remembered
            local record=o.native.mount(frame.boss,world,function(row)
                assert(not remembered,'one visual Actor per remote body')
                remembered=row;self.record=row;self.record_key=world..'|'..expected
            end)
            assert(record==remembered and record~=nil,'visual Actor must be recorded before construction')
        end
        assert(o.native.update(self.record,frame,world)==true,'visual pose update not acknowledged')
        self.applied_frame=frame
        self.pose_failures,self.pose_retry_at=0,nil
    end
    function self:tick()
        if self.closed then return end
        -- A continuous stream of valid poses must not strand a failed cleanup.
        -- Retire its recorded Actor at most four times per second, and require
        -- a fresh packet after recovery before constructing another body.
        if self.restore_pending then self:invalidate(self.reason,true);return end
        local ok,why=pcall(update)
        if not ok then
            self.pose_failures=math.min((self.pose_failures or 0)+1,4)
            local now=recovery_clock()
            self.pose_retry_at=now and now+.25*2^(self.pose_failures-1) or nil
            self:invalidate('visual update failed: '..tostring(why),true)
            if self.last_error~=self.reason then self.last_error=self.reason;o.log(self.reason)end
        end
    end
    function self:close()
        self.closed=true
        return self:invalidate('visual closed')
    end
    return self
end
return M
