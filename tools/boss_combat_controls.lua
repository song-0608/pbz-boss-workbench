-- Optional development assembly. An unreviewed focus/key source cannot enable defense.
-- This module owns arbitration/lifecycle only; abilities and particles remain native.
local Controls={};Controls.__index=Controls
function Controls.attach(session,options)
    assert(not session.native_combat_controls,'combat controls already attached')
    assert(options and options.developer_only==true and type(options.now)=='function'
        and type(options.input_allowed)=='function','development combat host required')
    if options.native_input then
        assert(options.native_input.binding_verified==true,'reviewed native input module binding required')
        local gate=options.input_allowed
        local native=require('boss_native_input').new(options.globals,options.native_input.pid,gate)
        local copied={};for key,value in pairs(options)do copied[key]=value end;options=copied
        options.now=function()return native:now()end
        options.input_allowed=function()return native:allowed(session.receipt)end
        options.read_defense=function(receipt,key)return native:read(receipt,key)end
        options.input_binding_verified=true;options.focus_binding_verified=true
    end
    local defense=options.defense
    if defense then
        assert(options.input_binding_verified==true and type(options.read_defense)=='function'
            and options.focus_binding_verified==true,'verified held-key and focus source required')
        assert(type(defense.key)=='string'and defense.key~='','explicit defense key required')
        for _,key in pairs(session.config.controls or{})do
            assert(key~=defense.key,'defense key conflicts with a control')
        end
        for _,row in pairs(session.config.skills or{})do
            assert(row.verified~=true or row.key~=defense.key,'defense key conflicts with a skill')
        end
    end
    local self=setmetatable({session=session,options=options,receipt=nil,defense=nil,cue=nil,
        cleanup_pending=false,failed=nil},Controls)
    local bridge=session.bridge
    local enter,restore,skill=session.enter,session.restore,session.skill
    local boundary=session.world_boundary
    local request,flush=session.request_skill,session.flush_buffered_skill
    local verify_restored=bridge.verify_restored
    function bridge:verify_restored(receipt,...)
        if self==session.bridge and self.active_receipt==receipt
            and session.native_combat_controls.cleanup_pending then return false end
        return verify_restored(self,receipt,...)
    end
    function session:enter(...)
        assert(not self.native_combat_controls.receipt,'previous combat cleanup incomplete')
        local ok,why=enter(self,...)
        if ok~=true then return ok,why end
        local attached,problem=pcall(self.native_combat_controls.begin,self.native_combat_controls,self.receipt)
        if not attached then self:restore('native combat attach failed');return false,tostring(problem)end
        return ok,why
    end
    function session:restore(...)
        -- Classify a map transition before touching the previous ASC/action.
        -- Base retirement may already have proved disposal and retired combat.
        if self.native_combat_controls.receipt and self.world_boundary then
            local status,why=self:world_boundary()
            if status=='retired'then return true end
            if status~='same'then return false,why or'world transition pending or unverified'end
        end
        local clean,errors=self.native_combat_controls:cleanup()
        -- Always attempt the original player/camera restoration, even on cleanup failure.
        local ok,why=restore(self,...)
        if not clean then self.state='FAULTED';return false,table.concat(errors,'; ')end
        return ok,why
    end
    if boundary then
        function session:world_boundary(...)
            local status,why=boundary(self,...)
            if status=='retired'and self.native_combat_controls.receipt then
                local ok,problem=pcall(self.native_combat_controls.retire,self.native_combat_controls)
                if not ok then
                    self.state='FAULTED'
                    self.native_combat_controls.cleanup_pending=true
                    self.native_combat_controls.failed='combat retirement: '..tostring(problem)
                    return 'faulted',self.native_combat_controls.failed
                end
            end
            return status,why
        end
    end
    function session:sample_combat_input(input)
        if input and input.allowed~=true then
            if self.native_combat_controls.defense then
                self.native_combat_controls.defense:step({down=false,allowed=false})
            end
            if self.native_combat_controls.cue then
                assert(self.native_combat_controls.cue:cleanup(),'suspended cue cleanup failed')
            end
            return false,'input suspended'
        end
        return self.native_combat_controls:sample()
    end
    local function allowed()
        local c=session.native_combat_controls
        if c.receipt~=session.receipt then return false,'combat receipt changed'end
        if c.failed then return false,c.failed end
        -- A key callback between frames takes its own fresh focus/held sample.
        if c:sample()~=true then
            if session.clear_buffered_skill then session:clear_buffered_skill('input suspended')end
            return false,'combat input suspended'
        end
        if c.defense and c.defense:blocks_action()then
            if session.clear_buffered_skill then session:clear_buffered_skill('defense held')end
            return false,'native defense held'
        end
        return true
    end
    function session:skill(...)
        if self.state~='ACTIVE'or not self.receipt then return skill(self,...)end
        local ok,why=allowed();if not ok then return false,why end
        return skill(self,...)
    end
    if request then
        function session:request_skill(...)
            if self.state=='ACTIVE'and self.receipt then
                local ok,why=allowed();if not ok then return false,why end
            end
            return request(self,...)
        end
    end
    if flush then
        function session:flush_buffered_skill(...)
            if not self.buffered_skill then return flush(self,...)end
            local ok=allowed()
            if not ok then
                if self.clear_buffered_skill then self:clear_buffered_skill('combat input suspended')end
                return true
            end
            return flush(self,...)
        end
    end
    session.native_combat_controls=self
    return self
