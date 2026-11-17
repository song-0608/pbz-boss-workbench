local root=assert(arg[1])
local own={'bwb_protocol.lua','bwb_adapter.lua','bwb_entry.lua','bwb_config.lua','bwb_host.lua','bwb_enemy_fence.lua',
    'bwb_online_scope.lua','bwb_online_control.lua','bwb_local_dependencies.lua','bwb_online_arena.lua','bwb_spawn_native.lua',
    'bwb_profile_policy.lua','bwb_online_session.lua','bwb_startup.lua','bwb_combat_runtime.lua','bwb_visual.lua','bwb_visual_native.lua','bwb_visual_session.lua','bwb_launch_gate.lua','bwb_online_workbench.lua','bwb_workbench_native.lua'}
local native={'control_bridge','ue_calls','session','runtime','input_driver','world_boundary',
    'boss_catalog','keymap','profiles/ahua','profiles/wanjun','profiles/yanqiansui','profiles/youlong',
    'profiles/wanjun_bindings','profiles/yanqiansui_bindings','profiles/youlong_bindings',
    'object_lifecycle','ue_combat','owned_initialization','player_protection','ue_arena_layout',
    'arena_layout','yanqiansui_clearance_core','combat_identity','remote_control','ue_remote',
    'ue_camera','camera_rig','ue_input_barrier','input_barrier','ue_host','ue_input',
    'combo_scheduler','subtree_contracts','target_selector','boss_workbench','workbench_input','workbench_catalog'}
local upstream={'main.lua','coop.lua','onlinepanel.lua','partner.lua','pvppanel.lua','panel.lua','puppets.lua','moves.lua','autostart.lua'}
local count=0
for _,name in ipairs(own)do assert(loadfile(root..'/PBZCoop/Scripts/'..name));count=count+1 end
for _,name in ipairs(native)do assert(loadfile(root..'/PBZCoop/Scripts/bwb_local_native/'..name..'.lua'));count=count+1 end
for _,name in ipairs(upstream)do assert(loadfile(root..'/upstream-local-patches/'..name));count=count+1 end
print('PASS syntax only: '..count..' candidate Lua files; upstream code not executed')
