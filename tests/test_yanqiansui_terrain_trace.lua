local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..root..'/tools/?.lua;'..package.path
local Core=require('yanqiansui_clearance_search')
package.loaded.yanqiansui_clearance_core=Core
local Trace=require('yanqiansui_terrain_trace')
local origin={X=0,Y=0,Z=96};local forward={X=1,Y=0,Z=0}
local actual_print=print;local logs={};print=function(s)logs[#logs+1]=s end
local cases={
    function(p)return{X=p.X,Y=p.Y,Z=0}end,
    function(p)if p.X>=800 and p.X<=2800 and math.abs(p.Y)<=1000 then return{X=p.X,Y=p.Y,Z=0}end end,
    function(p)if math.abs(p.Y)<150 then return{X=p.X,Y=p.Y,Z=0}end end,
    function(p)return{X=p.X,Y=p.Y,Z=math.abs(p.X)>800 and -200 or 0}end,
    function(p)return{X=p.X+200,Y=p.Y,Z=0}end,
    function()return nil end,
}
for _,project in ipairs(cases)do
    local first,second={},{}
    local function spy(rows)return function(p)
        local value=project(p);rows[#rows+1]=string.format('%g,%g,%g:%s',p.X,p.Y,p.Z,value and value.Z or 'nil');return value
    end end
    local a,reason_a=Core.choose(spy(first),origin,forward,96,110,48,1,nil,96,42)
    local b,reason_b=Trace.choose(spy(second),origin,forward,96,110,48,1,nil,96,42)
    assert(table.concat(first,';')==table.concat(second,';'),'same calls, arguments and order required')
    assert((a~=nil)==(b~=nil)and reason_a==reason_b)
    assert(#second<=192 and logs[#logs]:find('queries:'..#second,1,true))
    if a then assert(a.key==b.key and a.boss.X==b.boss.X and a.queries_used==b.queries_used and b.clearance_cm==900 and b.clearance_samples==24)end
end
assert(not pcall(Trace.choose,cases[1],origin,forward,96,110,48,1,nil,96,42,300))
print=actual_print
print('PASS terrain trace makes identical navigation calls and decisions; preserves 9m/24 samples/192 bound and errors')
