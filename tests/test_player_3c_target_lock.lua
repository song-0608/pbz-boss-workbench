local root=assert(arg[1]);local Lock=require('player_target_lock')
local old=assert(loadfile(root..'/releases/ahua-boss-workbench-v5-3f29975fe3b8826f/PBZBossControl/Scripts/player_target_lock.lua'))()
local function fixture(Class,fps)
    local f={target={},dt=1/fps,rotation={Yaw=0,Pitch=-8},validations=0,writes=0,allowed=true,
        destination={X=1000*math.cos(math.rad(20)),Y=1000*math.sin(math.rad(20)),Z=0}}
    f.lock=Class.new({frame_seconds=function()return f.dt end,
        target=function()return f.target end,same=function(a,b)return a==b end,
        eligible=function()f.validations=f.validations+1;return f.allowed end,
        position=function()return{X=0,Y=0,Z=0},f.destination end,
        rotation=function()return f.rotation end,
        set_rotation=function(r)f.rotation=r;f.writes=f.writes+1 end})
    return f
end
local function run(Class,fps,seconds)
    local f=fixture(Class,fps);assert(f.lock:toggle())
    for _=1,math.floor(fps*seconds+0.5)do assert(f.lock:update())end
    return f
end
local old30,old120=run(old,30,0.1),run(old,120,0.1)
assert(math.abs(old30.rotation.Yaw-old120.rotation.Yaw)>5,'negative control must expose frame-dependent camera following')
local expected=20*(1-0.75^6)
for _,fps in ipairs({30,60,120})do
    local f=run(Lock,fps,0.1)
    assert(math.abs(f.rotation.Yaw-expected)<1e-8,'camera response must agree after 100 ms: '..fps)
    f=run(Lock,fps,1)
    assert(f.validations==11,'eligibility checks must stay at 10 Hz, independent of rendering: '..fps)
end
local f=fixture(Lock,60);assert(f.lock:toggle());f.dt=0
assert(f.lock:update()and f.writes==0,'zero native time must not advance camera')
f=fixture(Lock,60);assert(f.lock:toggle());f.dt=1;f.destination={X=0,Y=1000,Z=0}
assert(f.lock:update()and f.rotation.Yaw<=32,'hitch response is capped at 1/15 second')
for _,dt in ipairs({-1,1.01,0/0,math.huge})do
    f=fixture(Lock,60);assert(f.lock:toggle());f.dt=dt
    assert(not f.lock:update()and not f.lock.enabled and f.writes==0,'invalid native frame time must release lock')
end
f=fixture(Lock,120);assert(f.lock:toggle());f.target={};f.allowed=false
assert(not f.lock:update()and f.writes==0,'a changed target is revalidated before camera writes')
f=fixture(Lock,120);assert(f.lock:toggle());f.allowed=false
for _=1,11 do assert(f.lock:update())end
assert(not f.lock:update()and not f.lock.enabled,'obstruction releases at 100 ms rather than six render callbacks')
for _,point in ipairs({{X=0,Y=0,Z=0},{X=4000,Y=0,Z=0},{X=0/0,Y=0,Z=0}})do
    f=fixture(Lock,60);assert(f.lock:toggle());f.destination=point
    assert(not f.lock:update()and f.writes==0,'unusable geometry must not rotate camera')
end
f=fixture(Lock,60);assert(f.lock:toggle());f.rotation.Yaw=179
f.destination={X=1000*math.cos(math.rad(-179)),Y=1000*math.sin(math.rad(-179)),Z=0}
assert(f.lock:update()and f.rotation.Yaw>179 and f.rotation.Yaw<180,'shortest yaw across wrap remains correct')
f=fixture(Lock,60);f.lock.native.frame_seconds=function()error('disabled lock must not read native clock')end
assert(f.lock:update()and f.writes==0)
-- Exercise the actual bridge extension too: the timer must be read from this
-- receipt's Boss, and free-camera frames must never run the follow clock.
local rotation={Yaw=0,Pitch=-8};local clock_reads=0
local boss={K2_GetActorLocation=function()return{X=0,Y=0,Z=0}end}
local target={K2_GetActorLocation=function()return{X=1000*math.cos(math.rad(20)),Y=1000*math.sin(math.rad(20)),Z=0}end}
local pc={};local receipt={boss=boss,player={},remote_control={},camera_rig={},input_enabled=true,
    combat={selected_target=target}}
local Bridge={check=function(_,r)assert(r==receipt);return pc end,verify_control=function()return true end,
    update_camera=function()return true end,look=function()return true end,restore=function()return true end,
    start_skill=function()return false end}
require('player_experience_bridge').extend(Bridge)
local bridge=setmetatable({profile={id='056_youlong',camera={pivot_height=80}},
    calls={resolve=function(_,r)return r end,optional=function(_,r)return r end},
    api={remote={native={rotation=function(p)assert(p==pc);return rotation end,
                set_rotation=function(p,r)assert(p==pc);rotation=r end}},
        combat={verify_target=function()return true end},target_selector={eligible=function()return true end},
        locomotion={native={frame_seconds=function(owner)assert(owner==boss);clock_reads=clock_reads+1;return 1/30 end}}}},
    {__index=Bridge})
assert(bridge:update_camera(receipt)and clock_reads==0 and rotation.Yaw==0,'free camera stays outside timed lock')
assert(bridge:toggle_target_lock(receipt));assert(bridge:update_camera(receipt))
assert(clock_reads==1 and math.abs(rotation.Yaw-8.75)<1e-8,'bridge must use current Boss native frame time')
local Driver=require('input_driver')
local moved
bridge.move=function(_,r,x,y)assert(r==receipt);moved={x,y};return true end
local session={state='ACTIVE',receipt=receipt,bridge=bridge,poll=function()return true end,
    restore=function()error('valid locked movement must not restore')end}
local driver=Driver.new(session,{read_input=function()return{allowed=true,forward=true,yaw_degrees=0}end})
assert(driver:step())
assert(clock_reads==2 and math.abs(rotation.Yaw-13.671875)<1e-8)
assert(math.abs(moved[1]-math.cos(math.rad(rotation.Yaw)))<1e-9
    and math.abs(moved[2]-math.sin(math.rad(rotation.Yaw)))<1e-9,'locked movement must follow the final camera yaw')
print('PASS legacy negative control, 30/60/120 Hz timed camera response, 10 Hz target checks, wrap, zero/hitch/invalid time and target loss')
