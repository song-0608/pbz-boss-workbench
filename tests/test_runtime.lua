-- 用途：验证真实运行调度代码的线程排队、生命周期和按键隔离；不启动游戏。
local root = assert(arg[1], "project directory required")
package.path = root .. "/mod/PBZBossControl/Scripts/?.lua;" .. package.path
local Runtime = require("runtime")
local count = 0
local function test(name, fn)
    local ok, why = pcall(fn); assert(ok, name .. ": " .. tostring(why))
    count = count + 1; print("PASS " .. name)
end
local function fixture()
    local f = { keys = {}, queue = {}, log = {}, reads = 0, movements = 0, restores = 0 }
    local b = {}
    function b:context()return { isolated=true,offline=true,exe_sha256="fixture",world_id="one",boss_available=true }end
    function b:capture()return {}end
    function b:take_control()return true end
    function b:verify_control()return true end
    function b:can_start_skill()return true end
    function b:start_skill()f.started=true;return "token"end
    function b:is_skill_finished()return true end
    function b:cancel_skills()return true end
    function b:restore()f.restores=f.restores+1;return true end
    function b:verify_restored()return true end
    function b:move()f.movements=f.movements+1;return true end
    function b:look()return true end
    f.host = {
        on_game_thread=function(fn)f.queue[#f.queue+1]=fn end,
        bind_key=function(key,fn)assert(not f.keys[key]);f.keys[key]=fn end,
        every_frame=function(fn)f.frame=fn;return 7 end,
        cancel_frame=function(handle)assert(handle==7);f.cancelled=true end,
        read_input=function()f.reads=f.reads+1;return {allowed=true,forward=true,yaw_degrees=0}end,
        log=function(message)f.log[#f.log+1]=message end,
    }
    f.config = { expected_exe_sha256="fixture",controls={enter="F6",exit="F10"},
        skills={ slot1={id="attack",key="F1",verified=true},slot2={key="F2",verified=false} } }
    f.bridge=b;f.runtime=Runtime.new(b,f.config,f.host)
    return f
end
test("only verified skill keys are registered",function()
    local f=fixture();assert(f.runtime:start());assert(f.keys.F6 and f.keys.F10 and f.keys.F1 and not f.keys.F2)
end)
test("enter is queued onto the game thread",function()
    local f=fixture();f.runtime:start();f.keys.F6();assert(f.runtime.session.state=="OFF")
    f.queue[1]();assert(f.runtime.session.state=="ACTIVE")
end)

test('queued repeated F10 restores once and reports one complete event',function()
    local f=fixture();f.runtime:start();f.keys.F6();f.queue[1]()
    f.keys.F10();f.keys.F10()
    for index=2,#f.queue do f.queue[index]()end
    assert(f.restores==1 and f.runtime.session.state=='OFF')
    local exits=0;for _,line in ipairs(f.log)do if line:find('exit success=true',1,true)then exits=exits+1 end end
    assert(exits==1)
end)
test("inactive frame does not read input",function()
    local f=fixture();f.runtime:start();f.frame();assert(f.reads==0 and f.movements==0)
end)
test('idle world watch runs while OFF and suspends old HUD while pending',function()
    local f=fixture();local checks,status=0,0
    f.host.inspect_idle_world=function()checks=checks+1;return false end
    f.host.status=function()status=status+1 end
    f.runtime:start();local before=status;f.frame()
    assert(checks==1 and status==before and f.reads==0)
    f.host.inspect_idle_world=function()error('ambiguous old object')end
    f.frame();assert(not f.runtime.running and f.cancelled and f.restores==0)
end)
test("active frame polls and drives movement",function()
    local f=fixture();f.runtime:start();f.keys.F6();f.queue[1]();f.frame();assert(f.reads==1 and f.movements==1)
end)
test("skill action dispatches configured slot",function()
    local f=fixture();f.runtime:start();f.keys.F6();f.queue[1]();f.keys.F1();f.queue[2]();assert(f.started)
end)
test("stop restores and invalidates queued actions",function()
    local f=fixture();f.runtime:start();f.keys.F6();f.queue[1]();f.keys.F1()
    assert(f.runtime:stop("shutdown"));f.queue[2]();f.frame()
    assert(f.cancelled and f.restores==1 and not f.started and f.reads==0)
end)
test("duplicate keys are rejected before registration",function()
    local f=fixture();f.config.controls.exit="F6";assert(not pcall(f.runtime.start,f.runtime));assert(next(f.keys)==nil)
end)
test("frame exception restores and reports failure",function()
    local f=fixture();f.runtime:start();f.keys.F6();f.queue[1]()
    f.runtime.driver.step=function()error("injected frame failure")end
    f.frame();assert(f.restores==1 and f.runtime.session.state=="OFF")
    assert(f.log[#f.log]:find("injected frame failure",1,true))
end)
test('automatic health exit is reported separately from the F10 callback',function()
    local f=fixture();f.runtime:start();f.keys.F6();f.queue[1]()
    function f.bridge:control_health()return false,'boss health depleted'end
    f.frame();assert(f.runtime.session.state=='OFF'and f.restores==1)
    assert(table.concat(f.log,'\n'):find('auto_exit success=true state=OFF reason=boss health depleted',1,true))
    for _,line in ipairs(f.log)do assert(not line:match('^exit success=true'))end
end)
test('Esc restores active session once and stays quiet when already OFF',function()
    local f=fixture();f.config.controls.menu_exit='ESCAPE';f.runtime:start()
    f.keys.F6();f.queue[1]();f.keys.ESCAPE();f.queue[2]()
    assert(f.restores==1 and f.runtime.session.state=='OFF')
    assert(table.concat(f.log,'\n'):find('menu_exit success=true state=OFF',1,true))
    local queued=#f.queue;f.keys.ESCAPE();assert(#f.queue==queued)
end)
test('optional F7 queues a target request on game thread',function()
    local f=fixture();f.config.controls.cycle_target='F7'
    function f.bridge:cycle_target()f.target_requested=true;return 'enemy-two'end
    f.runtime:start();f.keys.F6();f.queue[1]();f.keys.F7();assert(not f.target_requested)
    f.queue[2]();assert(f.target_requested and f.runtime.session.pending_target)
end)
test('target key conflict is rejected before registering any key',function()
    local f=fixture();f.config.controls.cycle_target='F1';assert(not pcall(f.runtime.start,f.runtime));assert(next(f.keys)==nil)
end)
test('lab candidate dispatch stays on game thread and cannot change mid-skill',function()
    local f=fixture();f.config.skills.lab_a={id='candidate_a',verified=true,lab_only=true}
    f.config.skills.lab_b={id='candidate_b',verified=true,lab_only=true}
    f.config.skill_lab={next_key='F9',cast_key='INS',slots={'lab_a','lab_b'}}
    function f.bridge:start_skill(_,id)f.skill_id=id;return 'lab-token'end
    f.runtime:start();assert(f.keys.F9 and f.keys.INS and not f.keys.F8)
    f.keys.F6();f.queue[1]();f.keys.F9();assert(f.runtime.lab:selected()=='lab_a')
    f.queue[2]();assert(f.runtime.lab:selected()=='lab_b');f.keys.INS();assert(not f.skill_id)
    f.queue[3]();assert(f.skill_id=='candidate_b');f.keys.F9();f.queue[4]();assert(f.runtime.lab:selected()=='lab_b')
end)
test('default config never registers developer candidate keys',function()
    local f=fixture();f.runtime:start();assert(not f.keys.F9 and not f.keys.INS and not f.runtime.lab)
end)

local function workbench_fixture()
    local f=fixture();f.config.controls.menu_exit='ESCAPE'
    local Workbench=require('boss_workbench');f.selected='one';f.locks=0;f.unlocks=0;f.switches=0
    local entries={{id='one',name='One',playable=true},{id='two',name='Two',playable=true},
        {id='pending',name='Pending',playable=false,reason='not accepted'}}
    f.host.workbench=Workbench.new({entries=function()return entries end,selected=function()return f.selected end})
    f.host.workbench:set_adapter({restore=function(reason)return f.runtime.session:restore(reason)end,
        lock=function()f.locks=f.locks+1;return true end,
        unlock=function()f.unlocks=f.unlocks+1;return true end,
        select=function(id)f.selected=id;f.switches=f.switches+1;return true end})
    function f.flush()while #f.queue>0 do table.remove(f.queue,1)()end end
    return f
end
test('F11 restores ACTIVE before opening and blocks queued skills and takeover',function()
    local f=workbench_fixture();f.runtime:start();f.keys.F6();f.flush()
    f.keys.INS();f.keys.F1();f.keys.F6();f.flush();f.frame()
    assert(f.runtime.session.state=='OFF'and f.restores==1 and f.locks==1)
    assert(f.host.workbench:is_open()and not f.started and f.reads==0)
end)
test('workbench routes arrows and Enter and serializes duplicate switch input',function()
    local f=workbench_fixture();f.runtime:start();f.keys.INS();f.flush()
    f.keys.DOWN_ARROW();f.keys.RETURN();f.keys.RETURN();f.flush()
    assert(f.selected=='two'and f.switches==1 and f.host.workbench.busy)
    f.keys.F6();f.keys.F1();f.flush();assert(f.runtime.session.state=='OFF'and not f.started)
end)
test('preview selection stays quarantined and F10 closes workbench while OFF',function()
    local f=workbench_fixture();f.runtime:start();f.keys.INS();f.flush()
    f.keys.DOWN_ARROW();f.keys.DOWN_ARROW();f.keys.RETURN();f.flush()
    assert(f.selected=='one'and f.switches==0 and f.host.workbench.opened)
    f.keys.F10();f.flush();assert(not f.host.workbench:is_open())
    f.keys.F6();f.flush();assert(f.runtime.session.state=='ACTIVE')
end)
test('Escape closes only workbench and stop invalidates pending workbench actions',function()
    local f=workbench_fixture();f.runtime:start();f.keys.INS();f.flush()
    f.keys.ESCAPE();f.flush();assert(not f.host.workbench:is_open())
    f.keys.INS();assert(f.runtime:stop('fixture teardown'));f.flush()
    assert(not f.host.workbench:is_open()and f.locks==1)
end)
test('workbench keys conflict before any native registration',function()
    local f=workbench_fixture();f.config.skills.slot1.key='INS'
    assert(not pcall(f.runtime.start,f.runtime)and next(f.keys)==nil)
end)
test('workbench stop refuses a false native cleanup result',function()
    local f=workbench_fixture();f.runtime:start()
    f.host.workbench.shutdown=function()return false,'input layer still present'end
    local ok,why=f.runtime:stop();assert(ok==false and why=='input layer still present')
end)
test('native key preflight rejects before any callback is registered',function()
    local f=workbench_fixture()
    f.host.validate_keys=function(keys)assert(keys.UP_ARROW and keys.DOWN_ARROW);error('missing native key fixture')end
    assert(not pcall(f.runtime.start,f.runtime)and next(f.keys)==nil and not f.runtime.running)
end)
print("Runtime fixtures: "..count.." passed; no PBZ runtime integration claimed.")
