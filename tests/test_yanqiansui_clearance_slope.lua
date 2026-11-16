local root=assert(arg[1]);local candidate=assert(arg[2]);local centered=assert(arg[3])
package.path=candidate..'/PBZBossControl/Scripts/?.lua;'..root..'/tools/?.lua;'..package.path
local C=require('yanqiansui_clearance_core')
local Old=assert(loadfile(centered..'/PBZBossControl/Scripts/yanqiansui_clearance_core.lua'))()
local Terrain=require('yanqiansui_clearance_slope')
local origin={X=0,Y=0,Z=96};local forward={X=1,Y=0,Z=0}
local function run(project,module,rejected)
    local calls=0
    local plan=(module or C).choose(function(p)calls=calls+1;return project(p)end,origin,forward,96,110,48,1,rejected,96,42)
    assert(calls<=192)
    if plan then assert(plan.clearance_cm==900 and plan.clearance_samples==24 and plan.queries_used==calls)end
    return plan,calls
end
local function flat(p)return{X=p.X,Y=p.Y,Z=0}end
local plan,calls=run(flat);assert(plan and plan.key=='1:1'and calls==27)
local function ramp(degrees)
    return function(p)return{X=p.X,Y=p.Y,Z=p.X*math.tan(math.rad(degrees))}end
end
assert(not run(ramp(4),Old),'reproduce fixed-height false refusal on a gentle continuous slope')
plan=assert(run(ramp(4)));assert(math.abs(plan.terrain_slope_degrees-4)<1e-6)
assert(run(ramp(5)),'bounded five-degree ramp accepted')
assert(not run(ramp(5.01)),'steeper terrain refused')
assert(not run(function(p)if math.abs(p.Y)<150 then return flat(p)end end),'narrow ledge refused')
assert(not run(function(p)return{X=p.X,Y=p.Y,Z=math.abs(p.X)>800 and -200 or 0}end),'cliff refused')
assert(not run(function(p)return{X=p.X+36,Y=p.Y,Z=0}end),'projection drift refused')
assert(not run(function()return nil end),'missing navigation refused')
assert(not run(function(p)return{X=p.X,Y=p.Y,Z=0/0}end),'nonfinite point refused')
assert(not pcall(C.choose,flat,origin,forward,0,110,48,1,nil,96,42),'invalid capsule refused')
assert(not pcall(C.choose,flat,origin,forward,96,110,48,1,nil,96,42,899),'radius cannot be lowered')
local base={boss={X=0,Y=0,Z=112},targets={{X=250,Y=0,Z=98},{X=200,Y=300,Z=98}}}
local function verify(project)return Terrain.verify(project,base,110,96,900)end
assert(not verify(function(p)return{X=p.X,Y=p.Y,Z=p.Y>350 and 31 or 0}end),'31cm ledge refused')
assert(not verify(function(p)return{X=p.X,Y=p.Y,Z=p.X>350 and(p.Y>350 and -29 or 29)or 0}end),'tangential 58cm jump refused')
assert(not verify(function(p)return{X=p.X,Y=p.Y,Z=p.X>800 and 101 or 0}end),'100cm absolute height bound')
assert(verify(ramp(4)))
local oldtarget=base.targets[2].Z;base.targets[2].Z=150
assert(not verify(flat),'targets must lie on the verified footprint')
base.targets[2].Z=oldtarget
print('PASS slope clearance: old false refusal reproduced; 9m/24/192 retained; <=5deg plane, 30cm residual/discontinuity, 100cm height, targets and failure gates')
