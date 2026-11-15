local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Hud=require('player_hud')
local now,rendered=10,{}
local pc,boss,target={},{health=999},{health=123,name='敌人'}
local calls={optional=function(_,r)return r end,resolve=function(_,r)return r end}
local native={now=function()return now end,player_controller=function()return pc end,
    health=function(a)return a.health end,name=function(a)return a.name end,
    render=function(p,text,duration,key)assert(p==pc and duration>1 and key=='PBZBossControl.Status');rendered[#rendered+1]=text end}
local config={controls={enter='F6',exit='F10',cycle_target='F7'},skills={one={id='skill_01',name='技能01',key='F1',verified=true}}}
local hud=Hud.new(calls,native,config)
local session={state='OFF'}
assert(hud:update(session,true));assert(rendered[1]:find('F6',1,true))
assert(not hud:update(session,false));assert(#rendered==1)
session.state='ACTIVE';session.receipt={player_controller=pc,boss=boss,combat={selected_target=target}}
assert(hud:update(session,true));assert(rendered[2]:find('999',1,true)and rendered[2]:find('123',1,true))
session.current_skill='token';now=11;assert(hud:update(session,false));assert(rendered[3]:find('技能执行中',1,true))
for _,state in ipairs({'TRANSITIONING','FAULTED'})do session.state=state;assert(not hud:update(session,true))end
session.state='ACTIVE';target.health=0/0;assert(not pcall(hud.update,hud,session,true))
print('Player HUD rendering, live values, cadence, transition and invalid values passed')
