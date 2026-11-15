local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Layout=require('arena_layout');local origin={X=0,Y=0,Z=100};local forward={X=1,Y=0,Z=0}
local queries=0
local function flat(p)queries=queries+1;return{X=p.X,Y=p.Y,Z=0}end
local plan=assert(Layout.choose(flat,origin,forward,100,150,60,1))
assert(plan.boss.X==450 and plan.boss.Z==152 and #plan.targets==2 and queries==3)
assert(not Layout.choose(function()return nil end,origin,forward,100,150,60,1))
assert(not Layout.choose(function(p)return{X=p.X,Y=p.Y,Z=1000}end,origin,forward,100,150,60,1))
assert(not Layout.choose(function()return{X=450,Y=0,Z=0}end,origin,forward,100,150,60,1))
assert(not Layout.choose(function()return{X=0/0,Y=0,Z=0}end,origin,forward,100,150,60,1))
local plan2=assert(Layout.choose(flat,origin,forward,100,150,60,2));assert(math.abs(plan2.boss.Y-450)<0.001)
local large=assert(Layout.choose(flat,origin,forward,100,230,110,1))
for _,target in ipairs(large.targets)do
    assert((target.X-large.boss.X)^2+(target.Y-large.boss.Y)^2>=(2*110+40)^2)
end
assert(not pcall(Layout.choose,flat,origin,forward,100,230,257,1),'unsupported dimensions stay bounded')
local mixed=assert(Layout.choose(flat,origin,forward,100,230,110,1,nil,96,42))
assert(mixed.boss.Z==232 and mixed.targets[1].Z==98 and mixed.targets[2].Z==98,
    'each character must use its own verified capsule center height')
assert((mixed.targets[1].X-mixed.boss.X)^2+(mixed.targets[1].Y-mixed.boss.Y)^2>=(110+42+40)^2)
assert((mixed.targets[1].X-mixed.targets[2].X)^2+(mixed.targets[1].Y-mixed.targets[2].Y)^2>=(42+42+40)^2)
assert(not pcall(Layout.choose,flat,origin,forward,100,230,110,1,nil,96,257))
assert(Layout.visible(function()return true end,{},{{},{}}))
assert(not Layout.visible(function(_,target)return target.visible end,{},{{visible=true},{visible=false}}))
assert(not Layout.visible(function()error('unreadable')end,{},{{},{}}))
assert(not Layout.visible(function()return 'true'end,{},{{},{}}))
queries=0
assert(not Layout.choose(function(p)queries=queries+1;return{X=p.X+200,Y=p.Y,Z=0}end,origin,forward,100,150,60,1))
assert(queries<=72)
local next_plan=assert(Layout.choose(flat,origin,forward,100,150,60,1,{[plan.key]=true}))
assert(next_plan.key~=plan.key,'a rejected layout must not be retried')
local rejected={}
for direction=1,8 do rejected[direction..':1']=true end
local compact=assert(Layout.choose(flat,origin,forward,100,150,60,1,rejected))
assert(compact.key=='1:2'and compact.boss.X==350,'try bounded alternate formations')
print('Bounded local navigation layout rejects cliffs, overlaps, failed queries and invalid vectors')
