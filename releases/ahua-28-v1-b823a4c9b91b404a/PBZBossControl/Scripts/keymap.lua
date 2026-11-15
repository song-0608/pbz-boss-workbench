-- 用途：将已经校验的玩家按键表应用到本轮实际可用的技能；改键不能解除技能验收门槛。
local Keymap={}
function Keymap.apply(config,bindings)
    assert(type(bindings)=='table'and type(bindings.controls)=='table'and type(bindings.skills)=='table','keymap required')
    for action,key in pairs(bindings.controls)do
        if config.controls[action]then config.controls[action]=key end
    end
    for slot,key in pairs(bindings.skills)do
        local definition=config.skills[slot]
        if definition and definition.verified and not definition.lab_only then definition.key=key end
    end
    -- 用途：Runtime:start还会校验本轮所有实际启用键位冲突；这里不替未装配技能生成入口。
    return config
end
return Keymap
