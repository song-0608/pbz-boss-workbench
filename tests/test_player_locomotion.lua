local Motion=require('player_locomotion');local Tuning=require('player_3c_tuning')
local function fixture(fps)
    local actor={};local state={speed=160,acceleration=200,yaw=0,writes=0}
    local calls={reference=function(_,o)return o end,resolve=function(_,o)assert(o==actor);return o end,optional=function()return actor end}
    local native={binding_verified=true,read=function()return{speed=state.speed,acceleration=state.acceleration}end,
        write=function(_,s)state.writes=state.writes+1;if s.speed then state.speed=s.speed end;if s.acceleration then state.acceleration=s.acceleration end end,
        yaw=function()return state.yaw end,face=function(_,yaw)state.yaw=yaw end,frame_seconds=function()return 1/fps end}
    local motion=Motion.new(calls,native,Tuning.resolve('058_maddoctor'));return motion,motion:capture(actor),state,calls
end
for _,fps in ipairs({30,60,120})do
    local m,t,s=fixture(fps)
    for i=1,fps/10 do assert(m:step(t,0,1,1))end
    assert(math.abs(s.yaw-54)<0.00001,'turn speed must be independent of frame rate: '..fps)
    assert(s.speed==480 and s.acceleration==800 and s.writes==1,'speed applies once within multiplier bounds')
    assert(m:suspend(t));assert(s.speed==160 and s.acceleration==200,'native skill must receive its own walking limits')
    s.speed=180;assert(m:step(t,1,0,1));assert(m:restore(t));assert(s.speed==180,'preserve native post-skill baseline')
end
local m,t,s=fixture(60);assert(m:step(t,1,0,1));s.speed=12
assert(not pcall(m.step,m,t,1,0,1),'external movement changes must not be force-overwritten')
assert(not pcall(m.suspend,m,t),'contested field must remain visible as a failure')
assert(s.speed==12 and s.acceleration==200,'uncontested field must still be recovered')
m,t,s=fixture(60)
local write=m.native.write;local first=true
m.native.write=function(boss,values)
    if first then first=false;s.speed=values.speed;error('partial native write')end
    return write(boss,values)
end
assert(not pcall(m.step,m,t,1,0,1));assert(m:restore(t));assert(s.speed==160 and s.acceleration==200,'partial write must be recoverable')
m,t,s=fixture(1);assert(m:step(t,0,1,1));assert(s.yaw<=36,'hitch must not produce a full snap turn')
m,t,s=fixture(60);assert(m:restore(t));assert(not pcall(m.step,m,t,1,0,1),'retired ticket cannot move')
local events={};m,t,s=fixture(60);m.log=function(k,v)events[#events+1]={k,v}end
assert(m:step(t,1,0,1));assert(m:step(t,1,0,1));assert(#events==1 and events[1][1]=='WALK_LIMITS',
    'movement logging must record verified changes, not every frame')
assert(m:restore(t));assert(#events==2 and events[2][1]=='WALK_RESTORED')
print('PASS walking speed/acceleration bounds, 30/60/120 Hz facing, skill/native restoration, contested-write rejection and hitch limit')
