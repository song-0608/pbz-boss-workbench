local root,candidate=assert(arg[1]),assert(arg[2]);package.path=candidate..'/PBZBossControl/Scripts/?.lua;'..package.path
local Extension=require('player_experience_bridge')
local target={name='target',address=2,class='Enemy'}
local boss={K2_GetActorLocation=function()return{X=0,Y=0,Z=0}end}
local actor={K2_GetActorLocation=function()return{X=1000,Y=100,Z=0}end}
local r={input_enabled=true,combat={selected_target=target},boss='boss',player='player',remote_control={},camera_rig={}}
local f={camera=0,looks=0,restores=0,rotation={Yaw=0,Pitch=0},eligible=true,logs={}}
local base={}
function base:check(receipt)assert(receipt==r);return{}end
function base:verify_control()return true end
function base:update_camera()f.camera=f.camera+1;return true end
function base:look()f.looks=f.looks+1;return true end
function base:restore()f.restores=f.restores+1;return true end
local Bridge=Extension.extend(base)
local b=setmetatable({profile={camera={}},calls={optional=function(_,ref)return ref==target and actor or nil end,
    resolve=function(_,ref)if ref=='boss'then return boss elseif ref==target then return actor else return{}end end},
    api={remote={native={rotation=function()return f.rotation end,set_rotation=function(_,value)f.rotation=value end}},
        combat={verify_target=function()return true end},target_selector={eligible=function()return f.eligible end},
        experience_log=function(key,value)f.logs[#f.logs+1]=key..'='..value end}}, {__index=Bridge})
assert(b:update_camera(r)and r.player_target_lock.enabled and f.camera==1)
assert(r.player_target_lock.target==target,'store logical target reference rather than engine wrapper')
assert(b:look(r,1,1)and f.looks==0)
r.target_transition={};local yaw=f.rotation.Yaw;assert(b:update_camera(r)and f.rotation.Yaw==yaw)
r.target_transition=nil
assert(b:toggle_target_lock(r)and not r.player_target_lock.enabled)
assert(b:look(r,1,1)and f.looks==1)
assert(b:toggle_target_lock(r)and r.player_target_lock.enabled)
assert(b:restore(r)and f.restores==1 and not r.player_target_lock.enabled and not r.player_target_lock.target)
local old_camera=f.camera;r.input_enabled=false
assert(not pcall(b.toggle_target_lock,b,r)and f.camera==old_camera)
print('PASS bridge lock initialization, F7 wait, free camera, logical references and restoration')
