-- Prepare the original player for the game's own travel menu. Opening a map
-- package directly bypasses PBZ's spawn/travel state and is not a valid trial.
local Trial={}
function Trial.prepare(runtime,api)
    assert(runtime and runtime.running and type(api.attest)=='function'and type(api.log)=='function',
        'current protected travel trial required')
    local grant=api.attest()
    assert(grant and type(grant.expires_at)=='number'and grant.expires_at-api.now()>180,
        'native travel cleanup margin required')
    local session=runtime.session
    assert(session.state=='ACTIVE'and session.receipt and not session.current_skill and not session.pending_target,
        'idle active takeover required before native travel preparation')
    local restored,why=session:restore('native map menu trial')
    runtime:report('auto_exit',restored,restored and'native map menu trial'or why)
    assert(restored and session.state=='OFF'and not session.receipt,'native travel restoration not verified')
    api.log('NATIVE_TRAVEL_MENU_READY',true)
    return true
end
return Trial
