-- Load only the frozen local control dependencies staged by the builder.
-- A private require/cache prevents another mod's same-named Lua module from
-- replacing these implementations or receiving this control session's state.
return function(directory)
    local names={control_bridge=true,ue_calls=true,session=true,runtime=true,
        input_driver=true,world_boundary=true,boss_catalog=true,keymap=true,
        ['profiles.ahua']=true,['profiles.wanjun']=true,['profiles.yanqiansui']=true,['profiles.youlong']=true,
        ['profiles.wanjun_bindings']=true,['profiles.yanqiansui_bindings']=true,['profiles.youlong_bindings']=true,
        object_lifecycle=true,ue_combat=true,owned_initialization=true,player_protection=true,
        ue_arena_layout=true,arena_layout=true,yanqiansui_clearance_core=true,combat_identity=true,
        remote_control=true,ue_remote=true,ue_camera=true,camera_rig=true,ue_input_barrier=true,
        input_barrier=true,ue_host=true,ue_input=true,combo_scheduler=true,subtree_contracts=true,target_selector=true}
    local cache,loading={},{}
    local env=setmetatable({},{__index=_G})
    local function exact_require(name)
        assert(names[name],'unstaged local control dependency: '..tostring(name))
        if cache[name] then return cache[name] end
        assert(not loading[name],'cyclic local control dependency')
        loading[name]=true
        local chunk=assert(loadfile(directory..'bwb_local_native/'..name:gsub('%.','/')..'.lua','t',env))
        local value=chunk();assert(type(value)=='table','invalid local control module')
        loading[name]=nil;cache[name]=value
        return value
    end
    env.require=exact_require
    return {Bridge=exact_require('control_bridge'),Runtime=exact_require('runtime'),require=exact_require}
end
