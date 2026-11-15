local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Native=require('ue_arena_layout');local pc={};local calls=0
local library={}
function library:GetNavigationSystem(context)assert(context==pc);return{IsValid=function()return true end}end
function library:K2_ProjectPointToNavigation(context,point,out,nav,filter,extent)
    assert(context==pc and nav==nil and filter==nil and extent.Z==250)
    calls=calls+1
    if point.X<0 then return false end
    out.X=point.X;out.Y=point.Y;out.Z=10;return true
end
local g={StaticFindObject=function(path)
    assert(path=='/Script/NavigationSystem.NavigationSystemV1')
    return{IsValid=function()return true end,GetCDO=function()return library end}
end}
assert(not pcall(Native.new,g,{binding_verified=false},pc))
local project=Native.new(g,{binding_verified=true},pc)
assert(project({X=20,Y=30,Z=40}).Z==10)
assert(project({X=-1,Y=0,Z=0})==nil and calls==2)
library.K2_ProjectPointToNavigation=function()return 'true'end
assert(not pcall(project,{X=0,Y=0,Z=0}))
print('Navigation wrapper uses verified context and mutable vector output; rejects missing projections and unreadable booleans')
