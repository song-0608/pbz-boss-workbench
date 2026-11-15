local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Input=require('ue_input')
local names,checks,keys=0,0,0
local pc={}
function pc:IsMoveInputIgnored()return false end
function pc:IsLookInputIgnored()return false end
function pc:GetControlRotation()return{Yaw=90}end
function pc:GetInputMouseDelta(x,y)x.DeltaX=10;y.DeltaY=-5 end
function pc:IsInputKeyDown(key)keys=keys+1;return key.KeyName=='W'end
local bridge={check=function()checks=checks+1;return pc end}
local api={make_name=function(key)names=names+1;return key end,game_paused=function()return false end}
local input=Input.new(bridge,api,{input_verified=true,mouse_scale=0.1})
for _=1,100 do local r=input:read({});assert(r.allowed and r.forward and not r.backward and r.look_yaw==1)end
assert(names==4 and checks==100 and keys==400,'cache names only; preserve every-frame identity and real input reads')
bridge.check=function()error('stale identity')end
assert(not pcall(input.read,input,{}),'cached names must never bypass a stale participant')
print('PASS four cached FNames with unchanged per-frame input and identity checks')
