local root,candidate=assert(arg[1]),assert(arg[2]);package.path=candidate..'/PBZBossControl/Scripts/?.lua;'..package.path
local Runtime=require('runtime')
local function fixture()
    local f={keys={},queue={},logs={},casts=0,moves=0,restores=0,finished=false}
    local bridge={}
    function bridge:context()return{isolated=true,offline=true,exe_sha256='fixture',world_id='one',boss_available=true}end
    function bridge:capture()return{}end;function bridge:take_control()return true end
    function bridge:verify_control()return true end;function bridge:can_start_skill()return true end
    function bridge:start_skill()f.casts=f.casts+1;return'cast-'..f.casts end
    function bridge:is_skill_finished()return f.finished end
    function bridge:cancel_skills()return true end
    function bridge:restore()f.restores=f.restores+1;return true end
    function bridge:verify_restored()return true end
    function bridge:move()f.moves=f.moves+1;return true end
    function bridge:look()return true end
    function bridge:toggle_target_lock()f.locked=not f.locked;return true end
    local function bind(key,fn)assert(not f.keys[key]);f.keys[key]=fn end
    local host={on_game_thread=function(fn)f.queue[#f.queue+1]=fn end,bind_key=bind,
        bind_gameplay_key=function(key,fn)f.gameplay=f.gameplay or{};f.gameplay[key]=true;bind(key,fn)end,
        every_frame=function(fn)f.frame=fn;return 1 end,cancel_frame=function()end,
        read_input=function()return{allowed=true,forward=true,right=true,yaw_degrees=0}end,
        log=function(line)f.logs[#f.logs+1]=line end}
    local config={expected_exe_sha256='fixture',controls={enter='F6',exit='F10',lock_target='MIDDLE_MOUSE_BUTTON'},
        skills={slot1={id='skill_01',key='F1',verified=true}}}
    f.runtime=Runtime.new(bridge,config,host)
    function f.flush()while #f.queue>0 do table.remove(f.queue,1)()end end
    f.runtime:start();f.keys.F6();f.flush();return f
end
local f=fixture();assert(f.gameplay.F1 and f.gameplay.MIDDLE_MOUSE_BUTTON and not f.gameplay.F6)
f.frame();assert(f.moves==1)
f.keys.F1();f.flush();assert(f.casts==1)
f.frame();assert(f.moves==1,'held movement must not compete with running skill')
f.keys.F1();f.flush();assert(f.casts==1,'running native skill remains exclusive')
f.finished=true;f.keys.F1();f.flush();assert(f.casts==2,'fresh completion readback must allow next skill before next frame')
f.frame();assert(f.moves==2,'held movement resumes after native completion')
f.keys.MIDDLE_MOUSE_BUTTON();f.flush();assert(f.locked)
f.keys.F10();f.flush();assert(f.restores==1 and f.runtime.session.state=='OFF')
f.keys.F1();f.keys.MIDDLE_MOUSE_BUTTON();f.flush();assert(f.casts==2 and f.locked)
print('PASS moving cast, native activity exclusion, fresh completion, lock key and restore gates')
