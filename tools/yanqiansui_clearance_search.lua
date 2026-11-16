-- Initialization only. Preserve the 9m clearance and 192-query budget.
local Base=require('arena_layout')
local Search={}
local function finite(v)return type(v)=='number'and v==v and math.abs(v)<math.huge end
local function point(v)return type(v)=='table'and finite(v.X)and finite(v.Y)and finite(v.Z)end
local function distance2(a,b)return(a.X-b.X)^2+(a.Y-b.Y)^2 end
function Search.choose(project,origin,forward,player_half,boss_half,boss_radius,attempt,rejected,target_half,target_radius,radius)
    radius=radius or 900
    assert(radius==900,'independently scoped 900cm clearance required')
    target_half=target_half or boss_half;target_radius=target_radius or boss_radius
    local used,limit=0,192
    local function bounded(p)
        if used>=limit then return nil end
        used=used+1
        return project(p)
    end
    local function clearance(plan)
        local floor=plan.boss.Z-boss_half-2
        for ring=1,3 do
            for direction=0,7 do
                local angle=direction*math.pi/4
                local desired={X=plan.boss.X+math.cos(angle)*radius*ring/3,
                    Y=plan.boss.Y+math.sin(angle)*radius*ring/3,Z=floor}
                local p=bounded(desired)
                if not point(p)or distance2(p,desired)>35^2 or math.abs(p.Z-floor)>30 then return nil end
            end
        end
        plan.clearance_cm=radius;plan.clearance_samples=24
        plan.queries_used=used;plan.queries_bound=limit
        return plan
    end
    -- Base validates vectors/capsules and preserves the established first choice.
    local initial=Base.choose(bounded,origin,forward,player_half,boss_half,boss_radius,
        attempt,rejected,target_half,target_radius)
    if initial then
        local plan=clearance(initial)
        if plan then return plan end
    end
    -- Search centres up to 18m away; every participant remains inside 30m.
    -- No actor moves and no cached terrain result authorizes spawning.
    local heading=math.atan(forward.Y,forward.X)
    local scale=math.max(1,(boss_radius+target_radius+40)/250,(2*target_radius+40)/250)
    local floor=origin.Z-player_half
    for _,length in ipairs({1800,1350,1000})do
        for n=0,7 do
            if used>=limit then break end
            local direction=(n+(attempt or 1)-1)%8
            local key='clearance-search:'..length..':'..direction
            if not(rejected and rejected[key])then
                local angle=heading+direction*math.pi/4
                local x,y=math.cos(angle),math.sin(angle)
                local points={{length,0},{length+250*scale,0},{length+200*scale,300*scale}}
                local rows,accepted={},true
                for index,offset in ipairs(points)do
                    local desired={X=origin.X+x*offset[1]-y*offset[2],Y=origin.Y+y*offset[1]+x*offset[2],Z=floor}
                    if distance2(desired,origin)>3000^2 then accepted=false;break end
                    local p=bounded(desired)
                    if not point(p)or distance2(p,desired)>35^2 or math.abs(p.Z-floor)>30 then accepted=false;break end
                    rows[index]={X=p.X,Y=p.Y,Z=p.Z+(index==1 and boss_half or target_half)+2}
                    if distance2(rows[index],origin)<250^2 or distance2(rows[index],origin)>3000^2 then accepted=false;break end
                    for previous=1,index-1 do
                        local a=index==1 and boss_radius or target_radius
                        local b=previous==1 and boss_radius or target_radius
                        if distance2(rows[index],rows[previous])<(a+b+40)^2 then accepted=false;break end
                    end
                    if not accepted then break end
                end
                if accepted then
                    local plan=clearance({boss=rows[1],targets={rows[2],rows[3]},heading=math.deg(angle),key=key})
                    if plan then return plan end
                end
            end
        end
    end
    return nil,'no verified 9m same-level movement clearance within 192 navigation queries; move to open ground'
end
return Search
