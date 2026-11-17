local root=assert(arg[1]);local Lock=dofile(root..'/tools/player_target_lock.lua')
local count=0
local function test(name,fn)local ok,why=pcall(fn);assert(ok,name..': '..tostring(why));count=count+1;print('PASS '..name)end
local function fixture()
    local f={target={id=1},allowed=true,validations=0,writes=0,rotation={Yaw=179,Pitch=0},
        source={X=0,Y=0,Z=0},destination={X=-1000,Y=-17.45,Z=0}}
    f.lock=Lock.new({target=function()return f.target end,eligible=function()f.validations=f.validations+1;return f.allowed end,
        same=function(a,b)return a==b end,position=function()return f.source,f.destination end,
        rotation=function()return f.rotation end,set_rotation=function(r)f.rotation=r;f.writes=f.writes+1 end})
    return f
end
test('disabled lock never reads game target or writes camera',function()
    local f=fixture();f.lock.native.target=function()error('must not sample')end
    assert(f.lock:update()and f.writes==0)
end)
test('lock acquires verified combat target and takes shortest yaw across wrap',function()
    local f=fixture();assert(f.lock:toggle());assert(f.lock:update())
    assert(f.rotation.Yaw>179 and f.rotation.Yaw<180 and f.writes==1)
end)
test('F7 target change revalidates immediately without global discovery',function()
    local f=fixture();f.lock:toggle();f.lock:update();local previous=f.validations
    f.target={id=2};f.destination={X=0,Y=1000,Z=0};assert(f.lock:update())
    assert(f.validations==previous+1 and f.lock.target==f.target)
end)
test('dead target or obstruction releases within six updates',function()
    local f=fixture();f.lock:toggle();f.allowed=false
    for _=1,5 do assert(f.lock:update())end
    assert(not f.lock:update()and not f.lock.enabled and f.writes==5)
end)
test('missing or cross-world target releases before any camera write',function()
    local f=fixture();f.lock:toggle();f.target=nil
    assert(not f.lock:update()and f.writes==0 and not f.lock.enabled)
    f=fixture();f.lock:toggle();f.target={id=2};f.allowed=false
    assert(not f.lock:update()and f.writes==0)
end)
test('invalid geometry and out of range never rotate camera',function()
    for _,p in ipairs({{X=0/0,Y=0,Z=0},{X=4000,Y=0,Z=0},{X=0,Y=0,Z=0}})do
        local f=fixture();f.lock:toggle();f.destination=p
        assert(not f.lock:update()and f.writes==0)
    end
end)
test('manual unlock and missing target cannot fabricate a lock',function()
    local f=fixture();f.lock:toggle();assert(f.lock:toggle()and not f.lock.enabled)
    f.target=nil;assert(not f.lock:toggle()and not f.lock.enabled)
end)
test('camera changes are bounded and validation sampling is limited',function()
    local f=fixture();f.destination={X=1000,Y=0,Z=10000}
    f.lock:toggle();assert(not f.lock:update()and f.writes==0)
    f=fixture();f.destination={X=0,Y=1000,Z=200};f.lock:toggle()
    for _=1,60 do local before=f.rotation.Yaw;assert(f.lock:update());assert(math.abs(f.rotation.Yaw-before)<=8)end
    assert(f.validations==11 and f.writes==60)
end)
print('Camera target lock fixtures passed: '..count)
