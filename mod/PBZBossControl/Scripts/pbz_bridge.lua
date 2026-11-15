-- 用途：真实调用实现位于control_bridge/ue_calls；没有阿花绑定及本轮运行租约前保持入口禁用。
-- 不把“已编写调用代码”写成“已在阿花实机适配成功”。
return {
    available = false,
    reason = "Direct generic construction is disabled. Protected player assembly runs through main/player_entry/owned_arena after launcher attestation; full release lifecycle is still under validation.",
    create = function(api, profile) return require("control_bridge").new(api, profile) end,
    create_runtime = function(api, config, profile, globals)
        -- 用途：真实入口装配；声明验证、离线租约和输入验证缺失时，构造即失败且不注册键。
        local bridge = require("control_bridge").new(api, profile)
        local calls = require("ue_calls").new(api)
        api.cancel_skill = function(spec, binding) return calls:cancel(spec, binding) end
        if profile.camera and profile.camera.binding_verified then
            local native=require("ue_camera").new(globals,profile.camera)
            api.camera=require("camera_rig").new(calls,native,profile.camera)
        end
        bridge:environment()
        local host = require("ue_host").new(bridge, profile.input, globals)
        return require("runtime").new(bridge, config, host)
    end,
}
