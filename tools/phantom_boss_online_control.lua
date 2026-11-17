-- Online-specific orchestration around the immutable control/session/runtime
-- implementations. Supply their real modules from the pinned local dependency
-- folder; this file never calls the offline entry or supplies an offline proof.
local M={}
local function valid(o) return o and o:IsValid()==true end
function M.new(api,profile,config,scope,peer,host,dependencies)
    assert(type(scope)=='table' and type(scope.attest)=='function')
    assert(type(peer)=='table' and type(peer.begin_local_transition)=='function'
        and type(peer.finish_local_transition)=='function' and type(peer.refresh_local_body)=='function',
        'ownership transition adapter required')
    assert(type(api.owned_temporary)=='table' and type(api.usable)=='function','owned actor bindings required')
    assert(type(profile.instance_name)=='string','exact owned Boss instance required')
    assert(config.expected_exe_sha256==profile.exe_sha256,'local control build mismatch')
    assert(scope:attest(false).exe_sha256==profile.exe_sha256,'online scope game build mismatch')
    assert(peer:is_boss_class(profile.class_path),'Boss absent from online class whitelist')
    for _,definition in pairs(config.skills or {}) do
        if definition.verified then
            local skill=assert(profile.skills[definition.id],'missing local skill profile')
            assert(peer:resolve_local_action(profile.class_path,definition.id)==skill.class_path,
                'skill differs from online action whitelist')
        end
    end
    assert(type(dependencies)=='table' and type(dependencies.Bridge)=='table'
        and type(dependencies.Runtime)=='table','private pinned local dependencies required')
    local modules=dependencies
    local local_api={};for key,value in pairs(api) do local_api[key]=value end
    local_api.attest=function()return scope:attest(false)end
    local bridge=modules.Bridge.new(local_api,profile)
    local pending_transition,runtime,session
    local function control_ready()
        return peer.protocol.ready and not (peer.closed or peer.revoking or peer.revoked_reason
            or peer.restore_pending or peer.world_transition or (session and session.online_restore_pending)
            or (runtime and (runtime.online_stop_pending or runtime.online_stopped)))
    end
    -- Bridge's native methods retain their original build/object/World checks.
    -- Only their environment and the session's context policy are specialized.
    function bridge:environment() return scope:attest(self.online_restoring==true) end
    function bridge:context()
        local lease=self:environment()
        local pc=self.active_receipt and self.calls:resolve(self.active_receipt.player_controller) or self:player_controller()
        local boss_available
        if self.active_receipt then
            local ok,boss=pcall(self.calls.resolve,self.calls,self.active_receipt.boss)
            boss_available=ok and valid(boss) or false
        else boss_available=self:target(pc)~=nil end
        return {mode=lease.mode,isolated=lease.isolated,exe_sha256=lease.exe_sha256,
            world_id=self:world_id(pc,lease),boss_available=boss_available,restore_only=lease.restore_only}
    end
    local capture,take_control,can_start_skill=bridge.capture,bridge.take_control,bridge.can_start_skill
    function bridge:capture()
        scope:attest(false)
        -- Registration must precede possession, not wait for the next observer tick.
        for key,kind in pairs({boss='local_body',ai='controller'}) do
            local object=self.calls:resolve(local_api.owned_temporary[key])
            local addr=object:GetAddress();local row=peer.owned[addr]
            assert(row and row.kind==kind and peer:exclude(object,addr),'online actor ownership not registered: '..key)
        end
        return capture(self)
    end
    function bridge:take_control(receipt)
        pending_transition=peer:begin_local_transition(peer.owned[receipt.boss.address])
        local taken=take_control(self,receipt)
        if taken==true then
            assert(peer:finish_local_transition(pending_transition),'post-possession observation failed')
            pending_transition=nil
        end
        return taken
    end
    function bridge:can_start_skill(receipt,id)
        scope:attest(false)
        if not control_ready() then return false,'online peer or control recovery not ready' end
        return can_start_skill(self,receipt,id)
    end
    runtime=modules.Runtime.new(bridge,config,host)
    session=runtime.session
    function session:context()
        local ok,context=pcall(self.bridge.context,self.bridge)
        if not ok or type(context)~='table' then return nil,'online context unreadable' end
        if context.mode~='two-player-online-research' or context.isolated~=true
            or (context.restore_only and not bridge.online_restoring) then return nil,'online control not attested' end
        if context.exe_sha256~=self.config.expected_exe_sha256 then return nil,'game build mismatch' end
        if type(context.world_id)~='string' or context.world_id=='' then return nil,'missing World identity' end
        if self.world_id and context.world_id~=self.world_id then return nil,'World changed; stale receipt rejected' end
        return context
    end
    local enter,restore=session.enter,session.restore
    function session:enter()
        local ok=pcall(scope.attest,scope,false)
        if not ok or not control_ready() then return false,'online peer/control lease not ready' end
        return enter(self)
    end
    function session:restore(reason)
        local needs_observation=self.receipt~=nil or pending_transition~=nil or self.online_restore_pending==true
        -- Mark only this synchronous restore call as cleanup. No queued skill,
        -- input, capture or new possession may use the 15-second cleanup period.
        if self.receipt and not pending_transition and not peer.closed and not peer.revoking then
            local row=peer.owned[self.receipt.boss.address]
            if row then
                local started,token=pcall(peer.begin_local_transition,peer,row)
                if started then pending_transition=token end
            end
        end
        bridge.online_restoring=true
        local ok,result,why=pcall(restore,self,reason)
        bridge.online_restoring=false
        if not ok then
            self.online_restore_pending=true;self.state='FAULTED'
            self.online_restore_reason='online restore exception: '..tostring(result)
            pcall(self.record,self,'online restore exception: '..tostring(result));return false,result
        end
        if result~=true then
            self.online_restore_pending=needs_observation;self.online_restore_reason=tostring(why or 'native restore unverified')
            return result,why
        end
        if needs_observation and not peer.closed then
            local observed,current
            if pending_transition and peer.local_transition==pending_transition then
                observed,current=pcall(peer.finish_local_transition,peer,pending_transition)
            else observed,current=pcall(peer.refresh_local_body,peer) end
            if not observed or current~=true then
                self.online_restore_pending=true;self.state='FAULTED'
                self.online_restore_reason='restored local body observation unverified'
                return false,'restored local body observation unverified'
            end
        end
        pending_transition=nil;self.online_restore_pending=false;self.online_restore_reason=nil
        return result,why
    end
    -- Keep the pinned single-player runtime intact. Online shutdown owns each
    -- resource independently: a failed menu/key/timer must never skip restoring
    -- the native player, and failed resources remain available for retry.
    local start=runtime.start
    function runtime:start()
        -- A stopped owner must be replaced by the arena, never reactivated:
        -- its old game-thread callbacks may still be queued in the host.
        if self.online_stopped or session.online_restore_pending then return false,'online runtime retired or recovery pending' end
        return start(self)
    end
    function runtime:stop(reason)
        self.running=false;self.online_stopped=true;self.online_stop_pending=true
        local failures={}
        local function cleanup(label,fn,explicit)
            local ok,result,why=pcall(fn)
            if not ok or result==false or (explicit and result~=true) then
                failures[#failures+1]=label..': '..tostring(ok and (why or result) or result)
                return false
            end
            return true
        end
        if self.host.release_keys then cleanup('keys',self.host.release_keys) end
        if self.frame_handle then
            if cleanup('frame',function()return self.host.cancel_frame(self.frame_handle)end) then self.frame_handle=nil end
        end
        if self.host.workbench then
            cleanup('workbench',function()return self.host.workbench:shutdown()end,true)
        end
        cleanup('native player',function()return self.session:restore(reason or 'runtime stop')end,true)
        self.online_stop_pending=#failures>0
        local why=self.online_stop_pending and table.concat(failures,'; ') or nil
        self.online_stop_reason=why
        pcall(self.report,self,'stop',not self.online_stop_pending,why)
        return not self.online_stop_pending,why
    end
    local self={runtime=runtime,session=session,bridge=bridge,scope=scope}
    function self:observed_body()
        local receipt=bridge.active_receipt
        if not receipt or receipt.input_enabled~=true then return nil end
        scope:attest(false)
        assert(bridge:verify_control(receipt)==true,'controlled Boss readback failed')
        if not receipt.remote_control then return nil end -- native Possess is read by the ordinary host snapshot
        local body=bridge.calls:resolve(receipt.boss)
        assert(peer:is_boss_class(body:GetClass():GetFullName():match('^[^ ]+ (.+)$')),
            'observed body absent from online whitelist')
        return {verified=true,body=body,controller=bridge.calls:resolve(receipt.ai),
            player=bridge.calls:resolve(receipt.player),player_controller=bridge.calls:resolve(receipt.player_controller)}
    end
    function self:start() scope:attest(false);return runtime:start() end
    function self:revoke(reason)
        scope:revoke(reason)
        return runtime:stop(reason)
    end
    return self
end
return M
