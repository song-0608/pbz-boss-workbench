local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..root..'/tools/?.lua;'..package.path
local C=require('yanqiansui_arena_clearance');local calls=0
local function flat(p)calls=calls+1;return{X=p.X,Y=p.Y,Z=0}end
local o={X=0,Y=0,Z=96};local f={X=1,Y=0,Z=0}
local function choose(project,radius)return C.choose(project,o,f,96,110,48,1,nil,96,42,radius or 900)end
local plan=assert(choose(flat));assert(plan.clearance_cm==900 and plan.clearance_samples==24)
assert(calls==27 and plan.queries_used==calls,'only initialization queries')
calls=0
assert(not choose(function(p)calls=calls+1;if math.abs(p.Y)>150 then return nil end;return{X=p.X,Y=p.Y,Z=0}end))
assert(calls<=192,'narrow ledge must fail in a bounded pass')
calls=0
assert(not choose(function(p)calls=calls+1;return{X=p.X,Y=p.Y,Z=math.abs(p.X)>800 and -200 or 0}end))
assert(calls<=192,'height discontinuity must fail')
assert(not choose(function(p)return{X=0/0,Y=p.Y,Z=0}end))
assert(not choose(function()return nil end))
assert(not pcall(choose,flat,0),'no caller bypass')
print('PASS initialization-only clearance: flat area, narrow ledge, height discontinuity, invalid data and bounded queries')
