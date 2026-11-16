-- One local owned Boss, assembled asynchronously. No offline entry or save access.
local M={}
function M.new(scope,peer,observer,native)
    for _,key in ipairs({'prepare','protect','spawn','resolve','register_controller','readiness','suspend',
        'release_initialization','restore_player','create_control','destroy','schedule','now','log'})do
        assert(type(native[key])=='function','online assembly binding missing '..key)
    end
    assert(type(observer.bind_control_probe)=='function','controlled body observer required')
    local self={state='IDLE',generation=0,owned={},polls=0}
    local cancel,detach
    local function cancel_poll()
        if cancel then local old=cancel;cancel=nil;old() end
    end
    function self:stop(reason)
        self.generation=self.generation+1;cancel_poll()
        local ok,why=pcall(function()
            if self.control then
                assert(self.control.runtime:stop(reason)==true,'local control restoration not acknowledged')
                assert(not self.control.session.receipt,'unrestored online control receipt')
            end
            -- Failed control restoration leaves its observer and all owned actors
            -- intact. Never destroy a body still referenced by a recovery receipt.
            if detach then assert(detach()==true);detach=nil end
            local errors={}
            for index=#self.owned,1,-1 do
                local destroyed,problem=pcall(native.destroy,self.owned[index],self.context)
                if not destroyed or problem~=true then errors[#errors+1]='owned destruction: '..tostring(problem) end
            end
            if self.context then
                local restored,problem=pcall(native.restore_player,self.context)
                if not restored or problem~=true then errors[#errors+1]='player restoration: '..tostring(problem) end
            end
            assert(#errors==0,table.concat(errors,'; '))
            self.owned={};self.control=nil;self.state='IDLE'
        end)
        if not ok then self.state='FAULTED';self.failure=tostring(why);native.log('assembly cleanup unverified: '..self.failure) end
        return ok,why
    end
    function self:revoke(reason)
        scope:revoke(reason)
        return self:stop(reason)
    end
    local function failed(why)
        self.failure=tostring(why);native.log('assembly rejected: '..self.failure)
        local clean=self:stop('assembly rejected')
        if clean then self.state='REJECTED' end
    end
    function self:start(boss_id)
        assert(self.state=='IDLE' or self.state=='REJECTED','previous assembly must be cleaned first')
        scope:attest(false)
        assert(not peer.closed and not peer.restore_pending,'online adapter not recoverable')
        self.state='PREPARING';self.failure=nil;self.polls=0
        self.generation=self.generation+1;local generation=self.generation
        local ok,why=pcall(function()
            self.context=native.prepare(boss_id)
            assert(self.context.world==peer.world,'assembly/observer World mismatch')
            native.protect(self.context)
            local owned=native.spawn(self.context,function(record)
                -- Deferred Actor and each newly discovered AI are recorded before
                -- construction/initialization continues, including partial failures.
                self.owned[#self.owned+1]=record
            end)
            self.body=owned;self.state='INITIALIZING';self.started_at=native.now()
            local previous,stable=nil,0
            local function poll()
                if generation~=self.generation then return end
                local accepted,problem=pcall(function()
                    scope:attest(false)
                    assert(self.context.world==peer.world,'World changed during online assembly')
                    assert(native.now()-self.started_at<80 and self.polls<64,'bounded Boss initialization timed out')
                    self.polls=self.polls+1
                    local body=native.resolve(owned,self.context)
                    native.register_controller(body,self.context,function(record)self.owned[#self.owned+1]=record end)
                    local signature=native.readiness(body,self.context,self.polls)
                    if signature and signature==previous then stable=stable+1 else stable=0 end
                    previous=signature
                    if signature and stable>=12 then
                        native.suspend(body,self.context)
                        native.release_initialization(self.context)
                        native.restore_player(self.context)
                        self.control=native.create_control(body,self.context)
                        detach=observer.bind_control_probe(function()return self.control:observed_body()end)
                        assert(self.control:start()==true,'online input runtime did not start')
                        self.state='READY';cancel_poll();native.log('owned Boss ready: '..boss_id)
                    end
                end)
                if not accepted then failed(problem) end
            end
            cancel=native.schedule(250,poll)
            assert(type(cancel)=='function','cancellable assembly scheduler required')
        end)
        if not ok then failed(why);return false,why end
        return true
    end
    return self
end
return M