end
function Controls:begin(receipt)
    assert(not self.receipt and self.session.state=='ACTIVE'and self.session.receipt==receipt,
        'new active combat receipt required')
    self.receipt=receipt;self.failed=nil;self.cleanup_pending=true
    if self.options.defense then
        self.defense=require('boss_defense_bridge').attach(self.session.bridge,receipt,
            self.options.defense,self.options.now,self.options.input_allowed,self.options.native_input and true)
        if self.options.log then self.options.log('NATIVE_DEFENSE_READY',self.options.defense.key)end
    end
    if self.options.cues then
        self.cue=require('boss_cue_bridge').new(self.session.bridge,self.options.globals,
            self.options.cues,self.options.input_allowed,function(label,why)
                self.cue_failure=label..': '..why
            end,self.options.log)
        local installed,problem=pcall(self.cue.install,self.cue)
        if not installed then
            local cue=self.cue
            -- Optional visual hooks must not block control after a clean rollback.
            assert(not cue.enabled and #cue.hooks==0 and cue.cues.size==0,problem)
            self.cue=nil
            if self.options.log then self.options.log('NATIVE_CUE_UNAVAILABLE',tostring(problem))end
        end
    end
    self.cleanup_pending=false
end
function Controls:sample()
    if not self.receipt then return true end
    assert(self.session.receipt==self.receipt and self.session.state=='ACTIVE','stale combat sample rejected')
    assert(not self.failed,self.failed)
    if self.cue_failure then
        local clean,errors=self.cue:close()
        assert(clean,self.cue_failure..' | '..table.concat(errors,'; '))
        if self.options.log then self.options.log('NATIVE_CUE_UNAVAILABLE',self.cue_failure)end
        self.cue,self.cue_failure=nil,nil
    end
    if not self.defense then
        local permitted=self.options.input_allowed()==true
        if not permitted and self.cue then assert(self.cue:cleanup(),'focus-loss cue cleanup failed')end
        return permitted
    end
    -- Busy is observed from the session, never guessed from elapsed animation time.
    self.receipt.combat_action_active=self.session.current_skill~=nil
    local input=self.options.read_defense(self.receipt,self.options.defense.key)
    assert(type(input)=='table'and type(input.down)=='boolean'and type(input.allowed)=='boolean',
        'verified native defense sample unreadable')
    local permitted=input.allowed
    if permitted and not self.options.native_input then permitted=self.options.input_allowed()==true end
    local _,why=self.defense:step({allowed=permitted,down=input.down,now=input.now})
    if self.defense_status~=why then
        self.defense_status=why
        if self.options.log then self.options.log('NATIVE_DEFENSE_STATE',why)end
    end
    if why=='suspended' then permitted=false end
    if not permitted and self.cue then assert(self.cue:cleanup(),'suspended cue cleanup failed')end
    if self.defense:blocks_action()and self.session.clear_buffered_skill then
        self.session:clear_buffered_skill('defense held')
    end
    return permitted,why
end
function Controls:cleanup()
    if not self.receipt then return true,{}end
    if self.disposal_verified then
        local ok,why=pcall(self.retire,self)
        self.cleanup_pending=not ok
        return ok,ok and{}or{tostring(why)}
    end
    local errors={}
    local function attempt(label,fn)
        local ok,result,why=pcall(fn)
        if not ok or result~=true then errors[#errors+1]=label..': '..tostring(ok and why or result)end
    end
    if self.defense then attempt('defense',function()return self.defense:release('restoring player')end)end
    if self.cue then attempt('cues',function()
        local ok,why=self.cue:close();return ok,table.concat(why,'; ')
    end)end
    self.cleanup_pending=#errors>0
    if not self.cleanup_pending then
        self.receipt.combat_action_active=nil
        if self.receipt.native_defense==self.defense then self.receipt.native_defense=nil end
        self.receipt,self.defense,self.cue,self.cue_failure=nil,nil,nil,nil
        self.defense_status=nil
    end
    return not self.cleanup_pending,errors
end
function Controls:retire()
    -- The base World boundary has proved disposal of every modified participant.
    -- No cancellation through a dead ASC or effect cleanup in a replacement World.
    local r=assert(self.receipt,'retiring combat receipt required')
    assert(r.world_retired==true and(self.session.state=='OFF'
        or self.disposal_verified and self.session.state=='FAULTED')and not self.session.receipt
        and self.session.bridge.active_receipt~=r,'base World disposal proof required')
    self.disposal_verified=true
    if self.cue then
        local ok,why=self.cue:retire()
        assert(ok,'retired cue hook cleanup failed: '..table.concat(why,'; '))
    end
    if r.native_defense==self.defense then r.native_defense=nil end
    r.combat_action_active=nil
    self.receipt,self.defense,self.cue,self.cue_failure=nil,nil,nil,nil
    self.defense_status=nil
    self.cleanup_pending=false
    self.disposal_verified=nil
end
return Controls
