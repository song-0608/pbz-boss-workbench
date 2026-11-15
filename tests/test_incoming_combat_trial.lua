local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Trial=require('incoming_combat_trial')
local function fixture()
    local f={time=0,health=9000,queue={},logs={},casts=0,cancels=0,clears=0}
    local session={state='ACTIVE',receipt={}}
    local a,b={ActiveCount=0},{ActiveCount=0}
    local api={session=session,sources={a,b},attest=function()return{expires_at=600}end,now=function()return f.time end,
        health=function()return f.health end,spec=function(actor)return actor end,
        name=function(actor)return actor==a and'a'or'b'end,
        validate=function()end,target=function()end,
        log=function(k,v)f.logs[#f.logs+1]=k..'='..tostring(v)end,
        activate=function(spec)f.casts=f.casts+1;spec.ActiveCount=1;return true end,
        cancel=function(spec)f.cancels=f.cancels+1;if f.reject_cancel then return false end;spec.ActiveCount=0;return true end,
        clear=function()f.clears=f.clears+1 end,
        schedule=function(fn)f.queue[#f.queue+1]=fn end}
    f.trial=Trial.new(api);f.api=api;f.session=session;f.a=a;f.b=b
    function f:step(seconds)self.time=self.time+(seconds or .25);local fn=table.remove(self.queue,1);if fn then fn()end end
    return f
end
local total=0
local function test(name,fn)fn();total=total+1;print('PASS '..name)end
test('native active sources are observed instead of repeatedly recast',function()
    local f=fixture();f.trial:start();assert(f.casts==2);f:step();assert(f.casts==2 and f.cancels==0)
end)
test('stop cancels each exact active source and queued polls become inert',function()
    local f=fixture();f.trial:start();assert(f.trial:stop());assert(f.cancels==2 and f.clears==2)
    f:step();assert(f.casts==2);assert(f.trial:stop());assert(f.cancels==2)
end)
test('real health depletion observation stops incoming abilities',function()
    local f=fixture();f.trial:start();f.health=0;f:step();assert(f.cancels==2 and not f.trial.running)
    assert(table.concat(f.logs):find('INCOMING_COMBAT_DEPLETED=true',1,true))
end)
test('bounded timeout cancels sources without rewriting target health',function()
    local f=fixture();f.trial:start();f.a.ActiveCount=0;f.b.ActiveCount=0;f:step(361)
    assert(not f.trial.running and f.health==9000 and f.casts==2)
end)
test('changed control receipt stops combat and reports the rejected boundary',function()
    local f=fixture();f.trial:start();f.session.receipt={};f:step()
    assert(not f.trial.running and f.cancels==2 and table.concat(f.logs):find('ISSUE_INCOMING_COMBAT=',1,true))
end)
test('failed native cancellation cannot report successful cleanup',function()
    local f=fixture();f.trial:start();f.reject_cancel=true
    assert(not pcall(f.trial.stop,f.trial));assert(f.a.ActiveCount==1)
    assert(not table.concat(f.logs):find('INCOMING_COMBAT_STOP=',1,true))
end)
test('expired margin rejects before any source activation',function()
    local f=fixture();f.time=400;assert(not pcall(f.trial.start,f.trial));assert(f.casts==0)
end)
test('post restore observation is read only bounded and stops on new receipt',function()
    local f=fixture();local samples=0;f.api.observe=function()samples=samples+1 end
    f.trial:start();f.trial:stop();f.session.receipt=nil;f.session.state='OFF'
    f.trial:watch_restored();local initial=samples
    f:step(61);f:step();assert(samples>initial and not f.trial.watching)
    assert(f.health==9000 and f.casts==2 and f.cancels==2)
    local g=fixture();g.api.observe=function()end;g.trial:start();g.trial:stop()
    g.session.receipt=nil;g.trial:watch_restored();g.session.receipt={};g:step();g:step()
    assert(not g.trial.watching)
end)
print('Incoming combat fixtures passed: '..total)
