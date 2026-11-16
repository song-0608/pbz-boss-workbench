local root=assert(arg[1]);local candidate=assert(arg[2])
package.path=candidate..'/PBZBossControl/Scripts/?.lua;'..root..'/tools/?.lua;'..package.path
local C=require('yanqiansui_clearance_core')
local Old=require('yanqiansui_clearance_dense')
local origin={X=0,Y=0,Z=96};local forward={X=1,Y=0,Z=0}
local function run(project,module,rejected)
    local calls=0
    local plan=(module or C).choose(function(p)calls=calls+1;return project(p)end,origin,forward,96,110,48,1,rejected,96,42)
    assert(calls<=192)
    if plan then
        assert(plan.clearance_cm==900 and plan.clearance_samples==24 and plan.queries_used==calls)
        for _,p in ipairs({plan.boss,table.unpack(plan.targets)})do assert(p.X*p.X+p.Y*p.Y<=3000^2)end
    end
    return plan,calls
end
local function courtyard(height)
    return function(p)
        if p.X>=900 and p.X<=2700 and math.abs(p.Y)<=900 then return{X=p.X,Y=p.Y,Z=height}end
    end
end
assert(not run(courtyard(80),Old),'old search wrongly anchors added centres and targets to the player floor')
local p=assert(run(courtyard(80)))
assert(p.boss.Z==192 and p.targets[1].Z==178 and p.targets[2].Z==178)
assert(not run(courtyard(80),C,{[p.key]=true}),'rejected candidate remains blocked')
assert(not run(courtyard(101)),'centre must retain the established 100cm same-level bound')
local flat=function(p)return{X=p.X,Y=p.Y,Z=0}end
local first,n=run(flat);assert(first.key=='1:1'and n==27,'normal placement and queries remain identical')
assert(not run(function(p)if math.abs(p.Y)<150 then return flat(p)end end),'ledge rejected')
assert(not run(function(p)return{X=p.X,Y=p.Y,Z=math.abs(p.X)>800 and -200 or 0}end),'cliff rejected')
assert(not run(function(p)return{X=p.X+36,Y=p.Y,Z=0}end),'35cm footprint drift bound retained')
assert(not run(function()return nil end),'unavailable navigation rejected')
assert(not run(function(p)return{X=p.X,Y=p.Y,Z=0/0}end),'nonfinite height rejected')
assert(not pcall(C.choose,flat,origin,forward,96,110,48,1,nil,96,42,899),'900cm footprint cannot be reduced')
local function split(p)
    if p.X>=900 and p.X<=2700 and math.abs(p.Y)<=900 then
        return{X=p.X,Y=p.Y,Z=80+(p.Y>350 and 31 or 0)}
    end
end
assert(not run(split),'31cm footprint discontinuity still rejected relative to projected centre')
print('PASS centred floor: reproduce old false refusal; 9m/24/192, 100cm centre, 30cm targets/footprint, rejected keys and all failure gates')
