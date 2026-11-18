local root=assert(arg[1]);local Driver=require('input_driver');local Tuning=require('player_3c_tuning')
local function driver_fixture(Class)
    local state={yaw=0,rendered={},moves={}}
    local s={state='ACTIVE',receipt={},poll=function()return true end,restore=function(self)self.state='OFF';return true end}
    s.bridge={verify_control=function()return true end,
        look=function(_,r,y,p)state.yaw=state.yaw+y;return true,state.yaw end,
        update_camera=function()state.rendered[#state.rendered+1]=state.yaw;return true end,
        move=function(_,r,x,y)state.moves[#state.moves+1]={x,y};return true end}
    return Class.new(s,{read_input=function()return{allowed=true,forward=true,yaw_degrees=0,look_yaw=9}end}),s,state
end
local old=assert(loadfile(root..'/releases/ahua-boss-workbench-v5-3f29975fe3b8826f/PBZBossControl/Scripts/input_driver.lua'))()
local driver,session,state=driver_fixture(old);assert(driver:step());assert(state.rendered[1]==0,'negative control must expose old-frame camera')
driver,session,state=driver_fixture(Driver);assert(driver:step());assert(state.rendered[1]==9,'new look must render in the same callback')
assert(math.abs(state.moves[1][2]-math.sin(math.rad(9)))<1e-9,'movement must use actual post-look yaw')

local events={};local rotation={Yaw=0,Pitch=0};local lock={enabled=false,toggle=function(self)self.enabled=not self.enabled;return true end,
    clear=function(self)self.enabled=false;return true end,update=function()return true end}
local Bridge={check=function()return{}end,verify_control=function()return true end,update_camera=function()return true end,
    look=function(_,r,y,p)rotation.Yaw=rotation.Yaw+y;return true end,restore=function()return true end,
    start_skill=function()return false end}
require('player_experience_bridge').extend(Bridge)
local b=setmetatable({profile={id='058_maddoctor'},api={experience_log=function(k,v)events[#events+1]={k,v}end,
    remote={native={rotation=function()return rotation end}}}},{__index=Bridge})
local r={input_enabled=true,camera_rig={},combat={},remote_control={},player_target_lock=lock}
assert(b:update_camera(r)and not lock.enabled and r.player_lock_initialized,'camera must initially stay free')
assert(b:toggle_target_lock(r)and lock.enabled)
assert(b:look(r,0.2,0)and lock.enabled and rotation.Yaw==0,'small lock jitter must not rotate camera')
local accepted,yaw=b:look(r,1.2,0);assert(accepted and yaw==1.2 and not lock.enabled,'intentional mouse turn must release camera lock')
assert(b:start_skill(r,'skill_01')==false);assert(b:start_skill(r,'skill_01')==false)
assert(r.native_skill_rejections.skill_01==2,'repeated native rejections must remain diagnosable')
local ids={'ahua_guitoudao','057_wanjun','073_yanqiansui','056_youlong','071_xianzhe','058_maddoctor'}
for _,id in ipairs(ids)do local t=Tuning.resolve(id);assert(t.mouse_scale==0.22 and t.walk_speed_cm_s>=420 and t.walk_speed_cm_s<=520)end
assert(not pcall(Tuning.resolve,'058_maddoctor',{walk_speed_cm_s=9000}))
assert(not pcall(Tuning.resolve,'058_maddoctor',{mouse_scale=0/0}))
local binding={input_verified=true,mouse_scale=0.1}
local pc={IsMoveInputIgnored=function()return false end,IsLookInputIgnored=function()return false end,
    IsInputKeyDown=function()return false end,GetControlRotation=function()return{Yaw=0}end,
    GetInputMouseDelta=function(_,x,y)x.DeltaX=10;y.DeltaY=0 end}
local input=require('ue_input').new({profile={id='058_maddoctor'},check=function()return pc end},
    {make_name=function(s)return s end,game_paused=function()return false end},binding):read({})
assert(input.look_yaw==2.2 and binding.mouse_scale==0.1,'tuning must not edit historical profile data')
local OldInput=assert(loadfile(root..'/releases/ahua-boss-workbench-v5-3f29975fe3b8826f/PBZBossControl/Scripts/ue_input.lua'))()
local function turn_at_rate(Class,fps,tuned,rate)
    local delta=rate/fps/0.22
    local controller={IsMoveInputIgnored=function()return false end,IsLookInputIgnored=function()return false end,
        IsInputKeyDown=function()return false end,GetControlRotation=function()return{Yaw=0}end,
        GetInputMouseDelta=function(_,x,y)x.DeltaX=delta;y.DeltaY=0 end}
    local bridge={check=function()return controller end,api={}}
    if tuned then bridge.profile={id='056_youlong'};bridge.api.locomotion={settings=Tuning.resolve('056_youlong')}end
    local reader=Class.new(bridge,{make_name=function(v)return v end,game_paused=function()return false end},
        {input_verified=true,mouse_scale=0.22})
    local degrees=0
    for _=1,fps do degrees=degrees+reader:read({}).look_yaw end
    return degrees
end
assert(math.abs(turn_at_rate(OldInput,30,false,600)-300)<1e-8
    and math.abs(turn_at_rate(OldInput,120,false,600)-600)<1e-8,'negative control must expose discarded low-fps mouse motion')
for _,fps in ipairs({30,60,120})do
    assert(math.abs(turn_at_rate(require('ue_input'),fps,true,600)-600)<1e-8,
        '3C sampler must retain the same finite mouse displacement at '..fps..' Hz')
end
assert(turn_at_rate(require('ue_input'),30,true,100000)==1350,'extreme mouse input remains capped at 45 degrees per callback')
assert(not pcall(Tuning.resolve,'056_youlong',{look_step_degrees=46}))
print('PASS old-camera negative control, same-frame mouse/movement, free camera, manual lock override, six-role tuning and native rejection diagnostics')
print('PASS 30/60/120 Hz mouse-displacement retention, legacy negative control and paired native bounds; no engine smoothness claim')
