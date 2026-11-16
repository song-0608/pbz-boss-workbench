local root=assert(arg[1])
local own={'bwb_protocol.lua','bwb_adapter.lua','bwb_entry.lua','bwb_config.lua','bwb_host.lua','bwb_enemy_fence.lua',
    'bwb_online_scope.lua','bwb_online_control.lua','bwb_local_dependencies.lua'}
local native={'control_bridge','ue_calls','session','runtime','input_driver','world_boundary'}
local upstream={'main.lua','coop.lua','onlinepanel.lua','partner.lua','pvppanel.lua','panel.lua','puppets.lua','moves.lua'}
local count=0
for _,name in ipairs(own)do assert(loadfile(root..'/PBZCoop/Scripts/'..name));count=count+1 end
for _,name in ipairs(native)do assert(loadfile(root..'/PBZCoop/Scripts/bwb_local_native/'..name..'.lua'));count=count+1 end
for _,name in ipairs(upstream)do assert(loadfile(root..'/upstream-local-patches/'..name));count=count+1 end
print('PASS syntax only: '..count..' candidate Lua files; upstream code not executed')
