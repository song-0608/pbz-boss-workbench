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
           'tools/player_world_watch.lua', 'tools/player_cross_map_trial.lua', 'tests/test_player_travel_repair.lua',
           'tests/test_player_travel_candidate.py')


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
    files[PREFIX + 'player_cross_map_trial.lua'] = (root / 'tools/player_cross_map_trial.lua').read_bytes()
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
           '                            return calls:world(bridge:player_controller())\n                        end)')
    change('owned_arena.lua', "                            if status=='retired'and not reassembly_requested then",
           "                            if status=='changed'and not reassembly_requested then\n"
           "                                log('IDLE_WORLD_CHANGED',captured.world.name..'|address='..captured.world.address)\n"
           "                                schedule_reassembly('new gameplay World; cleanup owned previous assembly')\n"
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
    change('owned_arena.lua', "                        local travel=require('map_travel_guard').new({runtime=function()return runtime end,attest=guard,log=log,",
           "                        local travel=require('map_travel_guard').new({runtime=function()return runtime end,attest=guard,log=log,\n"
           '                            retire_idle=function(world,current)\n'
           "                                assert(current.session.state=='OFF'and not current.session.receipt,'restored player required before travel cleanup')\n"
           "                                assert(calls:same(world,calls:resolve(captured_world)),'travel World differs from assembly')\n"
           "                                assert(cleanup(),'preload owned cleanup not verified')\n"
           '                                actor,ai,target_actor,target_ai,session,runtime,setup_protection,setup_ticket=nil,nil,nil,nil,nil,nil,nil,nil\n'
           '                                extra_targets={};initialized_owned={};spawn_attempts=0;initialization_deadline=nil;rejected_layouts={}\n'
           '                                gate_started,stationary_polls=0,0\n'
           '                                travel_wait_world=captured_world\n'
           "                                log('MAP_TRAVEL_IDLE_CLEANED',true)\n"
           '                                ExecuteInGameThreadWithDelay(1000,wait_for_player)\n'
           '                            end,')
    # These upvalues belong to Arena.start, not the per-assembly closure.
    change('owned_arena.lua', 'local map_travel_guard_installed=false',
           'local map_travel_guard_installed=false\nlocal travel_wait_world')
    change('owned_arena.lua', '                    if experiment_player_entry and not map_travel_guard_installed then',
           '                    local captured_world=calls:world(pc)\n'
           '                    if experiment_player_entry and not map_travel_guard_installed then')
    # The one installed hook must follow the current assembly, not its first pc/calls.
    change('owned_arena.lua', 'local travel_wait_world', 'local travel_wait_world\nlocal retire_idle_assembly')
    start = "                    local captured_world=calls:world(pc)\n                    if experiment_player_entry and not map_travel_guard_installed then"
    end = '                            end,\n                            same_world=function(world,reference)'
    text = files[PREFIX + 'owned_arena.lua'].decode('utf-8')
    a = text.index(start); b = text.index(end, a)
    block = text[a:b + len('                            end,')]
    body = block.split('                            retire_idle=function(world,current)\n', 1)[1].rsplit('                            end,', 1)[0]
    replacement = ('                    local captured_world=calls:world(pc)\n'
        '                    retire_idle_assembly=function(world,current)\n' + body + '                    end\n'
        '                    if experiment_player_entry and not map_travel_guard_installed then\n'
        "                        assert(type(RegisterLoadMapPreHook)=='function','current loader LoadMap pre-hook unavailable')\n"
        "                        local travel=require('map_travel_guard').new({runtime=function()return runtime end,attest=guard,log=log,\n"
        '                            retire_idle=function(world,current)return retire_idle_assembly(world,current)end,')
    files[PREFIX + 'owned_arena.lua'] = replace(text, block, replacement).encode('utf-8')
    change('owned_arena.lua', "        local identity=player:GetFullName()..'|'..tostring(player:GetAddress())",
           "        if travel_wait_world then\n"
           "            local world=player:GetWorld()\n"
           "            assert(valid(world),'gameplay World still loading')\n"
           "            if world:GetFullName()==travel_wait_world.name and world:GetAddress()==travel_wait_world.address then\n"
           "                no_gameplay_player=true;error('waiting for LoadMap to leave previous World')\n"
           '            end\n            travel_wait_world=nil\n        end\n'
           "        local identity=player:GetFullName()..'|'..tostring(player:GetAddress())")
    change('owned_arena.lua', "                                statics:OpenLevel(pc,FName(package),true,'')",
           "                                local destination=require('player_cross_map_trial').destination(package)\n"
           "                                log('CROSS_MAP_TRIAL_ROUTE',package..'|'..destination)\n"
           "                                statics:OpenLevel(pc,FName(destination),true,'')")
    change('owned_arena.lua', 'F12; reload exact captured current map once; isolated developer validation',
           'F12; native travel between observed valley/forest packages once; isolated developer validation')
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
