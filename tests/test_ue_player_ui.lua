local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local output={}
local g={print=function(text)output[#output+1]=text end}
local pc={GetFullName=function()return'PC /Fixture.PC'end}
local expires=os.time()+100
local ui=require('ue_player_ui').new(g,{binding_verified=true},function()return{offline=true,isolated=true,expires_at=expires,session_id='fixture'}end)
local location={X=10,Y=20,Z=30}
local controller={IsValid=function()return true end,K2_GetActorLocation=function()return location end,
    LineOfSightTo=function(_,target,point)return point.X~=0 end}
local boss={GetController=function()return controller end,GetFullName=function()return'Boss /Fixture.B'end,
    K2_GetActorLocation=function()return location end}
local target={GetFullName=function()return'Boss /Fixture.T'end,K2_GetActorLocation=function()return location end}
assert(ui.visible(boss,target)==false,'diagnostic alternate visibility must never override default query')
assert(#output==1 and output[1]:find('default=false|boss_center=true',1,true))
assert(ui.visible(boss,target)==false and #output==1,'unchanged visibility diagnostics must be bounded')
output={}
ui.render(pc,'line1\n"line2"\\')
assert(#output==1 and output[1]:find('line1\\u000a\\"line2\\"\\\\',1,true))
assert(output[1]:find('"session":"fixture"',1,true))
expires=0;assert(not pcall(ui.render,pc,'expired'))
ui.close();assert(not pcall(ui.render,pc,'closed'))
print('Exact JSON status escaping, active lease and close guard passed')
