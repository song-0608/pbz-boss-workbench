-- 用途：在主角附近选择同层导航落点；查询不成功就拒绝，不能以强制生成掩盖地形问题。
local Layout={}
local function finite(x)return type(x)=='number'and x==x and math.abs(x)<math.huge end
local function point(p)return type(p)=='table'and finite(p.X)and finite(p.Y)and finite(p.Z)end
local function d2(a,b)return(a.X-b.X)^2+(a.Y-b.Y)^2 end
function Layout.visible(query,boss,targets)
    assert(type(query)=='function'and type(targets)=='table'and #targets==2,'two targets and verified visibility reader required')
    for index,target in ipairs(targets)do
        local ok,visible=pcall(query,boss,target)
        if not ok or visible~=true then return false,'owned target '..index..' not visible from spawned boss; clean before choosing another local layout'end
    end
    return true
end
function Layout.choose(project,origin,forward,player_half,boss_half,boss_radius,attempt,rejected,target_half,target_radius)
    target_half=target_half or boss_half;target_radius=target_radius or boss_radius
    assert(type(project)=='function'and point(origin)and point(forward),'layout vectors required')
    assert(finite(player_half)and player_half>0 and finite(boss_half)and boss_half>0
        and player_half<=1024 and boss_half<=1024
        and finite(boss_radius)and boss_radius>0 and boss_radius<=256
        and finite(target_half)and target_half>0 and target_half<=1024
        and finite(target_radius)and target_radius>0 and target_radius<=256,'verified bounded capsule dimensions required')
    local base=math.atan(forward.Y,forward.X)
    local offsets={0,math.pi/2,-math.pi/2,math.pi,math.pi/4,-math.pi/4,3*math.pi/4,-3*math.pi/4}
    local formations={{{450,0},{700,0},{650,300}},{{350,0},{600,0},{550,250}},{{650,0},{900,0},{800,300}}}
    local scale=math.max(1,(boss_radius+target_radius+40)/250,(2*target_radius+40)/250)
    for formation_index,formation in ipairs(formations)do
      for index=1,#offsets do
        local direction=(index+(attempt or 1)-2)%#offsets+1
        local key=direction..':'..formation_index
        local theta=base+offsets[direction]
        local x,y=math.cos(theta),math.sin(theta)
        local rows={};local accepted=not(rejected and rejected[key])
        for _,offset in ipairs(accepted and formation or{})do
            local desired={X=origin.X+scale*(x*offset[1]-y*offset[2]),Y=origin.Y+scale*(y*offset[1]+x*offset[2]),Z=origin.Z}
            local projected=project(desired)
            if not point(projected)or d2(desired,projected)>150^2
                or math.abs(projected.Z-(origin.Z-player_half))>100 then accepted=false;break end
            rows[#rows+1]={X=projected.X,Y=projected.Y,Z=projected.Z+(#rows==0 and boss_half or target_half)+2}
        end
        if accepted then
            for i=1,3 do
                if d2(origin,rows[i])<250^2 then accepted=false end
                for j=1,i-1 do
                    local ri=i==1 and boss_radius or target_radius
                    local rj=j==1 and boss_radius or target_radius
                    if d2(rows[i],rows[j])<(ri+rj+40)^2 then accepted=false end
                end
            end
        end
        if accepted then return{boss=rows[1],targets={rows[2],rows[3]},heading=math.deg(theta),key=key,queries_bound=72}end
      end
    end
    return nil,'no same-height separated navigable layout in the bounded local area; move to open ground'
end
return Layout
