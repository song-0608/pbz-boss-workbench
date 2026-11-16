-- Load only the frozen local control dependencies staged by the builder.
-- A private require/cache prevents another mod's same-named Lua module from
-- replacing these implementations or receiving this control session's state.
return function(directory)
    local names={control_bridge=true,ue_calls=true,session=true,runtime=true,
        input_driver=true,world_boundary=true}
    local cache,loading={},{}
    local env=setmetatable({},{__index=_G})
    local function exact_require(name)
        assert(names[name],'unstaged local control dependency: '..tostring(name))
        if cache[name] then return cache[name] end
        assert(not loading[name],'cyclic local control dependency')
        loading[name]=true
        local chunk=assert(loadfile(directory..'bwb_local_native/'..name..'.lua','t',env))
        local value=chunk();assert(type(value)=='table','invalid local control module')
        loading[name]=nil;cache[name]=value
        return value
    end
    env.require=exact_require
    return {Bridge=exact_require('control_bridge'),Runtime=exact_require('runtime'),require=exact_require}
end
