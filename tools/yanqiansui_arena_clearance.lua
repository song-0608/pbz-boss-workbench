-- Initialization only: reject narrow ledges before spawning a long-motion Boss.
local Base=require('arena_layout')
local Clearance={}
local function finite(v)return type(v)=='number'and v==v and math.abs(v)<math.huge end
local function point(v)return type(v)=='table'and finite(v.X)and finite(v.Y)and finite(v.Z)end
function Clearance.choose(project,origin,forward,player_half,boss_half,boss_radius,attempt,rejected,target_half,target_radius,radius)
    radius=radius or 900
    assert(radius==900,'independently scoped 900cm clearance required')
    local blocked={};for k,v in pairs(rejected or{})do blocked[k]=v end
    local queries,limit=0,192
    local function bounded(p)
        if queries>=limit then return nil end
        queries=queries+1
        return project(p)
    end
    for _=1,5 do
        local plan=Base.choose(bounded,origin,forward,player_half,boss_half,boss_radius,attempt,blocked,target_half,target_radius)
        if not plan then break end
        local floor=plan.boss.Z-boss_half-2
        local accepted=true
        for ring=1,3 do
            if not accepted then break end
            for direction=0,7 do
                local angle=direction*math.pi/4
                local desired={X=plan.boss.X+math.cos(angle)*radius*ring/3,
                    Y=plan.boss.Y+math.sin(angle)*radius*ring/3,Z=floor}
                local p=bounded(desired)
                if not point(p)or(p.X-desired.X)^2+(p.Y-desired.Y)^2>35^2
                    or math.abs(p.Z-floor)>30 then accepted=false;break end
            end
        end
        if accepted then
            plan.clearance_cm=radius;plan.clearance_samples=24;plan.queries_used=queries;plan.queries_bound=limit
            return plan
        end
        blocked[plan.key]=true
        if queries>=limit then break end
    end
    return nil,'no verified 9m same-level movement clearance within 192 navigation queries; move to open ground'
end
return Clearance
