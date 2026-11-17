local root=assert(arg[1]);local Visual=dofile(root..'/tools/phantom_boss_visual.lua')
local checks=0;local function check(name,fn)fn();checks=checks+1;print('PASS '..name)end
local asset='/PBZCombatAsset/ActorData/Mobs/Test/Walk.Walk'
local function fixture(role)
    local s={now=1,map=7,world='WorldA',sent={},mounts=0,updates=0,destroys=0,logs={}}
    local protocol={ready=true,connected=true,generation=3,boss='ahua',remote={generation=4,boss='youlong'}}
    if role=='guest' then protocol.generation,protocol.remote.generation=4,3;protocol.boss,protocol.remote.boss='youlong','ahua'end
    local frame={world=s.world,map=s.map,x=10,y=20,z=30,yaw=90,animation=asset,time=.5}
    local native={mount=function(boss,world,remember)
        s.mounts=s.mounts+1;local record={boss=boss,world=world};remember(record)
        if s.mount_error then error('partial native construction')end
        return record
    end,update=function(record,f,world)
        assert(record.world==world and record.boss==f.boss);s.updates=s.updates+1;s.frame=f
        if s.update_error then error('identity replaced')end;return true
    end,destroy=function(record)
        s.destroys=s.destroys+1;if s.destroy_throws then error('native destruction failed')end
        return not s.cleanup_error
    end}
    local options={role=role or 'host',session='bwb_visual_test',protocol=protocol,
        bosses={ahua={},youlong={}},animations={ahua={[asset]=2},youlong={[asset]=2}},native=native,
        now=function()return s.now end,send=function(kind,line)s.sent[#s.sent+1]={kind,line}end,
        snapshot=function()return frame end,world=function()return s.world,s.map,{x=0,y=0,z=0}end,
        attest=function()if s.expired then error('expired')end end,log=function(t)s.logs[#s.logs+1]=t end}
    local v=Visual.new(options);s.v,s.p,s.local_frame,s.options=v,protocol,frame,options
    v:tick() -- establish this local World; no remote Actor is created
    function s:packet(sequence,change)
        local t={'1','bwb_visual_test',self.p.remote.generation,sequence or 1,
            options.role=='host' and 'guest' or 'host',self.p.remote.boss,self.p.generation,
            self.map,100,200,300,45,asset,.5}
        for k,value in pairs(change or {})do t[k]=value end
        return table.concat(t,' ')
    end
    function s:receive(sequence,change,sender)
        return v:receive(self:packet(sequence,change),sender or (options.role=='host' and 'guest' or 'host'))
    end
    return s
end
check('sender emits complete generation-bound poses at most twenty times per second',function()
    local s=fixture();assert(#s.sent==1 and s.sent[1][1]=='BWV1' and #s.sent[1][2]<850)
    for _=1,100 do s.v:tick()end;assert(#s.sent==1)
    s.now=1.051;s.v:tick();assert(#s.sent==2 and s.mounts==0)
end)
check('validated network handlers buffer without loading assets or spawning Actors',function()
    local s=fixture();assert(s:receive());assert(s.mounts==0 and s.updates==0)
    s.v:tick();assert(s.mounts==1 and s.updates==1 and s.frame.animation==asset)
end)
check('both authenticated roles accept only their opposite sender',function()
    for _,role in ipairs({'host','guest'})do
        local s=fixture(role);assert(not s:receive(1,nil,role));assert(s:receive())
    end
end)
check('session Boss generation and acknowledgement must match the control handshake',function()
    for _,row in ipairs({{2,'other'},{3,3},{5,'host'},{6,'ahua'},{7,9},{3,0},{4,-1},{4,'nan'}})do
        local s=fixture();assert(not s:receive(1,{[row[1]]=row[2]}));s.v:tick();assert(s.mounts==0)
    end
end)
check('duplicates and out of order packets cannot rewind the current pose',function()
    local s=fixture();assert(s:receive(5));assert(not s:receive(4));assert(not s:receive(5))
    assert(s:receive(6));s.v:tick();assert(s.mounts==1)
end)
check('malformed oversized nonfinite and out of bounds frames are rejected',function()
    local s=fixture()
    for _,line in ipairs({'',string.rep('x',851),s:packet()..' extra',s:packet()..'\n'})do
        assert(not s.v:receive(line,'guest'))
    end
    for _,row in ipairs({{8,0},{9,'nan'},{10,'inf'},{11,20000001},{12,361},{14,-.1},{14,2.01}})do
        assert(not s:receive(1,{[row[1]]=row[2]}))
    end
    assert(s.mounts==0)
end)
check('only captured sequences are accepted and reference poses carry no playback time',function()
    local s=fixture();assert(not s:receive(1,{[13]='/Game/Other.Other'}))
    assert(not s:receive(1,{[13]='-',[14]=1}));assert(s:receive(1,{[13]='-',[14]=0}))
    s.v:tick();assert(s.frame.animation=='-' and s.frame.time==0)
    s.options.animations.youlong['/Game/Injected.Injected']=2
    assert(not s:receive(2,{[13]='/Game/Injected.Injected'}))
end)
check('missing identity or disabled link destroys the cosmetic body',function()
    for _,key in ipairs({'ready','connected'})do
        local s=fixture();assert(s:receive());s.v:tick();s.p[key]=false;s.v:tick()
        assert(s.destroys==1 and not s.v.record and not s:receive(2))
    end
end)
check('stale or different-map poses retire instead of freezing indefinitely',function()
    local s=fixture();assert(s:receive());s.v:tick();s.now=1.31;s.v:tick()
    assert(s.destroys==1 and not s.v.record)
    s=fixture();assert(s:receive());s.v:tick();assert(s:receive(2,{[8]=8}));s.v:tick()
    assert(s.destroys==1 and not s.v.record)
end)
check('World changes discard cached poses before any new native operation',function()
    local s=fixture();assert(s:receive());s.v:tick();s.world='WorldB';s.v:tick()
    assert(s.destroys==1 and s.mounts==1 and not s.v.record)
    s.local_frame.world=s.world;assert(s:receive(2));s.v:tick();assert(s.mounts==2)
end)
check('remote generation changes retire old ownership before mounting another body',function()
    local s=fixture();assert(s:receive());s.v:tick();s.p.remote.generation=5
    assert(not s.v:receive(s:packet(2,{[3]=4}),'guest'))
    assert(s:receive());s.v:tick();assert(s.mounts==2 and s.destroys==1)
end)
check('partial construction failures retain and clean their recorded Actor',function()
    local s=fixture();s.mount_error=true;assert(s:receive());s.v:tick()
    assert(s.mounts==1 and s.destroys==1 and not s.v.record and #s.logs==1)
end)
check('failed cleanup blocks replacement and retains its recovery ownership',function()
    local s=fixture();assert(s:receive());s.v:tick();s.cleanup_error=true;s.p.remote.generation=5
    assert(s:receive());s.v:tick();assert(s.mounts==1 and s.v.record and s.v.restore_pending)
    s.cleanup_error=false;assert(s.v:close() and not s.v.record)
end)
check('lease expiry and native identity failures retire without ability or damage execution',function()
    for _,key in ipairs({'expired','update_error'})do
        local s=fixture();assert(s:receive());s.v:tick();s[key]=true;s.v:tick()
        assert(s.destroys==1 and not s.v.record and #s.logs==1)
    end
end)
check('remote bodies outside the bounded render range do not spawn',function()
    local s=fixture();assert(s:receive(1,{[9]=60000}));s.v:tick();assert(s.mounts==0)
end)
check('closing prevents all later receive and tick operations',function()
    local s=fixture();assert(s:receive());s.v:tick();assert(s.v:close());s.v:tick()
    assert(not s:receive(2) and s.mounts==1 and s.destroys==1)
end)
check('fresh same-generation packets cannot strand a failed visual recovery',function()
    local s=fixture();assert(s:receive());s.v:tick();s.update_error=true;s.cleanup_error=true
    assert(s:receive(2));s.v:tick();local record=s.v.record
    assert(record and s.v.restore_pending and s.destroys==1)
    s.update_error=false;s.cleanup_error=false;s.now=1.251;assert(s:receive(3));s.v:tick()
    assert(s.destroys==2 and not s.v.record and not s.v.restore_pending and s.mounts==1)
    assert(s:receive(4));s.v:tick();assert(s.mounts==2 and s.v.record~=record)
end)
check('automatic recovery retries are bounded while explicit close remains immediate',function()
    local s=fixture();assert(s:receive());s.v:tick();s.update_error=true;s.cleanup_error=true;s.v:tick()
    local record=s.v.record;assert(record and s.destroys==1)
    for sequence=2,21 do
        s.now=1+(sequence-1)*.01;assert(s:receive(sequence));s.v:tick()
        assert(not s.v:invalidate('assembly not ready',true))
    end
    assert(s.destroys==1 and s.mounts==1 and s.updates==2 and s.v.record==record)
    s.now=1.251;assert(s:receive(22));s.v:tick();assert(s.destroys==2)
    s.now=1.26;s.v:tick();assert(s.destroys==2)
    s.cleanup_error=false;assert(s.v:close()and s.destroys==3 and not s.v.record)
end)
check('native destruction exceptions retain ownership until the next bounded retry',function()
    local s=fixture();assert(s:receive());s.v:tick();s.update_error=true;s.destroy_throws=true;s.v:tick()
    local record=s.v.record;assert(record and s.v.restore_pending and s.destroys==1)
    s.v:tick();assert(s.destroys==1 and s.v.record==record)
    s.destroy_throws=false;s.now=1.251;s.v:tick();assert(s.destroys==2 and not s.v.record)
end)
check('invalid recovery clocks suppress automatic native work without blocking explicit cleanup',function()
    local s=fixture();assert(s:receive());s.v:tick();s.update_error=true;s.cleanup_error=true;s.v:tick()
    s.now=0/0;assert(pcall(s.v.tick,s.v));assert(s.destroys==1 and s.v.restore_pending)
    s.options.now=function()error('clock unavailable')end
    assert(pcall(s.v.tick,s.v));assert(s.destroys==1)
    s.cleanup_error=false;assert(s.v:close()and s.destroys==2 and not s.v.record)
end)
check('partial visual construction must finish recovery before a fresh packet can remount',function()
    local s=fixture();s.mount_error=true;s.cleanup_error=true;assert(s:receive());s.v:tick()
    assert(s.mounts==1 and s.destroys==1 and s.v.restore_pending)
    s.mount_error=false;s.cleanup_error=false;s.now=1.251;assert(s:receive(2));s.v:tick()
    assert(s.mounts==1 and s.destroys==2 and not s.v.record)
    assert(s:receive(3));s.v:tick();assert(s.mounts==2 and s.updates==1)
end)
check('persistent pose errors back off reconstruction while local pose sends continue',function()
    local s=fixture();assert(s:receive());s.v:tick();s.update_error=true;s.v:tick()
    assert(s.mounts==1 and s.destroys==1)
    for sequence=2,5 do
        s.now=1+(sequence-1)*.05;assert(s:receive(sequence));s.v:tick()
    end
    assert(s.mounts==1 and s.destroys==1 and #s.sent>=3)
    s.now=1.251;assert(s:receive(6));s.v:tick();assert(s.mounts==2 and s.destroys==2)
    s.now=1.51;assert(s:receive(7));s.v:tick();assert(s.mounts==2)
    s.now=1.752;assert(s:receive(8));s.v:tick();assert(s.mounts==3 and s.destroys==3)
    s.now=2.26;assert(s:receive(9));s.v:tick();assert(s.mounts==3)
    s.now=2.753;assert(s:receive(10));s.v:tick();assert(s.mounts==4 and s.destroys==4)
    s.now=3.8;assert(s:receive(11));s.v:tick();assert(s.mounts==4)
    s.now=4.754;assert(s:receive(12));s.v:tick();assert(s.mounts==5 and s.destroys==5)
    s.now=5.8;assert(s:receive(13));s.v:tick();assert(s.mounts==5)
    s.now=6.755;assert(s:receive(14));s.v:tick();assert(s.mounts==6 and s.destroys==6)
end)
check('successful visual recovery resets retry delay for a later independent failure',function()
    local s=fixture();assert(s:receive());s.v:tick();s.update_error=true;s.v:tick()
    s.now=1.251;s.update_error=false;assert(s:receive(2));s.v:tick();assert(s.mounts==2 and s.updates==3)
    s.now=1.3;s.update_error=true;assert(s:receive(3));s.v:tick();assert(s.destroys==2)
    s.now=1.551;s.update_error=false;assert(s:receive(4));s.v:tick();assert(s.mounts==3 and s.updates==5)
end)
check('construction failures before a recorded Actor also respect the visual retry delay',function()
    local s=fixture();local native=s.options.native
    native.mount=function()s.mounts=s.mounts+1;error('asset unavailable before spawning')end
    assert(s:receive());s.v:tick();assert(s.mounts==1 and not s.v.record)
    for sequence=2,30 do assert(s:receive(sequence));s.v:tick()end
    assert(s.mounts==1 and s.destroys==0)
    s.now=1.251;assert(s:receive(31));s.v:tick();assert(s.mounts==2)
    native.mount=function(_,world,remember)
        s.mounts=s.mounts+1;local row={boss='youlong',world=world};remember(row);return row
    end
    s.now=1.8;s.v:tick();assert(s.mounts==2) -- buffered pose is stale, even after cooldown
    assert(s:receive(32));s.v:tick();assert(s.mounts==3 and s.updates==1)
end)
print('PASS '..checks..' visual groups; cosmetic lifecycle with fake native bindings, no game started')
