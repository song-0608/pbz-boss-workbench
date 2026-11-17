local root,candidate=assert(arg[1]),assert(arg[2])
package.path=candidate..'/PBZBossControl/Scripts/?.lua;'..package.path
local Catalog=require('boss_catalog')
local roles,primaries=0,0
for _,row in ipairs(Catalog.list())do
    local profile=Catalog.profile(row.id)
    local config=Catalog.configure(row.id,profile)
    roles=roles+1
    if row.id=='071_xianzhe'then
        assert(not config.skills.primary_attack,'dodge-only role must not advertise an attack')
    else
        local primary=assert(config.skills.primary_attack,'missing primary shortcut: '..row.id)
        assert(primary.key=='LEFT_MOUSE_BUTTON'and profile.skills[primary.id].gameplay_verified)
        if row.id~='ahua_guitoudao'then
            local d=profile.skills[primary.id];d.gameplay_verified=false
            assert(not pcall(Catalog.configure,row.id,profile),'movement-only action cannot become primary attack')
            d.gameplay_verified=true
        end
        primaries=primaries+1
        Catalog.configure(row.id,profile,{controls={},skills={primary_attack='RIGHT_MOUSE_BUTTON'}})
    end
end
assert(roles==6 and primaries==5)
local Calls=require('ue_calls')
local scans,alive,usable,address,name=0,true,true,1,'Object /Fixture'
local object={IsValid=function()return alive end,GetAddress=function()return address end,
    GetFullName=function()return name end,GetClass=function()return{GetFullName=function()return'Class /Fixture.Kind'end}end}
local calls=Calls.new({find_exact=function()scans=scans+1;return object end,usable=function()return usable end})
local ref={name=name,address=address,class='Class /Fixture.Kind'}
for i=1,1000 do assert(calls:resolve(ref)==object)end
assert(scans==1,'repeated live access must not rescan the global object array')
name='Object /Reused';assert(not pcall(calls.resolve,calls,ref),'cached identity reuse must fail closed');name=ref.name
usable=false;assert(calls:optional(ref)==nil);usable=true
assert(calls:resolve(ref)==object and scans==2,'engine-invalid cache entry must be evicted')
alive=false;assert(calls:optional(ref)==nil);alive=true

local class_scans=0
calls=Calls.new({find_exact=function()return nil end,find_all=function(class)
    class_scans=class_scans+1;assert(class=='Kind');return{}end})
local old={world={name='Object /World',address=11,class='Class /Fixture.Kind'},
    player_controller={name='Object /PC',address=12,class='Class /Fixture.Kind'},owned_world_objects={}}
for i=1,15 do old.owned_world_objects[i]={name='Object /Old'..i,address=100+i,class='Class /Fixture.Kind'}end
assert(require('world_boundary').inspect(calls,old)=='retired'and class_scans==1,
    'one retirement census per class, not per missing object')

local now,queries=10,0
local current={name='World /New',address=20,class='Class World'}
local watch=require('idle_world_watch').new({optional=function()queries=queries+1;error('old actor access')end},
    old,function()return now end,function()return current end)
assert(watch:poll('OFF')=='changed'and queries==0 and not watch.finished,
    'new World with old objects alive must request cleanup, never fake retirement')
assert(watch:poll('OFF')=='changed'and queries==0)
now=11;current=nil;assert(watch:poll('OFF')=='pending'and queries==0)

