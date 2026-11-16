-- Bind the cosmetic channel to one owned online assembly. Optional until the
-- current-process visual declarations and animation catalog are accepted.
local M={}
function M.attach(api,scope,peer,observer,dependencies,binding,config,arena,directory,g)
    g=g or _G
    assert(type(g.LoopInGameThreadWithDelay)=='function' and type(g.CancelDelayedAction)=='function')
    local Native=dofile(directory..'bwb_visual_native.lua')
    local Visual=dofile(directory..'bwb_visual.lua')
    assert(not api.coop.handlers[Visual.EVENT],'visual handler already installed')
    local native=Native.new(api,scope,peer,observer,dependencies,binding,config,g)
    local visual=Visual.new({role=config.role,session=config.session,protocol=peer.protocol,
        bosses=config.bosses,animations=native.animations,native=native,
        now=observer.now,send=api.coop.sendEvent,snapshot=native.sample,attest=function(restore)scope:attest(restore)end,
        log=observer.log,world=function()
            local snapshot=observer.snapshot();local loc=snapshot.body_actor:K2_GetActorLocation()
            return snapshot.world,api.coop.net.localMap,{x=loc.X,y=loc.Y,z=loc.Z}
        end})
    local service={visual=visual,closed=false}
    local handle
    local handler=function(line,from)
        if service.closed or peer.closed or not api.coop.net.enabled or not api.coop.linked()
            or api.coop.net.party or api.coop.net.pvp or api.coop.net.role=='local' then return false end
        if from~=nil and not (config.role=='host' and from==2) then return false end
        return visual:receive(line,config.role=='host' and 'guest' or 'host')
    end
    function service:close()
        self.closed=true
        if handle~=nil then g.CancelDelayedAction(handle);handle=nil end
        if api.coop.handlers[Visual.EVENT]==handler then api.coop.handlers[Visual.EVENT]=nil end
        return visual:close()
    end
    handle=g.LoopInGameThreadWithDelay(50,function()
        if not service.closed then visual:tick()end
    end)
    assert(handle~=nil,'visual scheduler must be cancellable')
    api.coop.handlers[Visual.EVENT]=handler
    local original_stop,original_revoke=arena.stop,arena.revoke
    function arena:stop(reason)
        local visual_ok=visual:invalidate(reason)
        local control_ok,why=original_stop(self,reason)
        return visual_ok and control_ok,visual_ok and why or 'visual recovery remains pending'
    end
    function arena:revoke(reason)
        local visual_ok=service:close()
        local control_ok,why=original_revoke(self,reason)
        return visual_ok and control_ok,visual_ok and why or 'visual recovery remains pending'
    end
    peer.visual=service
    return service
end
return M
