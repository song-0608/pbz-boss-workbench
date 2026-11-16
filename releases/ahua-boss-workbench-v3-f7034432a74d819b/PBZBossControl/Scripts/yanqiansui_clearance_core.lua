-- Initialization only. Denser candidates; unchanged 9m/24 samples/192 queries.
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
    local Terrain=(function()
-- Initialization-only replacement for the flat footprint verifier.
-- A fitted gentle plane permits slopes; ledges and discontinuities remain refused.
local Terrain={}
local function finite(x)return type(x)=='number'and x==x and math.abs(x)<math.huge end
local function point(p)return type(p)=='table'and finite(p.X)and finite(p.Y)and finite(p.Z)end
local function d2(a,b)return(a.X-b.X)^2+(a.Y-b.Y)^2 end
function Terrain.verify(project,plan,boss_half,target_half,radius)
    assert(radius==900,'900cm footprint required')
    local center={X=plan.boss.X,Y=plan.boss.Y,Z=plan.boss.Z-boss_half-2}
    local samples,previous={},{}
    local sx,sy
    local function residual(p)return p.Z-center.Z-sx*(p.X-center.X)-sy*(p.Y-center.Y)end
    local function valid(p)return math.abs(p.Z-center.Z)<=100 and math.abs(residual(p))<=30 end
    for ring=1,3 do
        local current={}
        for direction=0,7 do
            local angle=direction*math.pi/4
            local desired={X=center.X+math.cos(angle)*radius*ring/3,
                Y=center.Y+math.sin(angle)*radius*ring/3,Z=center.Z}
            local p=project(desired)
            if not point(p)or d2(p,desired)>35^2 or math.abs(p.Z-center.Z)>100 then return nil end
            samples[#samples+1]=p;current[direction+1]=p
            if ring==1 and direction==2 then
                local east,north=samples[1],samples[3]
                local ex,ey=east.X-center.X,east.Y-center.Y
                local nx,ny=north.X-center.X,north.Y-center.Y
                local determinant=ex*ny-ey*nx
                if math.abs(determinant)<1 then return nil end
                sx=((east.Z-center.Z)*ny-ey*(north.Z-center.Z))/determinant
                sy=(ex*(north.Z-center.Z)-(east.Z-center.Z)*nx)/determinant
                if sx*sx+sy*sy>math.tan(math.rad(5))^2+1e-12 then return nil end
                for _,q in ipairs(samples)do if not valid(q)then return nil end end
            elseif sx and not valid(p)then return nil end
            if sx and previous[direction+1]and math.abs(residual(p)-residual(previous[direction+1]))>30 then return nil end
        end
        for direction=1,8 do
            if math.abs(residual(current[direction])-residual(current[direction%8+1]))>30 then return nil end
        end
        previous=current
    end
    for _,target in ipairs(plan.targets)do
        if not valid({X=target.X,Y=target.Y,Z=target.Z-target_half-2})then return nil end
    end
    plan.terrain_slope_degrees=math.deg(math.atan(math.sqrt(sx*sx+sy*sy)))
    plan.terrain_residual_limit_cm=30
    return plan
end
return Terrain

end)()
    local function clearance(plan)
        if not Terrain.verify(bounded,plan,boss_half,target_half,radius)then return nil end
        plan.clearance_cm=radius;plan.clearance_samples=24
        plan.queries_used=used;plan.queries_bound=limit
        return plan
    end
    local initial=Base.choose(bounded,origin,forward,player_half,boss_half,boss_radius,
        attempt,rejected,target_half,target_radius)
    if initial then
        local plan=clearance(initial)
        if plan then return plan end
    end
    local heading=math.atan(forward.Y,forward.X)
    local scale=math.max(1,(boss_radius+target_radius+40)/250,(2*target_radius+40)/250)
    local floor=origin.Z-player_half
    -- Preserve the old 18m choices first. Interleave diagonal refinements and
    -- farther centres; do not spend the whole budget on one distance or side.
    local passes={{1800,0,8},{2400,0.5,16},{1800,0.5,8},{1350,0,16},{1000,0.5,16}}
    for _,pass in ipairs(passes)do
        local length,phase,count=table.unpack(pass)
        for n=0,count-1 do
            if used>=limit then return nil,'navigation query budget exhausted; move to open ground'end
            local direction=(n+(attempt or 1)-1)%count
            local key='dense-clearance:'..length..':'..phase..':'..direction
            local legacy='clearance-search:'..length..':'..direction
            if not(rejected and(rejected[key]or(count==8 and phase==0 and rejected[legacy])))then
                local angle=heading+(direction+phase)*2*math.pi/count
                local x,y=math.cos(angle),math.sin(angle)
                local points={{length,0},{length+250*scale,0},{length+200*scale,300*scale}}
                local rows,accepted={},true
                local projected_floor
                for index,offset in ipairs(points)do
                    local desired={X=origin.X+x*offset[1]-y*offset[2],Y=origin.Y+y*offset[1]+x*offset[2],Z=index==1 and floor or projected_floor}
                    if distance2(desired,origin)>3000^2 then accepted=false;break end
                    local p=bounded(desired)
                    if not point(p)or distance2(p,desired)>35^2 or math.abs(p.Z-(index==1 and floor or projected_floor))>(index==1 and 100 or 30) then accepted=false;break end
                    if index==1 then projected_floor=p.Z end
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
