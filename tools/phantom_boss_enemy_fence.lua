-- Quarantine only locally proven owned actors. Called on ownership transitions,
-- never a per-frame actor search. No health, AI, ability, inventory or save writes.
local M = {}
local id_maps = {
    'remoteEnemies','hostLethal','deadSent','guestKilled','guestKillSent','pendingDeaths',
    'notOnHost','bossAsk','bringing','broughtBack','pendingBosses','partnerBosses',
    'foggedBosses','hostKilled','hostBosses','lethalPending','healTicks','hostSeen',
    'hitHere','postureTicks','guestRuns','guestLines','mine','fightOf','struck',
    'killedAt','mirrorOn','bossFell','extraBossWatch','fellInFight','spawnedFor',
}
local enemy_events = {D=true,K=true,GK=true,LR=true,RUN=true,B=true,BEATEN=true,
    HAS=true,NOT=true,A=true,HX=true}
local function compact(list,addresses,cursor,remove)
    local out,addrs,before={},{},0
    for index,item in ipairs(list or {}) do
        local addr=addresses and addresses[index] or nil
        if not remove(item,addr) then
            out[#out+1]=item
            if addresses then addrs[#addrs+1]=addr end
            if index<(cursor or 1) then before=before+1 end
        end
    end
    return out,addrs,before+1
end

function M.new(coop,game,is_owned)
    assert(type(coop.workbenchEnemyState)=='function','pinned enemy-cache view required')
    assert(type(is_owned)=='function')
    local self={blocked={},blocked_count=0}
    function self:reset()
        self.blocked,self.blocked_count={},0
    end
    function self:allow_name(name) return self.blocked[name]~=true end
    function self:allow_event(kind,first,second)
        if kind=='N' or kind=='NQ' then
            local name=second
            if name==nil and type(first)=='string' then name=first:match('^%d+ (%S+) %S+$') end
            return self:allow_name(name)
        end
        if enemy_events[kind] and type(first)=='string' then
            return self:allow_name(first:match('^(%S+)'))
        end
        return true
    end
    function self:purge(row)
        local view=assert(coop.workbenchEnemyState())
        local net,reach,round,handover=view.net,view.reach,view.round,view.handover
        local names={}
        local function owned(actor,addr)
            if actor==nil then return false end
            if addr==nil then
                local ok,value=pcall(function() return actor:GetAddress() end)
                if not ok then return false end
                addr=value
            end
            return addr==row.address and is_owned(actor,addr)
        end
        for name,actor in pairs(view.names) do
            if owned(actor) then names[name]=true end
        end
        for _,entry in ipairs(round.queue or {}) do
            if type(entry.name)=='string' and owned(entry.actor,entry.addr) then names[entry.name]=true end
        end
        local aside=net.aside[row.address]
        if aside and type(aside.name)=='string' and owned(aside.actor,row.address) then names[aside.name]=true end
        for name,entry in pairs(net.mirrorOn or {}) do
            if owned(entry.actor,entry.addr) then names[name]=true end
        end
        for name in pairs(names) do
            if not self.blocked[name] then
                assert(self.blocked_count<512,'owned enemy alias limit reached')
                self.blocked[name]=true;self.blocked_count=self.blocked_count+1
            end
            view.names[name]=nil
            local number=net.enemyNumbers[name]
            if number~=nil then
                net.enemyNumbers[name]=nil;net.announced[number]=nil
                if net.linesSent then net.linesSent[number]=nil end
            end
            for _,key in ipairs(id_maps) do if net[key] then net[key][name]=nil end end
            net.matchSticky[name]=nil
            view.seen[name]=nil
            if round.seen then round.seen[name]=nil end
            for _,key in ipairs({'seen','since','retryAt'}) do handover[key][name]=nil end
        end
        -- A sticky address without a matching actor proves no remote identity. Drop
        -- that stale association, but let the ordinary remote enemy be matched again.
        for name,addr in pairs(net.matchSticky) do
            if addr==row.address and view.names[name]==nil then net.matchSticky[name]=nil end
        end
        for number,entry in pairs(net.enemyNames) do
            if names[entry.name] then net.enemyNames[number]=nil end
        end
        for name,entry in pairs(view.seen) do
            if entry.addr==row.address and view.names[name]==nil then view.seen[name]=nil end
        end
        if round.seen then
            for name,entry in pairs(round.seen) do
                if entry.addr==row.address and view.names[name]==nil then round.seen[name]=nil end
            end
        end
        local function owned_entry(entry,addr) return owned(entry.actor,addr or entry.addr) end
        if reach.near[row.address] and owned_entry(reach.near[row.address],row.address) then
            reach.near[row.address]=nil
        end
        reach.list,reach.addrs,reach.at=compact(reach.list,reach.addrs,reach.at,owned)
        local queue,unused,at=compact(round.queue,nil,round.at,owned_entry)
        round.queue,round.at=queue,at
        if net.heldAlive[row.address] and owned(net.heldAlive[row.address],row.address) then
            net.heldAlive[row.address]=nil
        end
        if round.held and owned(round.held[row.address],row.address) then round.held[row.address]=nil end
        aside=net.aside[row.address]
        if aside and owned_entry(aside,row.address) then net.aside[row.address]=nil end
        net.deadBodies[row.address]=nil
        -- Unlike release(), this erases the puppet record without starting AI or
        -- restoring health/poise on a body whose controller is taking ownership.
        if view.puppets then
            assert(type(view.puppets.forgetWorkbenchActor)=='function','pinned puppet-cache removal required')
            view.puppets.forgetWorkbenchActor(row.address,owned,names)
        end
        return names
    end
    return self
end
return M
