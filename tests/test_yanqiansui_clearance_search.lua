local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..root..'/tools/?.lua;'..package.path
local C=require('yanqiansui_clearance_search')
local origin={X=0,Y=0,Z=96};local forward={X=1,Y=0,Z=0}
local function run(project,rejected)
    local calls=0
    local p,reason=C.choose(function(v)calls=calls+1;return project(v)end,origin,forward,96,110,48,1,rejected,96,42)
    assert(calls<=192,'one bounded initialization pass')
    if p then assert(p.queries_used==calls and p.clearance_cm==900 and p.clearance_samples==24)end
    return p,calls,reason
end
local function flat(p)return{X=p.X,Y=p.Y,Z=0}end
local p,calls=run(flat);assert(p and calls==27 and p.key=='1:1','preserve normal first layout')
local function courtyard(p)
    if p.X>=800 and p.X<=2800 and math.abs(p.Y)<=1000 then return flat(p)end
end
p=assert(run(courtyard));assert(p.key=='clearance-search:1800:0'and p.boss.X==1800)
assert(not run(courtyard,{['clearance-search:1800:0']=true}),'honor rejected placement keys')
assert(not run(function(p)if math.abs(p.Y)<150 then return flat(p)end end),'narrow ledge rejected')
assert(not run(function(p)return{X=p.X,Y=p.Y,Z=math.abs(p.X)>800 and -200 or 0}end),'height discontinuity rejected')
assert(not run(function(p)return{X=p.X+200,Y=p.Y,Z=0}end),'projected lateral drift rejected')
assert(not run(function(p)return{X=0/0,Y=p.Y,Z=0}end),'nonfinite coordinates rejected')
assert(not run(function()return nil end),'unavailable navigation rejected')
assert(not pcall(C.choose,flat,origin,forward,96,110,48,1,nil,96,42,300),'clearance cannot be weakened')
assert(not pcall(C.choose,flat,origin,forward,0,110,48,1,nil,96,42),'capsule validation preserved')
print('PASS bounded clearance search: preserved first choice, distant courtyard, reject key, ledge, height, drift and invalid data')
