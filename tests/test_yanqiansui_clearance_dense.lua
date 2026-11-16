local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..root..'/tools/?.lua;'..package.path
local C=require('yanqiansui_clearance_dense')
local Old=require('yanqiansui_clearance_search')
local origin={X=0,Y=0,Z=96};local forward={X=1,Y=0,Z=0}
local function run(project,module,rejected)
    local calls=0
    local p,reason=(module or C).choose(function(v)calls=calls+1;return project(v)end,origin,forward,96,110,48,1,rejected,96,42)
    assert(calls<=192,'bounded initialization queries')
    if p then
        assert(p.queries_used==calls and p.clearance_cm==900 and p.clearance_samples==24)
        for _,r in ipairs({p.boss,table.unpack(p.targets)})do assert(r.X*r.X+r.Y*r.Y<=3000^2)end
    end
    return p,calls,reason
end
local function flat(p)return{X=p.X,Y=p.Y,Z=0}end
local p,calls=run(flat);assert(p and calls==27 and p.key=='1:1')
local angle=math.pi/16
local cx,cy=2400*math.cos(angle),2400*math.sin(angle)
local function missed_courtyard(p)
    if math.abs(p.X-cx)<=950 and math.abs(p.Y-cy)<=950 then return flat(p)end
end
assert(not run(missed_courtyard,Old),'regression must reproduce the old sparse miss')
p=assert(run(missed_courtyard));assert(math.abs(p.boss.X-cx)<.001 and math.abs(p.boss.Y-cy)<.001)
local rejected={[p.key]=true};assert(not run(missed_courtyard,C,rejected),'rejected placement cannot be retried')
assert(not run(function(p)if math.abs(p.Y)<150 then return flat(p)end end),'ledge rejected')
assert(not run(function(p)return{X=p.X,Y=p.Y,Z=math.abs(p.X)>800 and -200 or 0}end),'height discontinuity rejected')
assert(not run(function(p)return{X=p.X+200,Y=p.Y,Z=0}end),'navigation drift rejected')
assert(not run(function()return nil end),'missing navigation rejected')
assert(not run(function(p)return{X=0/0,Y=p.Y,Z=0}end),'nonfinite data rejected')
assert(not pcall(C.choose,flat,origin,forward,96,110,48,1,nil,96,42,300),'cannot weaken footprint')
assert(not pcall(C.choose,flat,origin,forward,0,110,48,1,nil,96,42),'capsule validation retained')
package.loaded.yanqiansui_clearance_core=C
local Trace=require('yanqiansui_terrain_trace')
local output,old_print={},print;print=function(s)output[#output+1]=s end
local a,ac=run(missed_courtyard);local b,bc=run(missed_courtyard,Trace)
assert(a.key==b.key and ac==bc and output[1]:find('accepted:true',1,true))
print=old_print
print('PASS dense search: sparse miss recovered, normal first choice, 9m/24/192, 30m actors and all rejection gates retained')
