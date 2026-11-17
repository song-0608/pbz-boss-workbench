local root,candidate=assert(arg[1]),assert(arg[2])
package.path=candidate..'/PBZBossControl/Scripts/?.lua;'..package.path
local Trial=require('player_native_travel_trial')
local events={}
local session={state='ACTIVE',receipt={}}
local runtime={running=true,session=session}
function runtime:report(label,success)events[#events+1]=label..':'..tostring(success)end
local restored=true
function session:restore(reason)
    assert(reason=='native map menu trial')
    events[#events+1]='restore'
    if restored then self.state='OFF';self.receipt=nil end
    return restored,'fixture refusal'
end
local expires=1000
local api={now=function()return 100 end,attest=function()return{expires_at=expires}end,
    log=function(key)events[#events+1]=key end,
    OpenLevel=function()error('raw package opening is never a native menu trial')end}
assert(Trial.prepare(runtime,api))
assert(table.concat(events,',')=='restore,auto_exit:true,NATIVE_TRAVEL_MENU_READY')
events={};session.state='ACTIVE';session.receipt={};restored=false
assert(not pcall(Trial.prepare,runtime,api))
assert(table.concat(events,',')=='restore,auto_exit:false','failed restoration cannot unlock native menus')
events={};restored=true;session.current_skill='active skill'
assert(not pcall(Trial.prepare,runtime,api)and #events==0,'active skills must finish before preparation')
session.current_skill=nil;session.pending_target=true
assert(not pcall(Trial.prepare,runtime,api)and #events==0)
session.pending_target=nil;expires=250
assert(not pcall(Trial.prepare,runtime,api)and #events==0,'trial must preserve cleanup margin')
expires=1000;runtime.running=false
assert(not pcall(Trial.prepare,runtime,api)and #events==0)
print('PASS real restoration before native-menu readiness; skill, target, time and runtime gates; no raw map opening')
