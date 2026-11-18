-- 用途：保留AI控制器的遥控链、输入屏蔽与独立恢复；不会启动游戏。
local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Remote=require('remote_control');local count=0
local function fixture(trial)
    local f={pc={},player={enabled=true},boss={},ai={tick=true,actor_tick=true,started=true},move_blocks=0,look_blocks=0,rotation={Pitch=0,Yaw=10,Roll=0}}
    f.pc.pawn=f.player;f.player.controller=f.pc;f.ai.pawn=f.boss;f.boss.controller=f.ai
    local calls={reference=function(_,x)return x end,resolve=function(_,x)return x end,same=function(_,a,b)return a==b end,
        pawn=function(_,x)return x.pawn end,controller=function(_,x)return x.controller end}
    local n={ai_started=function(ai)return ai.started end,set_ai_started=function(ai,on)ai.started=on end,
        ai_tick=function(ai)return ai.actor_tick end,set_ai_tick=function(ai,on)ai.actor_tick=on end,
        brain_tick=function(ai)return ai.tick end,set_brain_tick=function(ai,on)ai.tick=on end,
        snapshot=function()return{move_ignored=false,look_ignored=false,input_enabled=f.player.enabled,rotation={Pitch=0,Yaw=10,Roll=0}}end,
        block_move=function(_,on)f.move_blocks=f.move_blocks+(on and 1 or -1)end,
        block_look=function(_,on)if f.fail_look then f.fail_look=false;error('look block failed')end;f.look_blocks=f.look_blocks+(on and 1 or -1)end,
        disable_input=function(p)p.enabled=false end,enable_input=function(p)p.enabled=true end,
        input_enabled=function(p)return p.enabled end,move_ignored=function()return f.move_blocks>0 end,
        look_ignored=function()return f.look_blocks>0 end,rotation=function()return f.rotation end,
        set_rotation=function(_,r)f.rotation=r end,move=function(b,x,y,scale)assert(b==f.boss);f.moved={x=x,y=y,scale=scale}end}
    f.clock=100
    f.service=Remote.new(calls,n,{binding_verified=true,scheduler_trial=trial,now=function()return f.clock end});f.ticket=f.service:capture(f.pc,f.player,f.boss,f.ai);return f
