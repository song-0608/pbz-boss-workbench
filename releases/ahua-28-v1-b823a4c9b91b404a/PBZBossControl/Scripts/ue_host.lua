-- 用途：把纯Lua运行调度接到本版本UE4SS的游戏线程、逐帧回调、真实输入和键位。
-- 环境租约由外部研究监督器注入bridge；这里绝不写死offline=true。
local Input = require("ue_input")
local Host = {}

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
    return {
        on_game_thread = function(fn) g.ExecuteInGameThread(fn) end,
        bind_key = function(key, fn)
            assert(g.Key[key] ~= nil, "unknown key: " .. tostring(key))
            g.RegisterKeyBind(g.Key[key], fn)
        end,
        -- 用途：每帧只取一次鼠标位移；不用独立异步定时器重复消费同一帧输入。
        every_frame = function(fn) return g.LoopInGameThreadAfterFrames(1, fn) end,
        cancel_frame = function(handle) return g.CancelDelayedAction(handle) end,
        read_input = function(receipt) return input:read(receipt) end,
        log = function(message) g.print("[PBZBossControl] " .. message .. "\n") end,
    }
end

return Host
