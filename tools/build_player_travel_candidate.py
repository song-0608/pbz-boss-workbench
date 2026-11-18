"""Build the primary-input / World-lifetime repair without editing an accepted release."""
import argparse
import hashlib
import json
from pathlib import Path

from boss_adaptation_workflow import ROOT, sha, write_json
from build_player_experience_candidate import replace
from mod_installation import MANIFEST, assert_closed, unlinked_path, validate_package

BASE = 'ahua-boss-workbench-v5-3f29975fe3b8826f'
PREFIX = 'PBZBossControl/Scripts/'
SOURCES = ('tools/build_player_travel_candidate.py', 'tools/player_role_controls.lua',
           'tools/player_world_watch.lua', 'tools/player_native_travel_trial.lua', 'tools/player_controller_query.lua',
           'tests/test_player_travel_repair.lua', 'tests/test_player_controller_query.lua',
           'tests/test_player_travel_candidate.py', 'tools/player_overlay.py', 'tests/test_player_overlay.py',
           'tools/player_reassembly.lua', 'tests/test_player_reassembly.lua', 'tests/test_player_native_travel_trial.lua',
           'tools/player_assembly_tasks.lua', 'tests/test_player_assembly_tasks.lua', 'tests/test_player_retirement_budget.lua',
           'tools/player_map_lifecycle.lua', 'tools/player_map_lifecycle_binding.lua', 'tests/test_player_map_lifecycle.lua',
           'tests/test_player_map_initialization.lua', 'tests/test_player_target_diagnostics.lua',
           'tools/player_controller_owner.lua', 'tests/test_player_controller_owner.lua',
           'tools/inspect_player_controller_contract.py', 'tools/check_player_travel_repair.py',
           'tests/test_player_source_checks.py')


