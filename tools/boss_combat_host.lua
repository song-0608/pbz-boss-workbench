-- Bind native combat input to one runtime, rather than the mutable arena runtime.
-- The native helper adds foreground/key checks; this gate owns menu/session checks.
local Host={}
function Host.options(runtime,role,contract,g,pause_query,log)
    local session=assert(runtime.session,'combat session required')
    local bridge=assert(session.bridge,'combat bridge required')
    assert(type(role)=='string'and role~=''and contract
        and contract.native_input_binding_verified==true
        and math.type(contract.pid)=='integer'and contract.pid>0,
        'current native combat input contract required')
    assert(type(pause_query)=='function',
        'native combat pause query unavailable')
    return {developer_only=true,now=os.clock,globals=g,log=log,
        native_input={binding_verified=true,pid=contract.pid},
        cues=contract.cues,defense=(contract.defense_by_role or{})[role],
        input_allowed=function(receipt)
            if runtime.running~=true or runtime.session~=session or session.bridge~=bridge
                or session.state~='ACTIVE'or receipt==nil or session.receipt~=receipt
                or receipt.input_enabled~=true then return false end
            local workbench=runtime.host and runtime.host.workbench
            if workbench and workbench:is_open()then return false end
            -- A missing/unreadable pause result must not authorize gameplay input.
            return pause_query(bridge:check(receipt))==false
        end}
end
return Host
