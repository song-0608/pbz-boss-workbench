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
