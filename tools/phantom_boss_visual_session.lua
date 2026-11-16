-- Bind the cosmetic channel to one owned online assembly. Optional until the
-- current-process visual declarations and animation catalog are accepted.
local M={}
function M.attach(api,scope,peer,observer,dependencies,binding,config,arena,directory,g)
    g=g or _G
    assert(type(g.LoopInGameThreadWithDelay)=='function' and type(g.CancelDelayedAction)=='function')
    assert(type(arena.add_cleanup)=='function','assembly-owned visual cleanup registration required')
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
        if service.closed or peer.closed or arena.state~='READY' or not api.coop.net.enabled or not api.coop.linked()
            or api.coop.net.party or api.coop.net.pvp or api.coop.net.role=='local' then return false end
        if from~=nil and not (config.role=='host' and from==2) then return false end
        return visual:receive(line,config.role=='host' and 'guest' or 'host')
    end
    function service:close()
        self.closed=true
        if api.coop.handlers[Visual.EVENT]==handler then api.coop.handlers[Visual.EVENT]=nil end
        local cancelled,cancel_error=true,nil
        if handle~=nil then
            cancelled,cancel_error=pcall(g.CancelDelayedAction,handle)
            if cancelled then handle=nil end
        end
        local observed,clean=pcall(visual.close,visual)
        self.cleanup_error=not cancelled and ('visual scheduler recovery: '..tostring(cancel_error))
            or (not observed and tostring(clean))or(clean~=true and 'visual native recovery remains pending')or nil
        return cancelled and observed and clean==true,self.cleanup_error
    end
    assert(arena:add_cleanup('remote_visual',function(reason)
        if service.closed then return service:close()end
        return visual:invalidate(reason)
    end)==true,'visual cleanup responsibility not registered')
    handle=g.LoopInGameThreadWithDelay(50,function()
        if service.closed then return end
        if peer.closed or arena.state~='READY'then visual:invalidate('local assembly not ready',true);return end
        visual:tick()
    end)
    assert(handle~=nil,'visual scheduler must be cancellable')
    api.coop.handlers[Visual.EVENT]=handler
    local original_revoke=arena.revoke
    function arena:revoke(reason)
        service.closed=true
        return original_revoke(self,reason)
    end
    peer.visual=service
    return service
end
return M
