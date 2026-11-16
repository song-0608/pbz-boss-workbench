local root=assert(arg[1]);local module=dofile(root..'/tools/phantom_boss_online_scope.lua')
local checks=0
local function check(name,fn)fn();checks=checks+1;print('PASS '..name)end
local function env()
    local e={now=100}
    e.expected={role='host',session_id='research',exe_sha256=string.rep('a',64),
        catalog_sha256=string.rep('b',64),upstream_commit=string.rep('c',40)}
    e.grant={mode='two-player-online-research',isolated=true,issued_at=100,expires_at=200}
    for k,v in pairs(e.expected)do e.grant[k]=v end
    function e:create()return module.new(function()return self.grant end,self.expected,function()return self.now end)end
    e.scope=e:create();return e
end
check('online lease has explicit mode and never creates an offline flag',function()
    local e=env();local grant=e.scope:attest(false)
    assert(grant.mode=='two-player-online-research' and grant.offline==nil and grant.expires_at==200)
end)
check('caller mutation cannot change the captured lease',function()
    local e=env();local grant=e.scope:attest();grant.expires_at=9999;grant.role='guest'
    assert(e.scope:attest().expires_at==200 and e.scope:attest().role=='host')
end)
check('expiry refuses new control while same receipt cleanup gets a bounded separate purpose',function()
    local e=env();e.now=200;assert(not pcall(e.scope.attest,e.scope,false))
    local grant=e.scope:attest(true);assert(grant.restore_only and grant.expires_at==200)
    e.now=215;assert(not pcall(e.scope.attest,e.scope,true))
end)
check('disconnect revocation cannot be undone by a still-current provider',function()
    local e=env();e.scope:revoke('disconnect');assert(not pcall(e.scope.attest,e.scope))
    assert(e.scope:attest(true).restore_only);e.scope:revoke('again')
    assert(not pcall(e.scope.attest,e.scope,false))
end)
check('close denies cleanup and input alike',function()
    local e=env();e.scope:close();e.scope:close()
    assert(not pcall(e.scope.attest,e.scope,true) and not pcall(e.scope.attest,e.scope,false))
end)
check('offline and non-isolated providers are rejected',function()
    for _,change in ipairs({{'offline',true},{'mode','offline'},{'isolated',false}})do
        local e=env();e.grant[change[1]]=change[2];assert(not pcall(e.create,e))
    end
end)
check('changed build catalog role session and upstream cannot renew a scope',function()
    for _,key in ipairs({'exe_sha256','catalog_sha256','role','session_id','upstream_commit'})do
        local e=env();e.grant[key]='changed';assert(not pcall(e.scope.attest,e.scope,true))
    end
end)
check('extending expiry or changing issue time also refuses cleanup',function()
    for _,key in ipairs({'issued_at','expires_at'})do
        local e=env();e.grant[key]=e.grant[key]+1;assert(not pcall(e.scope.attest,e.scope,true))
    end
end)
check('future expired overlong and nonfinite leases refuse construction',function()
    for _,times in ipairs({{101,200},{90,100},{0,1201},{100,math.huge}})do
        local e=env();e.grant.issued_at,e.grant.expires_at=times[1],times[2];assert(not pcall(e.create,e))
    end
end)
check('backwards and nonfinite clocks cannot extend control',function()
    for _,now in ipairs({99,math.huge,0/0})do
        local e=env();e.now=now;assert(not pcall(e.scope.attest,e.scope,true))
    end
end)
check('expected identities are captured and later table edits cannot redirect the lease',function()
    local e=env();e.expected.role='guest';assert(e.scope:attest().role=='host')
end)
check('restoration purpose cannot be injected as a truthy nonboolean',function()
    local e=env();for _,value in ipairs({'restore',1,{}})do assert(not pcall(e.scope.attest,e.scope,value))end
end)
print('PASS '..checks..' online scope groups; isolated Lua lease logic, no engine/network')