def payload(root=ROOT):
    base = root / 'releases' / BASE
    manifest = validate_package(base)
    proof = root / manifest['acceptance_report']
    assert sha(proof) == manifest['acceptance_report_sha256']
    assert json.loads(proof.read_bytes())['passed']
    files = {name: (base / name).read_bytes() for name in manifest['files']}
    def change(name, before, after):
        key = PREFIX + name
        files[key] = replace(files[key].decode('utf-8').replace('\r\n', '\n'), before, after).encode('utf-8')

    files[PREFIX + 'player_role_controls.lua'] = (root / 'tools/player_role_controls.lua').read_bytes()
    files[PREFIX + 'idle_world_watch.lua'] = (root / 'tools/player_world_watch.lua').read_bytes()
    files[PREFIX + 'player_native_travel_trial.lua'] = (root / 'tools/player_native_travel_trial.lua').read_bytes()
    files[PREFIX + 'player_controller_query.lua'] = (root / 'tools/player_controller_query.lua').read_bytes()
    files[PREFIX + 'player_controller_owner.lua'] = (root / 'tools/player_controller_owner.lua').read_bytes()
    files[PREFIX + 'player_reassembly.lua'] = (root / 'tools/player_reassembly.lua').read_bytes()
    files[PREFIX + 'player_assembly_tasks.lua'] = (root / 'tools/player_assembly_tasks.lua').read_bytes()
    files[PREFIX + 'player_map_lifecycle.lua'] = (root / 'tools/player_map_lifecycle.lua').read_bytes()
    original_bridge = files[PREFIX + 'control_bridge.lua'].decode('utf-8').replace('\r\n', '\n')
    begin = original_bridge.index('function Bridge:player_controller()\n')
    end = original_bridge.index('\nfunction Bridge:world_id(', begin)
    change('control_bridge.lua', original_bridge[begin:end],
           'function Bridge:player_controller()\n'
           "    self.controller_query=self.controller_query or require('player_controller_query').new(self.calls,self.api,true)\n"
           '    local pc,count=self.controller_query:get()\n'
           '    assert(count==1 and pc,"exactly one local gameplay controller required")\n'
           '    return pc\nend\n')

    # Use the process engine's current viewport/local player, including during
    # readiness. Do not sweep the global object array once a second in gameplay.
    change('owned_arena.lua', 'local gate_started,stationary_polls=0,0',
           "local readiness_query=require('player_controller_query').new(\n"
           "    require('ue_calls').new({find_exact=StaticFindObject,usable=valid}),\n"
           '    {find_all=FindAllOf,now=os.time,usable=valid},true)\n'
           'local gate_started,stationary_polls=0,0')
    change('owned_arena.lua', "        local player,count=nil,0\n"
           "        for _,pc in ipairs(FindAllOf('PBZPlayerController')or{})do\n"
           "            if valid(pc)and valid(pc.Pawn)and pc:GetFullName():find(':PersistentLevel.',1,true)then player=pc.Pawn;count=count+1 end\n"
           '        end',
           '        local ready_pc,count=readiness_query:get()\n'
           '        local player=ready_pc and ready_pc.Pawn')
    change('owned_arena.lua', '        local pc\n'
           '        for _,candidate in ipairs(FindAllOf("PBZPlayerController") or {})do\n'
           '            if valid(candidate) and valid(candidate.Pawn) and candidate:GetFullName():find(":PersistentLevel.",1,true)then\n'
           '                assert(not pc,"ambiguous player controller");pc=candidate\n'
           '            end\n        end\n'
           '        assert(pc,"local gameplay player missing")',
           '        local pc,count=readiness_query:get()\n'
           '        assert(count==1 and pc,"unique current gameplay player required")')

    # A swallowed timer exception or a key held across travel must not leave a
    # permanent callback and a permanently locked menu queue.
    change('ue_host.lua', '        after_key_release = function(key,fn)',
           '        after_key_release = function(key,fn,rejected)')
    change('ue_host.lua', '                if finished then return end\n                frames=frames+1',
           '                if finished or not pending_releases[handle]then return end\n                frames=frames+1')
    change('ue_host.lua', '            local frames,handle,finished=0,nil,false',
           '            local frames,handle,finished=0,nil,false\n'
           '            local started_at=os.time()\n'
           '            local function finish(problem)\n'
           '                if finished then return end\n'
           '                finished=true;g.CancelDelayedAction(handle);pending_releases[handle]=nil\n'
           '                if problem then\n'
           '                    if rejected then rejected(problem)end\n'
           '                else fn()end\n'
           '            end')
    change('ue_host.lua', '                local pc=bridge:player_controller()\n'
           "                if pc:IsInputKeyDown({KeyName=g.FName(names[key]or key)})then return end\n"
           '                -- The delayed-action API ignores callback return values. Cancel explicitly\n'
           '                -- before invoking an action which may replace or stop this host.\n'
           '                finished=true\n'
           '                g.CancelDelayedAction(handle)\n'
           '                pending_releases[handle]=nil\n'
           '                fn()',
           '                if frames>=180 or os.time()-started_at>=3 then\n'
           "                    finish('key release not observed within bounded wait');return\n"
           '                end\n'
           '                local ok,held=pcall(function()\n'
           '                    local pc=bridge:player_controller()\n'
           '                    return pc:IsInputKeyDown({KeyName=g.FName(names[key]or key)})\n'
           '                end)\n'
           '                if not ok then finish(held);return end\n'
           "                if type(held)~='boolean'then finish('key state unreadable');return end\n"
           '                if not held then finish()end')
    change('runtime.lua', '    self.host.after_key_release(key,function()\n'
           '        self.workbench_action_pending=false\n'
           '        if self.running then self:action(label,fn)end\n'
           '    end)',
           '    local function rejected(problem)\n'
           '        self.workbench_action_pending=false\n'
           "        if self.running then self:report('workbench_release',false,problem)end\n"
           '    end\n'
           '    local ok,why=pcall(self.host.after_key_release,key,function()\n'
           '        self.workbench_action_pending=false\n'
           '        if self.running then self:action(label,fn)end\n'
           '    end,rejected)\n'
           '    if not ok then rejected(why)end')
    change('boss_catalog.lua', '    if keymap then require(\'keymap\').apply(config,keymap)end',
           "    require('player_role_controls').apply(config,profile)\n"
           "    if keymap then require('keymap').apply(config,keymap)end")
    for name in ('wanjun', 'yanqiansui', 'youlong'):
        change('boss_catalog.lua', "bindings='profiles." + name + "_bindings',abilities=8,bindings_count=8",
               "bindings='profiles." + name + "_bindings',abilities=8,bindings_count=9")
    change('boss_catalog.lua', '["bindings"]="profiles.maddoctor_bindings",["abilities"]=4,["bindings_count"]=4',
           '["bindings"]="profiles.maddoctor_bindings",["abilities"]=4,["bindings_count"]=5')

    # Insert is not delivered on every keyboard/window setup. A modifier chord on
    # the already working takeover key provides a second native, focus-scoped
    # route. It shares the ordinary restore/lock/release path and never polls OS
    # input or binds F11/F12, which belong to window and developer controls.
    change('ue_host.lua', '        bind_gameplay_key = function(key,fn) gameplay:bind(key,fn) end,',
           "        validate_menu_alias = function(key)\n"
           "            assert(g.Key[key] and g.ModifierKey and g.ModifierKey.SHIFT,'native menu chord unavailable')\n"
           '        end,\n'
           '        bind_menu_alias = function(key,fn)\n'
           "            local id='shift:'..tostring(g.Key[key])\n"
           '            if not router.registered[id]then\n'
           '                g.RegisterKeyBind(g.Key[key],{g.ModifierKey.SHIFT},function()\n'
           '                    local route=router.routes[id];if route then route.fn()end\n'
           '                end)\n'
           '                router.registered[id]=true\n'
           '            end\n'
           '            router.routes[id]={owner=owner,fn=fn}\n'
           '        end,\n'
           '        bind_gameplay_key = function(key,fn) gameplay:bind(key,fn) end,')
    change('runtime.lua', '    if self.host.validate_keys then self.host.validate_keys(keys)end',
           '    if self.host.workbench and self.host.validate_menu_alias then\n'
           '        self.host.validate_menu_alias(self.config.controls.enter)\n    end\n'
           '    if self.host.validate_keys then self.host.validate_keys(keys)end')
    change('runtime.lua', '    self.host.bind_key(self.config.controls.enter, function()\n'
           '        self:action("enter", function() return self.session:enter() end)\n    end)',
           '    self.host.bind_key(self.config.controls.enter, function()\n'
           "        if self.host.workbench and (self.session.state=='ACTIVE'or self.host.workbench:is_open())then\n"
           '            local confirming=self.host.workbench:is_open()\n'
           "            self:action(confirming and'workbench_confirm'or'workbench_toggle',function()\n"
           '                if confirming then return self.host.workbench:confirm()else return self.host.workbench:open()end\n'
           '            end)\n'
           '        else self:action("enter", function() return self.session:enter() end)end\n    end)')
    change('runtime.lua', '    local bind_gameplay=self.host.bind_gameplay_key or self.host.bind_key',
           '    if self.host.workbench and self.host.bind_menu_alias then\n'
           '        local key=self.config.controls.enter\n'
           '        self.host.bind_menu_alias(key,function()\n'
           "            self:workbench_action('workbench_toggle',key,function()return self.host.workbench:toggle()end)\n"
           '        end)\n    end\n'
           '    local bind_gameplay=self.host.bind_gameplay_key or self.host.bind_key')
    change('runtime.lua', '            bind_gameplay(definition.key, function()\n'
           '                self:action(selected, function()',
           '            bind_gameplay(definition.key, function()\n'
           '                if self.host.workbench and self.host.workbench:is_open()then\n'
           "                    local delta=selected=='slot1'and-1 or(selected=='heavy_01'and 1 or nil)\n"
           "                    if delta then self:action('workbench_move',function()return self.host.workbench:move(delta)end)end\n"
           '                    return\n                end\n'
           '                self:action(selected, function()')
    change('boss_workbench.lua', '选择角色后按 Enter；Insert 或 Esc 返回',
           '选择角色后按 Enter；Insert、Shift+接管键或 Esc 返回')
    change('player_boss_picker.lua', 'Boss 工作台  |  Insert 开关',
           'Boss 工作台  |  Insert / Shift+接管键 开关')
    change('player_boss_picker.lua', '↑ / ↓ 浏览  |  Enter 选择  |  Esc 返回',
           '↑ / ↓ 或 F1 / F2 浏览 | Enter / F6 选择 | Esc / F10 返回')
    change('player_hud.lua', 'Insert', 'Insert / Shift+F6')
    change('player_hud.lua', 'Boss 工作台：选择角色与查看适配状态',
           '选角；接管中再按 F6 也可打开')
    change('owned_arena.lua', "                    if experiment_player_entry then log('PLAYER_ENTRY_READY',experiment_boss_id)end",
           "                    if experiment_player_entry then log('WORKBENCH_SHORTCUT_READY','SHIFT+'..config.controls.enter)end\n"
           "                    if experiment_player_entry then log('PLAYER_ENTRY_READY',experiment_boss_id)end")

    # Avoid repeated global object-array traversal for the same live identity.
    # Every cache use still checks weak/engine validity plus full name/address/class.
    change('ue_calls.lua', 'return setmetatable({ api = api }, Calls)',
           'return setmetatable({ api = api, object_cache = {}, cache_size = 0 }, Calls)')
    change('ue_calls.lua', '    local object = self.api.find_exact(path)\n',
           '    local object = self.object_cache[path]\n'
           '    if object == nil then object = self.api.find_exact(path) end\n')
    change('ue_calls.lua', '    if not weak_valid then return nil end',
           '    if not weak_valid then self.object_cache[path]=nil;return nil end')
    change('ue_calls.lua', '        assert(type(usable)==\'boolean\',\'object engine validity unreadable\')\n        if not usable then return nil end\n',
           '        assert(type(usable)==\'boolean\',\'object engine validity unreadable\')\n'
           '        if not usable then self.object_cache[path]=nil;return nil end\n')
    change('ue_calls.lua', '    return object\nend\n\nfunction Calls:resolve',
           '    if self.object_cache[path]==nil then\n'
           '        if self.cache_size>=256 then self.object_cache={};self.cache_size=0 end\n'
           '        self.object_cache[path]=object;self.cache_size=self.cache_size+1\n'
           '    end\n    return object\nend\n\nfunction Calls:resolve')
    # Keep every native target read and validation. Only duplicate diagnostic I/O
    # is suppressed; identity reuse and hard/soft-lock changes still log an event.
    change('ue_combat.lua', "    local utils=valid(g.StaticFindObject('/Script/SGameCombatSystem.Default__FactionUtils'),'faction library')",
           "    local last_query=setmetatable({},{__mode='k'})\n"
           "    local utils=valid(g.StaticFindObject('/Script/SGameCombatSystem.Default__FactionUtils'),'faction library')")
    change('ue_combat.lua', "                print('PBZ_COMBAT_TARGET:QUERY='..name(target)..'|ignore_soft='..name(hard)..'\\n')",
           "                local query=name(target)..'|ignore_soft='..name(hard)\n"
           "                local function address(o)return o and o:IsValid()and tostring(o:GetAddress())or'None'end\n"
           "                local signature=query..'|'..address(target)..'|'..address(hard)\n"
           '                if last_query[actor]~=signature then\n'
           "                    print('PBZ_COMBAT_TARGET:QUERY='..query..'\\n')\n"
           '                    last_query[actor]=signature\n                end')
    change('ue_calls.lua', 'function Calls:retirement_optional(reference)',
           'function Calls:retirement_optional(reference,census)')
    change('ue_calls.lua', '    local candidates=self.api.find_all(class_name)or{}',
           '    local candidates=census and census[class_name]\n'
           '    if not candidates then\n'
           '        candidates=self.api.find_all(class_name)or{}\n'
           '        if census then census[class_name]=candidates end\n    end')
    change('world_boundary.lua', '    local lookup=calls.retirement_optional or calls.optional',
           '    local census={}\n    local function lookup(owner,reference)\n'
           '        if owner.retirement_optional then return owner:retirement_optional(reference,census)end\n'
           '        return owner:optional(reference)\n    end')
    change('world_boundary.lua', '    local world=lookup(calls,receipt.world)\n    local pc=lookup(calls,receipt.player_controller)',
           '    local fast,world,pc=pcall(function()\n'
           '        return calls:optional(receipt.world),calls:optional(receipt.player_controller)\n    end)\n'
           '    if not fast then world=nil;pc=nil end')

    # A new gameplay controller may exist while old World objects remain valid.
    # Cleanup owned actors before reassembly rather than waiting indefinitely for GC.
    change('owned_arena.lua', "local watch=require('idle_world_watch').new(calls,captured,os.time)",
           "local watch=require('idle_world_watch').new(calls,captured,os.time,function()\n"
           '                            local current=bridge:player_controller()\n'
           '                            local pawn=current.Pawn\n'
           '                            return calls:world(current),calls:reference(current),calls:reference(pawn),pawn:K2_GetActorLocation()\n'
           '                        end)')
    change('owned_arena.lua', "                            if status=='retired'and not reassembly_requested then",
           "                            if status=='changed'and not reassembly_requested then\n"
           "                                log('IDLE_WORLD_CHANGED',captured.world.name..'|address='..captured.world.address)\n"
           "                                schedule_reassembly('gameplay World, player or location changed; cleanup previous assembly')\n"
           "                            elseif status=='retired'and not reassembly_requested then")

    # LoadMap also occurs after Esc/F10, with no active receipt. Retire that idle
    # assembly before loading; never carry the old camera/targets into a new map.
    change('map_travel_guard.lua', '    if not runtime or not runtime.running or not runtime.session.receipt then return end',
           '    if not runtime or not runtime.running then return end')
    change('map_travel_guard.lua', "    assert(session.state=='ACTIVE','travel requires current active receipt')",
           "    if not session.receipt then\n"
           "        if self.api.retire_idle then\n"
           "            assert(session.state=='OFF','idle travel requires restored player')\n"
           "            self.api.retire_idle(world,runtime)\n        end\n"
           '        return\n    end\n'
           "    assert(session.state=='ACTIVE','travel requires current active receipt')")
    change('map_travel_guard.lua', "    self.api.log('MAP_TRAVEL_RESTORED_BEFORE_LOAD',true)",
           "    self.api.log('MAP_TRAVEL_RESTORED_BEFORE_LOAD',true)\n"
           '    if self.api.retire_idle then self.api.retire_idle(world,runtime)end')
    # Install native pre/post hooks before title/readiness/initialization timers.
    # All mutable stages share the assembly epoch, including queued begin work.
    text=files[PREFIX+'owned_arena.lua'].decode('utf-8').replace('\r\n','\n')
    start=text.index('                    if experiment_player_entry and not map_travel_guard_installed then')
    end=text.index('                    if options.scene_transition_trial then',start)
    text=text[:start]+text[end:]
    files[PREFIX+'owned_arena.lua']=text.encode('utf-8')
    change('owned_arena.lua', 'local map_travel_guard_installed=false',
           'local map_lifecycle\nlocal assembly_world,assembly_calls')
    change('owned_arena.lua', '        local player=pc.Pawn\n',
           '        local player=pc.Pawn\n'
           '        if experiment_player_entry then\n'
           "            assert(not map_lifecycle:suspended()and map_lifecycle:ready(player:GetWorld()),'native map transaction still pending')\n"
           "            assembly_calls=require('ue_calls').new({find_exact=StaticFindObject,usable=valid})\n"
           '            assembly_world=assembly_calls:world(pc)\n'
           '            map_lifecycle:accept_readiness(player:GetWorld())\n        end\n')
    change('owned_arena.lua', 'wait_for_player=function()\n',
           'wait_for_player=function()\n'
           '    if experiment_player_entry and map_lifecycle:suspended()then return end\n')
    change('owned_arena.lua', "        local identity=player:GetFullName()..'|'..tostring(player:GetAddress())",
           '        if experiment_player_entry and not map_lifecycle:ready(player:GetWorld())then\n'
           "            no_gameplay_player=true;error('waiting for native post-load gameplay World')\n        end\n"
           "        local identity=player:GetFullName()..'|'..tostring(player:GetAddress())")
    change('owned_arena.lua', 'begin_experiment=function()\nExecuteInGameThread(function()',
           'begin_experiment=function()\nassembly_tasks:defer(0,function()')
    binding=(root/'tools/player_map_lifecycle_binding.lua').read_text(encoding='utf-8').replace('\r\n','\n')
    change('owned_arena.lua', 'ExecuteWithDelay(1500,function()ExecuteInGameThread(wait_for_player)end)',
           binding+'\nassembly_tasks:defer(1500,wait_for_player)')
    # Queued role selection must also become inert when pre-load cleanup retires it.
    change('owned_arena.lua', '                        ExecuteInGameThreadWithDelay(250,function()\n'
           '                            local restarted,problem=pcall(function()\n',
           "                        require('player_reassembly').schedule({current=function()return runtime end,\n"
           '                            defer=function(ms,fn)return assembly_tasks:defer(ms,fn)end},old_runtime,function()\n'
           '                            local restarted,problem=pcall(function()\n')
    # Native-route receipt distinguishes a missed native key edge from an action
    # refused by Lua. Event-only logging adds no per-frame input polling.
    change('ue_host.lua', '                    if route then route.fn()end\n',
           "                    if route then g.print('[PBZBossControl] input_route key='..tostring(native_key)..'\\n');route.fn()end\n")
    change('owned_arena.lua', "                                statics:OpenLevel(pc,FName(package),true,'')",
           "                                require('player_native_travel_trial').prepare(runtime,\n"
           '                                    {attest=guard,now=os.time,log=log})')
    change('owned_arena.lua', "                                log('ACTIVE_WORLD_TRIAL_REQUESTED',true)",
           "                                log('ACTIVE_WORLD_TRIAL_PREPARED',true)")
    change('owned_arena.lua', 'F12; reload exact captured current map once; isolated developer validation',
           'F12; restore once for native map menu travel; isolated developer validation')

    # Capture already verified wrappers with their receipt. Retirement can then
    # prove engine invalidity without a global name/class scan for every object.
    # A different cached identity still takes the independent census fallback.
    change('ue_calls.lua', 'object_cache = {}, cache_size = 0',
           'object_cache = {}, retirement_cache = {}, cache_size = 0')
    change('ue_calls.lua', '    return { name = object:GetFullName(), address = object:GetAddress(), class = object:GetClass():GetFullName() }',
           '    local ref={name=object:GetFullName(),address=object:GetAddress(),class=object:GetClass():GetFullName()}\n'
           '    local path=assert(ref.name:match("^[^ ]+ (.+)$"),"full object name required")\n'
           '    if self.object_cache[path]==nil then\n'
           '        if self.cache_size>=256 then self.object_cache={};self.retirement_cache={};self.cache_size=0 end\n'
           '        self.cache_size=self.cache_size+1\n'
           '    end\n'
           '    self.object_cache[path]=object\n'
           '    self.retirement_cache[path]={reference=ref,object=object}\n'
           '    return ref')
    change('ue_calls.lua', '    local named=self.api.find_exact(path)',
           '    local saved=self.retirement_cache[path]\n'
           '    local identity=saved and saved.reference\n'
           '    local cached=identity and identity.name==reference.name and identity.address==reference.address\n'
           '        and identity.class==reference.class and saved.object\n'
           '    if cached then\n'
           '        local weak=cached:IsValid()\n'
           '        assert(type(weak)=="boolean","retirement weak validity unreadable")\n'
           '        if not weak then return nil end\n'
           '        if cached:GetFullName()==reference.name and cached:GetAddress()==reference.address\n'
           '            and cached:GetClass():GetFullName()==reference.class then\n'
           '            if self.api.usable then\n'
           '                local usable=self.api.usable(cached)\n'
           '                assert(type(usable)=="boolean","retirement validity unreadable")\n'
           '                if not usable then return nil end\n'
           '            end\n'
           '            return cached\n'
           '        end\n'
           '    end\n'
           '    local named=self.api.find_exact(path)')
    text=files[PREFIX+'ue_calls.lua'].decode('utf-8')
    files[PREFIX+'ue_calls.lua']=text.replace('self.object_cache={};self.cache_size=0',
        'self.object_cache={};self.retirement_cache={};self.cache_size=0').encode('utf-8')
    # Only pending retirement checks are throttled. Never reuse a cached 'same'
    # result to authorize input or reuse a cached 'retired' result as disposal.
    change('world_boundary.lua', 'function Boundary.inspect(calls,receipt)',
           'local pending_checks=setmetatable({},{__mode="k"})\n'
           'function Boundary.inspect(calls,receipt,now)\n'
           '    if now~=nil then\n'
           '        assert(type(now)=="number"and now==now and math.abs(now)<math.huge,"retirement clock invalid")\n'
           '        local previous=pending_checks[receipt]\n'
           '        if previous and now>=previous.at and now<previous.at+1 then return "pending",previous.why end\n'
           '        pending_checks[receipt]=nil\n'
           '    end')
    change('world_boundary.lua', "    if #surviving>0 then return 'pending',table.concat(surviving,',')end",
           '    if #surviving>0 then\n'
           '        local why=table.concat(surviving,",")\n'
           '        if now~=nil then pending_checks[receipt]={at=now,why=why}end\n'
           '        return "pending",why\n'
           '    end')
    change('control_bridge.lua', "    local ok,status,why=pcall(require('world_boundary').inspect,self.calls,receipt)",
           "    local ok,status,why=pcall(require('world_boundary').inspect,self.calls,receipt,self.api.now())")

    # Delayed observations and timeout cleanup belong to one assembly. Cancel
    # them on cleanup; queued native callbacks must also check the retired epoch.
    change('owned_arena.lua', 'local assembly_generation=0',
           "local assembly_tasks=require('player_assembly_tasks').new(ExecuteInGameThreadWithDelay,CancelDelayedAction)\n"
           'local assembly_generation=0')
    change('owned_arena.lua', 'local function cleanup()\n    guard()',
           'local function cleanup()\n    guard()\n    assembly_tasks:retire()')
    change('owned_arena.lua', '    if setup_ticket and not setup_ticket.restored then setup_protection:restore(setup_ticket)end\n    return true',
           '    if setup_ticket and not setup_ticket.restored then setup_protection:restore(setup_ticket)end\n'
           '    assembly_world,assembly_calls=nil,nil\n    return true')
    text=files[PREFIX+'owned_arena.lua'].decode('utf-8')
    # The scheduler is constructed with the native function value (no call here).
    # Every actual delayed call belongs to the current assembly, including setup.
    text=text.replace('ExecuteInGameThreadWithDelay(', 'assembly_tasks:defer(')
    files[PREFIX+'owned_arena.lua']=text.encode('utf-8')
    return manifest, files


