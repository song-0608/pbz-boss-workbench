-- Real role catalog -> real native-key router -> Runtime -> Session, with an
-- injected game adapter. This proves dispatch, not engine activation or damage.
local root,candidate=assert(arg[1]),assert(arg[2])
package.path=candidate..'/PBZBossControl/Scripts/?.lua;'..package.path
local saved_input=package.loaded.ue_input
package.loaded.ue_input={new=function(bridge)return{read=function()return bridge.input end}end}
local Host=require('ue_host');local Runtime=require('runtime');local Catalog=require('boss_catalog')
local events,queue,frames={},{},{};local serial,registrations=0,0
local g={EngineTickAvailable=true,Key={},ModifierKey={SHIFT=16},print=function()end,FName=function(value)return value end,
    StaticFindObject=function()return{IsValid=function()return true end}end,
    ExecuteInGameThread=function(fn)queue[#queue+1]=fn end,
    LoopInGameThreadAfterFrames=function(_,fn)serial=serial+1;frames[serial]=fn;return serial end,
    CancelDelayedAction=function(handle)frames[handle]=nil end}
g.RegisterKeyBind=function(key,modifiers,fn)
    if type(modifiers)=='function'then fn=modifiers;modifiers={}end
    local chord=tostring(key)..':'..table.concat(modifiers,',')
    assert(not events[chord],'same-process reassembly must not accumulate native callbacks')
    events[chord]=fn;registrations=registrations+1
end
local roles=Catalog.list()
local function register_key(key)if not g.Key[key]then g.Key[key]=key end end
for _,role in ipairs(roles)do
    local profile=Catalog.profile(role.id)
    local config=Catalog.configure(role.id,profile)
    for _,key in pairs(config.controls)do register_key(key)end
    for _,definition in pairs(config.skills)do register_key(definition.key)end
end
local function press(key,shift)
    local fn=events[tostring(g.Key[key])..':'..(shift and'16'or'')]
    if fn then fn()end
end
local function flush()while #queue>0 do table.remove(queue,1)()end end
local function setup(role)
    local f={id=role.id,casts={},moves=0,finished=false,input={allowed=true,forward=true,yaw_degrees=0}}
    local profile=Catalog.profile(role.id);local config=Catalog.configure(role.id,profile)
    f.config=config
    local b={input=f.input,context=function()return{isolated=true,offline=true,
        exe_sha256=config.expected_exe_sha256,world_id='fixture-world',boss_available=true}end,
        capture=function()return{role=role.id}end,take_control=function()return true end,
        verify_control=function()return true end,can_start_skill=function()return true end,
        start_skill=function(_,receipt,id)
            assert(receipt.role==f.id and profile.skills[id],'attack must use the current role profile')
            f.casts[#f.casts+1]=id;return'token-'..#f.casts
        end,is_skill_finished=function()return f.finished end,cancel_skills=function()return true end,
        restore=function()return true end,verify_restored=function()return true end,
        move=function()f.moves=f.moves+1;return true end,look=function()return true end}
    f.host=Host.new(b,{},g);f.host.action_time=function()return 100 end
    f.runtime=Runtime.new(b,config,f.host);f.runtime:start()
    return f
end
local previous,first_cycle,attacking,nonattacking
attacking,nonattacking=0,0
for cycle=1,3 do
    for _,role in ipairs(roles)do
        -- Prepare the replacement before retiring its predecessor: old route
        -- cleanup must preserve the new owner's callbacks.
        if previous and previous.config.skills.primary_attack then
            press('LEFT_MOUSE_BUTTON') -- leave old input queued across replacement
        end
        local old=previous;local f=setup(role)
        if old then
            local before=#old.casts;assert(old.runtime:stop('role replacement'));flush()
            assert(#old.casts==before,'queued old-role primary must be inert after replacement')
        end
        press('LEFT_MOUSE_BUTTON');flush();assert(#f.casts==0,'OFF must not accept attack')
        press('F6');flush();assert(f.runtime.session.state=='ACTIVE')
        frames[f.runtime.frame_handle]();assert(f.moves==1,'movement must run before primary')
        local primary=f.config.skills.primary_attack
        press('LEFT_MOUSE_BUTTON');flush()
        if primary then
            assert(#f.casts==1 and f.casts[1]==primary.id,'left click must reach the selected real catalog slot: '..role.id)
            press('LEFT_MOUSE_BUTTON',true);flush();assert(#f.casts==1,'running native action stays exclusive')
            f.finished=true;press('LEFT_MOUSE_BUTTON',true);flush()
            assert(#f.casts==2 and f.casts[2]==primary.id,'Shift+left click must use the same current role action')
            if cycle==1 then attacking=attacking+1 end
        else
            assert(role.id=='071_xianzhe'and #f.casts==0,'dodge-only role cannot inherit the previous attack route')
            press('LEFT_MOUSE_BUTTON',true);flush();assert(#f.casts==0)
            if cycle==1 then nonattacking=nonattacking+1 end
        end
        press('F10');flush();assert(f.runtime.session.state=='OFF')
        local before=#f.casts;press('LEFT_MOUSE_BUTTON');press('LEFT_MOUSE_BUTTON',true);flush()
        assert(#f.casts==before,'restore must block bare and Shift primary attacks')
        previous=f
    end
    if cycle==1 then first_cycle=registrations else assert(registrations==first_cycle,'native registrations must remain bounded across roster cycles')end
end
assert(attacking==5 and nonattacking==1)
assert(previous.runtime:stop('fixture end'));assert(next(frames)==nil)
local before=#queue;for _,callback in pairs(events)do callback()end
assert(#queue==before,'retired hosts must not leave active native routes')
package.loaded.ue_input=saved_input

local Controls=require('player_role_controls')
local fields={'binding_verified','activation_runtime_verified','natural_completion_verified','cancellation_runtime_verified','gameplay_verified'}
for _,field in ipairs(fields)do
    for _,value in ipairs({false,1,'true'})do
        local definition={name='fixture'};for _,key in ipairs(fields)do definition[key]=true end
        definition[field]=value
        local config={skills={}}
        assert(not pcall(Controls.apply,config,{id='057_wanjun',skills={skill_01=definition}})
            and not config.skills.primary_attack,'non-boolean evidence cannot enable a primary shortcut: '..field)
    end
end
print('PASS five primary routes and one dodge-only role across three full roster cycles, bare/Shift input, movement, restore and stale owner cleanup')
print('PASS bounded native callbacks and strict primary evidence; no engine ability activation or damage claimed')
