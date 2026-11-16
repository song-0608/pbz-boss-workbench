-- Mount one online owned-Boss assembly onto an already captured gameplay host.
-- The dedicated launcher issues the lease and current native declarations.
local M={}
function M.new(api,launch,config,peer,observer,directory,globals)
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
    function peer:select_boss(id)
        scope:attest(false)
        assert(config.bosses[id],'Boss selection absent from online catalog')
        assert(self:refresh_local_body(),'valid gameplay snapshot required before online assembly')
        if arena.state~='IDLE' and arena.state~='REJECTED' then
            local clean,why=arena:stop('online Boss selection')
            if not clean then return false,why end
        end
        return arena:start(id)
    end
    function peer:assembly_status()
        return {state=arena.state,reason=arena.failure,boss_id=arena.context and arena.context.profile.id,
            source_only=true,runtime_acceptance_current=false}
    end
    return arena
end
return M
