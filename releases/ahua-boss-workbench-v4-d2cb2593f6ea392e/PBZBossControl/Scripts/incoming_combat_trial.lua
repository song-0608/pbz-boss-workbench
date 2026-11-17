-- 开发死亡验收：仅让本轮两个训练角色反复使用已授予技能07攻击自建Boss。
-- 所有伤害来自原生招式；不写属性、不构造伤害值、不启动自主AI。
local Trial={};Trial.__index=Trial
function Trial.new(api)
    return setmetatable({api=api,used=false,running=false,sources={}},Trial)
end
function Trial:stop()
    if self.stopped then return true end
    self.running=false
    local api=self.api
    for _,source in ipairs(self.sources)do
        local spec=api.spec(source.actor)
        if source.started and spec.ActiveCount>0 then
            assert(api.cancel(spec)==true and spec.ActiveCount==0,'incoming source cancellation failed')
        end
        api.clear(source.actor)
    end
    if #self.sources>0 then api.log('INCOMING_COMBAT_STOP','all_source_abilities_inactive=true')end
    self.stopped=true
    if api.observe then api.observe('stopped')end
    return true
end
function Trial:watch_restored()
    if not self.used or self.watching or not self.api.observe then return end
    self.watching=true
    local api=self.api
    local until_at=math.min(api.now()+60,api.attest().expires_at-10)
    api.log('INCOMING_COMBAT_POST_RESTORE_BEGIN','seconds='..(until_at-api.now()))
    local function poll()
        if not self.watching or api.session.receipt then self.watching=false;return end
        local ok,why=pcall(function()
            api.attest()
            api.observe('after_restore')
            if api.now()>=until_at then
                self.watching=false;api.log('INCOMING_COMBAT_POST_RESTORE_END',true);return
            end
            api.schedule(poll)
        end)
        if not ok then self.watching=false;api.log('INCOMING_COMBAT_POST_RESTORE_REJECTED',why)end
    end
    poll()
end
function Trial:start()
    local api=self.api
    assert(not self.used and api.session.state=='ACTIVE'and api.session.receipt and not api.session.current_skill,
        'one idle active owned combat trial required')
    local grant=api.attest()
    assert(grant.expires_at-api.now()>390,'six minute combat trial plus cleanup margin required')
    self.used=true;self.receipt=api.session.receipt
    self.expires=api.now()+360;self.running=true;self.stopped=false
    for _,actor in ipairs(api.sources)do
        api.validate(actor)
        assert(api.spec(actor).ActiveCount==0,'source skill already active')
        self.sources[#self.sources+1]={actor=actor,casts=0,attempts=0,next_at=0}
    end
    self.health=api.health()
    assert(self.health>0,'living owned target required')
    api.log('INCOMING_COMBAT_BEGIN','health='..self.health..'|sources='..#self.sources..'|seconds=360')
    self:poll()
end
function Trial:poll()
    if not self.running then return end
    local api=self.api
    local ok,why=pcall(function()
        assert(api.attest().expires_at>api.now()+15,'incoming combat grant exhausted')
        assert(api.session.state=='ACTIVE'and api.session.receipt==self.receipt,'control receipt changed')
        local health=api.health()
        if health~=self.health then
            api.log('INCOMING_COMBAT_HEALTH','before='..self.health..'|after='..health)
            self.health=health
        end
        if health<=0 then self:stop();api.log('INCOMING_COMBAT_DEPLETED',true);return end
        if api.now()>=self.expires then self:stop();api.log('INCOMING_COMBAT_TIMEOUT','health='..health);return end
        for _,source in ipairs(self.sources)do
            api.validate(source.actor)
            local spec=api.spec(source.actor)
            if spec.ActiveCount>0 then
                assert(source.started and api.now()-source.started<=25,'incoming source ability hung')
            elseif api.now()>=source.next_at and source.casts<32 and source.attempts<160 then
                source.started=nil;source.attempts=source.attempts+1
                api.target(source.actor)
                local activated=api.activate(spec,source.actor)
                source.next_at=api.now()+2
                if activated then
                    source.casts=source.casts+1;source.started=api.now()
                    api.log('INCOMING_COMBAT_CAST',api.name(source.actor)..'|skill=skill_07|number='..source.casts..'|active='..spec.ActiveCount)
                    if api.observe then api.observe('cast')end
                elseif source.attempts==1 then api.log('INCOMING_COMBAT_REJECTED',api.name(source.actor))end
            end
        end
        api.schedule(function()self:poll()end)
    end)
    if not ok then
        local clean,problem=pcall(self.stop,self)
        api.log('ISSUE_INCOMING_COMBAT',tostring(why)..'|cleanup='..tostring(clean)..'|'..tostring(problem))
    end
end
return Trial
