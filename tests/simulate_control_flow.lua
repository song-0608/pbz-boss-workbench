-- 用途：用一套完全虚构的对象演示“主角→Boss→技能→冷却→恢复”。
-- 不加载UE4SS，不启动游戏，不读写真实对象、网络或存档。
local project = assert(arg[1], "project directory required")
package.path = project .. "/mod/PBZBossControl/Scripts/?.lua;" .. package.path
local Session = require("session")

-- 用途：这是Lua内存中的玩具场景；名称与技能ID都不是PBZ真实名称。
local world = { controlled = "mock-player", camera = "mock-player", ai_running = true,
    time = 0, cooldown_until = 0, skill_running = false, casts = 0 }
local bridge = {}
function bridge:context()
    return { isolated = true, offline = true, exe_sha256 = "mock-only",
             world_id = "mock-arena", boss_available = true }
end
function bridge:capture() -- 用途：修改前保存玩具场景的原状态，供退出时核对。
    return { controlled = world.controlled, camera = world.camera, ai_running = world.ai_running }
end
function bridge:take_control(receipt) -- 用途：仅修改模拟表，展示暂停AI、切控制与镜头。
    world.ai_running = false
    world.controlled, world.camera = "mock-boss", "mock-boss"
    return true
end
function bridge:verify_control(receipt)
    return world.controlled == "mock-boss" and world.camera == "mock-boss" and not world.ai_running
end
function bridge:can_start_skill(receipt, skill_id)
    return skill_id == "mock-attack" and world.time >= world.cooldown_until and not world.skill_running
end
function bridge:start_skill(receipt, skill_id)
    world.casts = world.casts + 1
    world.skill_running, world.cooldown_until = true, world.time + 3
    return "mock-cast-" .. world.casts
end
function bridge:is_skill_finished(receipt, token) return not world.skill_running end
function bridge:cancel_skills(receipt) world.skill_running = false; return true end
function bridge:restore(receipt)
    world.controlled, world.camera, world.ai_running = receipt.controlled, receipt.camera, receipt.ai_running
    return true
end
function bridge:verify_restored(receipt)
    return world.controlled == receipt.controlled and world.camera == receipt.camera
       and world.ai_running == receipt.ai_running and not world.skill_running
end

local config = { expected_exe_sha256 = "mock-only",
    skills = { slot1 = { id = "mock-attack", verified = true } } }
local session = Session.new(bridge, config)
local steps = 0
local function step(description, check)
    assert(check, "模拟步骤失败：" .. description)
    steps = steps + 1
    print(string.format("步骤 %02d 通过：%s", steps, description))
end

step("初始控制主角，Boss由AI控制", world.controlled == "mock-player" and world.ai_running)
step("进入Boss控制，保存恢复状态", session:enter())
step("暂停Boss AI，控制和镜头切向Boss", world.controlled == "mock-boss" and world.camera == "mock-boss" and not world.ai_running)
step("释放第一个模拟技能", session:skill("slot1"))
step("招式未结束时，拒绝重复施放", not session:skill("slot1") and world.casts == 1)
-- 用途：测试驱动明确通知动作完成；不是根据PBZ动画时长猜测。
world.skill_running = false
step("收到模拟完成事件后解除技能占用", session:poll() and session.current_skill == nil)
step("动作已结束但冷却未到，仍拒绝释放", not session:skill("slot1") and world.casts == 1)
world.time = 3 -- 用途：推进玩具时钟，不修改真实游戏速度。
step("模拟冷却结束后允许再次释放", session:skill("slot1") and world.casts == 2)
step("动作中退出，先清理技能再恢复", session:restore("mock user exit"))
step("主角、镜头、Boss AI均恢复，并且没有残留技能", session.state == "OFF"
    and world.controlled == "mock-player" and world.camera == "mock-player"
    and world.ai_running and not world.skill_running and session.current_skill == nil)
print("完整模拟流程通过：" .. steps .. " 个步骤；实际游戏集成仍未验证。")