end
local function test(name,fn)local ok,why=pcall(fn);assert(ok,name..': '..tostring(why));count=count+1;print('PASS '..name)end
test('AI and player ownership remain unchanged',function()local f=fixture();f.service:apply(f.ticket);assert(f.service:verify(f.ticket));assert(f.ai.pawn==f.boss and f.pc.pawn==f.player and not f.player.enabled)end)
test('movement goes to boss while original input is disabled',function()local f=fixture();f.service:apply(f.ticket);assert(f.service:move(f.ticket,1,0,1));assert(f.moved.x==1 and not f.player.enabled)end)
test('camera look changes rotation without original player input',function()local f=fixture();f.service:apply(f.ticket);f.service:look(f.ticket,5,-3);assert(f.rotation.Yaw==15 and f.rotation.Pitch==-3)end)
test('3C mouse bounds agree with the input sampler and legacy control stays narrow',function()
    local f=fixture();f.service:apply(f.ticket)
    assert(not pcall(f.service.look,f.service,f.ticket,20,0)and f.rotation.Yaw==10)
    f.service.locomotion={settings=require('player_3c_tuning').resolve('056_youlong')}
    assert(f.service:look(f.ticket,40,-40)and f.rotation.Yaw==50 and f.rotation.Pitch==-40)
    assert(not pcall(f.service.look,f.service,f.ticket,46,0)and f.rotation.Yaw==50)
    assert(not pcall(f.service.look,f.service,f.ticket,0/0,0)and f.rotation.Yaw==50)
    f.service.locomotion.settings.look_step_degrees=90
    assert(not pcall(f.service.look,f.service,f.ticket,20,0)and f.rotation.Yaw==50)
end)
test('exit balances only its own input blocks and restores rotation',function()local f=fixture();f.service:apply(f.ticket);f.service:look(f.ticket,2,1);assert(f.service:restore(f.ticket));assert(f.move_blocks==0 and f.look_blocks==0 and f.player.enabled and f.rotation.Yaw==10 and f.ticket.restored)end)
test('repeated restore does not decrement input blocks twice',function()local f=fixture();f.service:apply(f.ticket);f.service:restore(f.ticket);f.service:restore(f.ticket);assert(f.move_blocks==0 and f.look_blocks==0)end)
test('lost boss controller blocks movement',function()local f=fixture();f.service:apply(f.ticket);f.boss.controller=f.pc;assert(not pcall(function()f.service:move(f.ticket,1,0,1)end));assert(not f.moved)end)
test('unnormalized direction is rejected',function()local f=fixture();f.service:apply(f.ticket);assert(not pcall(function()f.service:move(f.ticket,2,0,1)end));assert(not f.moved)end)
test('game reenabled brain scheduling rejects movement',function()local f=fixture();f.service:apply(f.ticket);f.ai.tick=true;assert(not pcall(function()f.service:move(f.ticket,1,0,1)end));assert(not f.moved);f.service:restore(f.ticket);assert(f.ai.tick and f.ai.actor_tick)end)
test('owned brain pause can be reasserted then restored to original',function()
    local f=fixture();f.service:apply(f.ticket);f.ai.tick=true;assert(f.service:maintain(f.ticket))
    assert(not f.ai.tick and f.ticket.brain_reassertions==1);f.service:restore(f.ticket);assert(f.ai.tick)
    assert(not pcall(f.service.maintain,f.service,f.ticket))
end)
test('other controller or input changes forbid maintenance writes',function()
    local f=fixture();f.service:apply(f.ticket);f.ai.tick=true;f.boss.controller=f.pc
    assert(not f.service:maintain(f.ticket));assert(f.ai.tick and not f.ticket.brain_reassertions)
    f.boss.controller=f.ai;f.move_blocks=0;assert(not f.service:maintain(f.ticket));assert(f.ai.tick)
end)
test('repeated game conflict exhausts bounded maintenance budget',function()
    local f=fixture();f.service:apply(f.ticket)
    for _=1,8 do f.ai.tick=true;assert(f.service:maintain(f.ticket))end
    f.ai.tick=true;assert(not pcall(f.service.maintain,f.service,f.ticket));assert(f.ai.tick)
end)
test('default remote refuses scheduler without writing brain',function()
    local f=fixture();f.service:apply(f.ticket)
    assert(not pcall(f.service.begin_scheduler,f.service,f.ticket,'attack_01',25));assert(not f.ai.tick and not f.ticket.scheduler)
end)
test('explicit scheduler permits real brain ticks while retaining all other invariants',function()
    local f=fixture(true);f.service:apply(f.ticket);f.service:begin_scheduler(f.ticket,'attack_01',25)
    assert(f.ai.tick and not f.service:brain_suspended(f.ticket)and f.service:verify(f.ticket))
    assert(f.service:maintain(f.ticket)and f.ai.tick and not f.ai.started and not f.ai.actor_tick)
    f.ai.tick=false;assert(f.service:maintain(f.ticket)and not f.ai.tick)
    f.boss.controller=f.pc;assert(not f.service:maintain(f.ticket));assert(not f.service:verify(f.ticket))
end)
test('expired scheduler cannot keep control or renew itself',function()
    local f=fixture(true);f.service:apply(f.ticket);f.service:begin_scheduler(f.ticket,'attack_01',25)
    f.clock=125;assert(not f.service:verify(f.ticket));assert(not f.service:maintain(f.ticket))
    assert(not pcall(f.service.begin_scheduler,f.service,f.ticket,'attack_01',25))
    f.service:end_scheduler(f.ticket);assert(not f.ai.tick and not f.ticket.scheduler)
    assert(f.service:restore(f.ticket)and f.ai.tick and f.player.enabled)
end)
test('wrong skill and unbounded lease cannot enable scheduler',function()
    local f=fixture(true);f.service:apply(f.ticket)
    assert(not pcall(f.service.begin_scheduler,f.service,f.ticket,'other',25))
    assert(not pcall(f.service.begin_scheduler,f.service,f.ticket,'attack_01',26));assert(not f.ai.tick)
end)
print('Remote control fixtures: '..count..' passed; runtime verification separate.')