local events={}
local session={state='OFF'}
local runtime={running=true,session=session,report=function()events[#events+1]='report'end}
local guard=require('map_travel_guard').new({runtime=function()return runtime end,attest=function()end,
    same_world=function()return true end,log=function(k)events[#events+1]=k end,
    retire_idle=function(_,r)assert(r.session.state=='OFF'and not r.session.receipt);events[#events+1]='cleanup'end})
guard:before({});assert(#events==1 and events[1]=='cleanup','F10/Esc travel must clean idle assembly')
events={};session.state='ACTIVE';session.receipt={world={name='World /Old',address=11}}
function session:restore()events[#events+1]='restore';self.state='OFF';self.receipt=nil;return true end
guard:before({});assert(events[2]=='restore'and events[#events]=='cleanup')
events={};session.state='FAULTED';assert(not pcall(guard.before,guard,{}));assert(#events==0)

-- The menu fallback must not replace bare takeover or accumulate closures.
local previous_input=package.loaded.ue_input
package.loaded.ue_input={new=function()return{read=function()return{}end}end}
local callbacks,registered,queue={},{},{}
local g={EngineTickAvailable=true,Key={F6=117},ModifierKey={SHIFT=16},
    LoopInGameThreadAfterFrames=function()return 1 end,CancelDelayedAction=function()end,
    ExecuteInGameThread=function(fn)queue[#queue+1]=fn end,FName=function(value)return value end,
    StaticFindObject=function()return{IsValid=function()return true end}end,print=function()end}
g.RegisterKeyBind=function(key,modifiers,fn)
    if type(modifiers)=='function'then fn=modifiers;modifiers={}end
    local id=tostring(key)..':'..table.concat(modifiers,',')
    assert(not callbacks[id],'native menu route duplicated');callbacks[id]=fn;registered[#registered+1]=id
end
local Host=require('ue_host')
local h=Host.new({}, {},g);h.validate_menu_alias('F6')
local bare,old_menu,new_menu=0,0,0
h.bind_key('F6',function()bare=bare+1 end)
h.bind_menu_alias('F6',function()old_menu=old_menu+1 end)
callbacks['117:16']();assert(old_menu==1 and bare==0)
callbacks['117:']();assert(bare==1)
local replacement=Host.new({}, {},g)
replacement.bind_menu_alias('F6',function()new_menu=new_menu+1 end)
h.release_keys();callbacks['117:16']()
assert(old_menu==1 and new_menu==1 and #registered==2,'reassembly must update only current menu owner')
replacement.release_keys();callbacks['117:16']();assert(new_menu==1)
package.loaded.ue_input=previous_input
local keys,game_queue={},{}
local b={context=function()return{isolated=true,offline=true,exe_sha256='fixture',world_id='one',boss_available=true}end,
    capture=function()return{}end,take_control=function()return true end,verify_control=function()return true end,
    can_start_skill=function()return true end,start_skill=function()return'token'end,is_skill_finished=function()return true end,
    move=function()return true end,look=function()return true end,
    cancel_skills=function()return true end,restore=function()return true end,verify_restored=function()return true end}
local menu={opened=false,busy=false}
function menu:is_open()return self.opened end
function menu:toggle()
    if not self.opened then assert(self.runtime.session:restore('open workbench'))end
    self.opened=not self.opened;return true
end
function menu:open()if not self.opened then return self:toggle()end;return true end
function menu:close()self.opened=false;return true end
function menu:confirm()return self:close()end
local runtime_host={workbench=menu,on_game_thread=function(fn)game_queue[#game_queue+1]=fn end,
    bind_key=function(key,fn)assert(not keys[key]);keys[key]=fn end,every_frame=function()return 1 end,
    cancel_frame=function()end,read_input=function()return{}end,log=function()end}
local r=require('runtime').new(b,{expected_exe_sha256='fixture',controls={enter='F6',exit='F10'},skills={}},runtime_host)
menu.runtime=r;r:start()
local function flush()while #game_queue>0 do table.remove(game_queue,1)()end end
keys.F6();flush();assert(r.session.state=='ACTIVE'and not menu.opened)
keys.F6();flush();assert(r.session.state=='OFF'and menu.opened,'active takeover key must restore and open chooser')
keys.F6();flush();assert(r.session.state=='OFF'and not menu.opened,'same-role confirmation must close without reentering')
-- Releasing a stuck or unreadable key must cancel the timer, reject the menu
-- action and release its pending flag without interpreting failure as key-up.
local saved_input=package.loaded.ue_input
package.loaded.ue_input={new=function()return{read=function()return{}end}end}
local timers,serial={},0
local held,read_error=true,false
local release_globals={EngineTickAvailable=true,Key={},print=function()end,
    StaticFindObject=function()return{IsValid=function()return true end}end,
    ExecuteInGameThread=function(fn)fn()end,RegisterKeyBind=function()end,FName=function(k)return k end,
    LoopInGameThreadAfterFrames=function(_,fn)serial=serial+1;timers[serial]=fn;return serial end,
    CancelDelayedAction=function(id)timers[id]=nil end}
local release_bridge={player_controller=function()
    if read_error then error('World loading')end
    return{IsInputKeyDown=function()return held end}
end}
local release_host=Host.new(release_bridge,{},release_globals)
local ran,rejected=0,0
local function success()ran=ran+1 end
local function reject()rejected=rejected+1 end
local handle=release_host.after_key_release('INS',success,reject)
local callback=timers[handle]
for _=1,180 do callback()end
assert(not timers[handle]and ran==0 and rejected==1,'held key wait must stop without invoking action')
held=false;callback();assert(ran==0 and rejected==1,'a stale timed-out callback must be inert')
handle=release_host.after_key_release('INS',success,reject)
callback=timers[handle];read_error=true;callback();callback()
assert(not timers[handle]and ran==0 and rejected==2,'World/loading exception must cancel release wait')
read_error=false
handle=release_host.after_key_release('INS',success,reject)
callback=timers[handle];release_host.release_keys();callback();callback()
assert(ran==0 and rejected==2,'callbacks queued before host release must be inert')
local rejection
runtime_host.after_key_release=function(_,_,failure)rejection=failure end
r:workbench_action('workbench_close','ESCAPE',success)
assert(r.workbench_action_pending and rejection)
rejection('key state unavailable')
assert(not r.workbench_action_pending and ran==0,'failed key wait must release the pending menu action')
r:workbench_action('workbench_close','ESCAPE',success)
assert(r.workbench_action_pending,'a later release attempt remains possible after rejection')
rejection('test cleanup')
package.loaded.ue_input=saved_input
print('PASS five accepted damage shortcuts; live identity cache; bounded retirement census; current World change; idle/active travel cleanup')
print('PASS Shift+takeover menu fallback preserves bare key and releases old assembly routes')
print('PASS repeated takeover key restores ACTIVE and opens/confirms chooser without timing or extra key dependency')
print('PASS key release timeout, World exception and retired callbacks reject safely and unlock the pending menu queue')
