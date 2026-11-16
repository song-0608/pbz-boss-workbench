-- 用途：把纯Lua运行调度接到本版本UE4SS的游戏线程、逐帧回调、真实输入和键位。
-- 环境租约由外部研究监督器注入bridge；这里绝不写死offline=true。
local Input = require("ue_input")
local Host = {}
-- One native dispatcher per key across same-process Boss reassemblies.
-- Retired hosts release their routes so native callbacks do not retain old runtimes.
local routers=setmetatable({},{__mode='k'})

function Host.new(bridge, binding, globals)
    local g = globals or _G
    assert(g.EngineTickAvailable == true and type(g.LoopInGameThreadAfterFrames) == "function"
        and type(g.CancelDelayedAction) == "function" and type(g.ExecuteInGameThread) == "function"
        and type(g.RegisterKeyBind) == "function", "verified UE4SS frame scheduler required")
    local statics = g.StaticFindObject("/Script/Engine.Default__GameplayStatics")
    assert(statics and statics:IsValid(), "GameplayStatics CDO missing")
    local input = Input.new(bridge, {
        make_name = function(value) return g.FName(value) end,
        game_paused = function(pc) return statics:IsGamePaused(pc) == true end,
    }, binding)
    local router=routers[g]
    if not router then router={registered={},routes={}};routers[g]=router end
    local owner={}
    local pending_releases={}
    return {
        on_game_thread = function(fn) g.ExecuteInGameThread(fn) end,
        validate_keys = function(keys)
            for key in pairs(keys)do assert(g.Key[key]~=nil,'unknown key: '..tostring(key))end
        end,
        bind_key = function(key, fn)
            assert(g.Key[key] ~= nil, "unknown key: " .. tostring(key))
            local native_key=g.Key[key]
            if not router.registered[native_key]then
                g.RegisterKeyBind(native_key,function()
                    local route=router.routes[native_key]
                    if route then route.fn()end
                end)
                router.registered[native_key]=true
            end
            router.routes[native_key]={owner=owner,fn=fn}
        end,
        release_keys = function()
            for handle in pairs(pending_releases)do g.CancelDelayedAction(handle)end
            pending_releases={}
            for key,route in pairs(router.routes)do
                if route.owner==owner then router.routes[key]=nil end
            end
            return true
        end,
        after_key_release = function(key,fn)
            local names={ESCAPE='Escape',RETURN='Enter',INS='Insert'}
            local frames,handle,finished=0,nil,false
            handle=g.LoopInGameThreadAfterFrames(1,function()
                if finished then return end
                frames=frames+1
                if frames<2 then return end
                local pc=bridge:player_controller()
                if pc:IsInputKeyDown({KeyName=g.FName(names[key]or key)})then return end
                -- The delayed-action API ignores callback return values. Cancel explicitly
                -- before invoking an action which may replace or stop this host.
                finished=true
                g.CancelDelayedAction(handle)
                pending_releases[handle]=nil
                fn()
            end)
            pending_releases[handle]=true
            return handle
        end,
        -- 用途：每帧只取一次鼠标位移；不用独立异步定时器重复消费同一帧输入。
        every_frame = function(fn) return g.LoopInGameThreadAfterFrames(1, fn) end,
        cancel_frame = function(handle) return g.CancelDelayedAction(handle) end,
        read_input = function(receipt) return input:read(receipt) end,
        log = function(message) g.print("[PBZBossControl] " .. message .. "\n") end,
    }
end

return Host
