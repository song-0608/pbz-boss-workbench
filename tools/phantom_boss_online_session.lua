-- Mount one online owned-Boss assembly onto an already captured gameplay host.
-- The dedicated launcher issues the lease and current native declarations.
local M={}
function M.new(api,launch,config,peer,observer,directory,globals)
    globals=globals or _G
    assert(type(launch.assembly)=='table' and type(launch.lease_provider)=='function',
        'online assembly options and live lease provider required')
    local scope=dofile(directory..'bwb_online_scope.lua').new(launch.lease_provider,{
        role=launch.role,session_id=launch.session,exe_sha256=config.exe_sha256,
        catalog_sha256=config.catalog_sha256,upstream_commit=config.upstream_commit},os.time)
    local grant=scope:attest(false)
    assert(grant.issued_at==launch.issued_at and grant.expires_at==launch.expires_at,
        'host and online control must share one unmodified research lease')
    local dependencies=dofile(directory..'bwb_local_dependencies.lua')(directory)
    local native=dofile(directory..'bwb_spawn_native.lua').new(api,scope,peer,observer,dependencies,
        dofile(directory..'bwb_online_control.lua'),assert(launch.assembly.bindings),globals)
    local arena=dofile(directory..'bwb_online_arena.lua').new(scope,peer,observer,native)
    local renderer
    if launch.assembly.bindings.workbench_ui~=nil then
        renderer=dofile(directory..'bwb_workbench_native.lua').new(api,scope,observer,dependencies,
            launch.assembly.bindings.workbench_ui,globals)
    end
    local workbench=dofile(directory..'bwb_online_workbench.lua').new(scope,peer,dependencies,config,
        function(text)globals.print(text)end,os.time,renderer)
    native.mount_workbench=function(control,host,layer,pc,id)return workbench:mount(control,host,layer,pc,id)end
    native.state_changed=function(state,reason)
        workbench:assembly_changed(state,reason)
        if state=='FAULTED'then
            local ok,why=pcall(workbench.stop_recovery,workbench)
            if not ok then native.log('faulted assembly menu recovery pending: '..tostring(why))end
            return
        end
        if state=='REJECTED'and not workbench.recovery then
            local ok,why=pcall(function()
                local id=assert(arena.requested_boss_id)
                local host,layer,pc,guard=native.recovery_menu(id)
                workbench:recover(host,layer,pc,id,guard,native.schedule)
            end)
            if not ok then native.log('recovery menu unavailable: '..tostring(why))end
        end
    end
    local revoking=false
    arena:add_cleanup('workbench',function()
        if revoking then return workbench:close()end
        if arena.state=='FAULTED'then return workbench:stop_recovery()end
        return true
    end)
    local revoke=arena.revoke
    function arena:revoke(reason)
        revoking=true
        return revoke(self,reason)
    end
    if launch.assembly.bindings.visual~=nil then
        dofile(directory..'bwb_visual_session.lua').attach(api,scope,peer,observer,dependencies,
            launch.assembly.bindings.visual,config,arena,directory,globals)
    end
    function peer:select_boss(id)
        scope:attest(false)
        assert(config.bosses[id],'Boss selection absent from online catalog')
        assert(self:refresh_local_body(),'valid gameplay snapshot required before online assembly')
        return arena:select(id)
    end
    function peer:assembly_status()
        local control=arena.control
        local pending=peer.restore_pending==true or arena.state=='FAULTED'
            or (control and (control.session.online_restore_pending==true or control.runtime.online_stop_pending==true)) or false
        local retired=peer.closed or peer.revoked_reason or peer.world_transition or scope.revoked
            or (control and control.runtime.online_stopped)
        local boundary=peer.world_transition
        return {state=arena.state,reason=arena.state=='FAULTED'and arena.failure
                or (control and (control.runtime.online_stop_reason or control.session.online_restore_reason))
                or peer.revoked_reason or arena.failure,
            activation_state=pending and 'RECOVERY_PENDING'or retired and 'RETIRED'or 'ACTIVE',
            restore_pending=pending,world_transition=boundary and {previous=boundary.previous,observed=boundary.observed}or nil,
            selection_failure=arena.selection_failure,
            boss_id=arena.context and arena.context.profile.id,
            visual=peer.visual and (peer.visual.visual.restore_pending and 'recovery pending' or 'contract supplied') or 'native contract pending',
            source_only=true,runtime_acceptance_current=false}
    end
    return arena
end
return M
