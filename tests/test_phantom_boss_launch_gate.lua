local root=assert(arg[1]);local Gate=dofile(root..'/tools/phantom_boss_launch_gate.lua')
local checks=0
local function check(name,f)f();checks=checks+1;print('PASS '..name)end
local function setup()
    local s={now=os.time(),files={},activations=0,closes=0,cancels=0}
    local g={LoopInGameThreadWithDelay=function(ms,fn)assert(ms==250);s.tick=fn;return 10 end,
        CancelDelayedAction=function(h)assert(h==10);s.cancels=s.cancels+1 end}
    local io_fake={open=function(path)
        local value=s.files[path];if not value then return nil end
        return {read=function(_,n)return value:sub(1,n)end,close=function()end}
    end}
    local peer={close=function()s.closes=s.closes+1;return not s.bad_close end}
    s.gate=Gate.wait('test/',function(launch)
        s.activations=s.activations+1;s.launch=launch
        if s.bad_activation then error('activation rejected')end
        return peer
    end,g,io_fake,function()
        s.identity_calls=(s.identity_calls or 0)+1
        return s.identity or '42:100000000000000001'
    end)
    function s:request(changes)
        local f={mode='two-player-online-research',role='host',session=string.rep('a',32),
            activation=string.rep('b',32),issued_at=self.now-1,expires_at=self.now+600,
            binding='bwb_current_bindings.lua',boss_id='ahua_guitoudao'}
        for k,v in pairs(changes or {})do f[k]=v end
        local lines={};for k,v in pairs(f)do lines[#lines+1]=k..'='..v end
        self.files['test/bwb_gate.ini']=table.concat(lines,'\n')..'\n'
    end
    function s:bindings(changes)
        local data={activation=string.rep('b',32),session=string.rep('a',32),role='host',
            issued_at=self.now-1,expires_at=self.now+600,native_player_class='/Test/Player_C',
            assembly={},boss_id='ahua_guitoudao',exe_sha256='exe',catalog_sha256='catalog',upstream_commit='upstream',
            process_identity='42:100000000000000001'}
        for k,v in pairs(changes or {})do data[k]=v end
        local values={};for k,v in pairs(data)do
            values[#values+1]=k..'='..(type(v)=='table' and '{}' or type(v)=='number' and tostring(v) or string.format('%q',v))
        end
        self.files['test/bwb_current_bindings.lua']='return {'..table.concat(values,',')..'}'
    end
    return s,g,peer,io_fake
end
check('without a request gate remains inert',function()
    local s=setup();for _=1,20 do s.tick()end
    assert(s.gate.state=='DORMANT' and s.activations==0)
end)
check('missing current declarations waits in the same process',function()
    local s=setup();s:request();s.tick();assert(s.gate.state=='WAITING_DECLARATIONS')
    s:bindings();s.tick();s.tick();assert(s.gate.state=='ACTIVE' and s.activations==1)
    assert(s.launch.session=='bwb_'..string.rep('a',32) and s.launch.lease_provider().isolated)
end)
check('duplicate initialization returns the same owner',function()
    local s,g,_,io_fake=setup();assert(Gate.wait('test/',function()error('duplicate')end,g,io_fake)==s.gate)
end)
check('stop while dormant cancels without activation',function()
    local s=setup();s.files['test/bwb_stop.txt']='stop';s.tick()
    assert(s.gate.closed and s.activations==0 and s.cancels==1)
end)
check('active stop invokes restoration before closing the lease',function()
    local s,_,peer=setup();s:request();s:bindings();s.tick()
    peer.close=function()assert(s.launch.lease_provider().role=='host');s.closes=s.closes+1;return true end
    s.files['test/bwb_stop.txt']='stop';s.tick();s.tick()
    assert(s.gate.closed and not s.gate.restore_pending and s.closes==1 and s.cancels==1)
end)
check('wrong launch binding never activates',function()
    for _,changes in ipairs({{role='guest'},{session='wrong'},{activation='wrong'},{expires_at=0}})do
        local s=setup();s:request();s:bindings(changes);s.tick();assert(s.gate.closed and s.activations==0)
    end
end)
check('bad requests and oversize declarations fail closed',function()
    for _,changes in ipairs({{mode='offline'},{role='other'},{expires_at=os.time()-1},{expires_at=os.time()+1500},
        {binding='../outside.lua'},{activation='wrong'}})do
        local s=setup();s:request(changes);s:bindings();s.tick();assert(s.gate.closed and s.activations==0)
    end
    local s=setup();s:request();s.files['test/bwb_current_bindings.lua']=string.rep('x',1048577);s.tick()
    assert(s.gate.closed and s.activations==0)
end)
check('failed startup retains failed cleanup responsibility',function()
    local s,_,peer=setup();s:request();s:bindings();s.tick();s.bad_close=true;peer.startup_state='FAILED';s.tick()
    assert(s.gate.closed and s.gate.restore_pending and s.closes==1)
end)
check('dormant gate never loads a process identity or native assembly',function()
    local s=setup();s:request();for _=1,10 do s.tick()end
    assert(not s.identity_calls and s.activations==0)
end)
check('another PID or reused PID with new FILETIME cannot activate',function()
    for _,identity in ipairs({'43:100000000000000001','42:100000000000000002','42:100000000000000000','bad'})do
        local s=setup();s.identity=identity;s:request();s:bindings();s.tick()
        assert(s.gate.closed and s.activations==0 and s.identity_calls==1)
    end
end)
check('missing process identity fails before native assembly',function()
    local s=setup();s:request();s:bindings({process_identity=''});s.tick()
    assert(s.gate.closed and s.activations==0)
end)
print('PASS '..checks..' launch gate groups')