def expected(root=ROOT):
    old, files = payload(root)
    sources = {name: sha(root / name) for name in SOURCES}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    identity = dict(files=hashes, sources=sources, base_manifest_sha256=sha(root / 'releases' / BASE / MANIFEST))
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    bosses = [dict(row, bindings=row['bindings'] + (row['id'] in
        ('057_wanjun', '073_yanqiansui', '056_youlong', '058_maddoctor'))) for row in old['bosses']]
    manifest = dict(old, release_id='ahua-player-travel-dev-' + key, status='development',
        complete_mod=False, runtime_acceptance_current=False, integration_only=True, files=hashes,
        bosses=bosses, skill_binding_count=old['skill_binding_count'] + 4,
        travel_repair_base=BASE, travel_repair_identity=identity,
        pending=['native primary mouse input and cancellation', 'native cross-map travel and frame-time comparison'],
        travel_repair_runtime_verified=False)
    manifest.pop('acceptance_report', None); manifest.pop('acceptance_report_sha256', None)
    return manifest, files


def verify(directory, root=ROOT):
    directory = unlinked_path(directory)
    manifest, files = expected(root)
    assert directory.parent == (root / 'runtime/release-candidates').resolve()
    assert directory.name == manifest['release_id'] and validate_package(directory) == manifest
    assert all((directory / name).read_bytes() == data for name, data in files.items())
    return manifest


def build(root=ROOT):
    assert_closed(root)
    manifest, files = expected(root)
    directory = root / 'runtime/release-candidates' / manifest['release_id']
    if not directory.exists():
        directory.mkdir(parents=True)
        for name, data in files.items():
            path = directory / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        write_json(directory / MANIFEST, manifest)
    verify(directory, root)
    return directory


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(dict(candidate=str(build()), installed=False, runtime_verified=False), ensure_ascii=False))
