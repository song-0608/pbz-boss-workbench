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
    end,destroy=function(record)s.destroys=s.destroys+1;return not s.cleanup_error end}
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
print('PASS '..checks..' visual groups; cosmetic lifecycle with fake native bindings, no game started')
