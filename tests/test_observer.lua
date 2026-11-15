-- 用途：假对象复现流送、轮转、技能增长及数组收缩；不启动或操作游戏。
local root = assert(arg[1], "project path required")
local passed = 0
local function run_case(name, setup, steps, verify)
    local queue, output, reads = {}, {}, 0
    local fixture = { frame = 0, enemies = {} }
    local env = setmetatable({}, { __index = _G })
    env.print = function(value) output[#output + 1] = value end
    env.ExecuteWithDelay = function(_, fn) queue[#queue + 1] = fn end
    env.ExecuteInGameThread = function(fn) fn() end
    local function object(path)
        return { IsValid = function() return true end, GetFullName = function() return path end }
    end
    local function array(count)
        local control = { count = count }
        return setmetatable({ GetArrayNum = function() return control.count end }, {
            __index = function(_, index)
                assert(type(index) == "number" and index >= 1 and index <= control.count, "out-of-bounds access")
                reads = reads + 1
                if control.after_read then control.after_read(index) end
                return { Ability = object("GrantedAbility_" .. index) }
            end,
        }), control
    end
    local function npc(number, count)
        local item = object("NPC TestWorld:PersistentLevel.Monster_" .. number)
        item.CharacterName = { ToString = function() return "None" end }
        item["Actor Config"] = object("Config_" .. number)
        item["Actor Config"]["Character Name"] = {
            ValueCache = { ToString = function() return "" end },
            Key = { ToString = function() return "fixture_key_" .. number end },
        }
        item.Controller = object("AIController_" .. number)
        item.Controller.BrainComponent = object("Brain_" .. number)
        item.Controller.Blackboard = object("Blackboard_" .. number)
        item.Controller.BrainComponent.IsRunning = function() return true end
        item.Controller.BrainComponent.GetRunningBehaviorTree = function() return object("BehaviorTree_" .. number) end
        local items, control = array(count or 46)
        item.AbilitySystemComponent = { ActivatableAbilities = { Items = items } }
        return item, control
    end
    fixture.npc = npc
    local pc, player = object("Controller TestWorld:PersistentLevel.Player"), object("Player TestWorld:PersistentLevel.Hun")
    pc.Pawn, player.Controller = player, pc
    pc.K2_GetPawn = function() return player end
    player.GetController = function() return pc end
    player.CharacterMovement = object("Movement")
    local player_array, player_control = array(140)
    player.AbilitySystemComponent = object("PlayerASC")
    player.AbilitySystemComponent.ActivatableAbilities = { Items = player_array }
    fixture.player_control = player_control
    env.FindAllOf = function(kind)
        if kind == "PBZPlayerController" then return {pc} end
        if kind == "PBZCharacter_NPC" then return fixture.enemies end
        error("unexpected lookup")
    end
    setup(fixture)
    assert(loadfile(root .. "/adaptation/pbz-26367565/Mods/PBZObserveAI/Scripts/main.lua", "t", env))()
    for frame = 1, steps do
        fixture.frame = frame
        if fixture.before_frame then fixture.before_frame(frame) end
        assert(table.remove(queue, 1), "observer stopped early")()
    end
    verify(table.concat(output, ""), reads, fixture)
    assert(#queue == 1, "should keep scheduling in the same session")
    passed = passed + 1; print("PASS: " .. name .. " (fixture only)")
end
run_case("late NPC discovery and bounded 140+46 reads", function(f)
    local enemy = f.npc(1)
    f.before_frame = function(frame) f.enemies = frame >= 2 and {enemy} or {} end
end, 3, function(log, reads)
    assert(log:find("NPC_PENDING=", 1, true))
    assert(log:find("PLAYER_ABILITY_COLLECTED=140", 1, true))
    assert(log:find("NPC_1_ABILITY_COLLECTED=46", 1, true))
    assert(not log:find("ISSUE_", 1, true)); assert(reads == 186)
end)
run_case("unready NPC retries each failed stage", function(f)
    local enemy, count = f.npc(1, 0)
    local ai, config = enemy.Controller, enemy["Actor Config"]
    enemy.Controller, enemy["Actor Config"] = nil, nil
    f.enemies = {enemy}
    f.before_frame = function(frame)
        if frame == 4 then enemy.Controller, enemy["Actor Config"], count.count = ai, config, 46 end
    end
end, 8, function(log, reads)
    local pending = assert(log:find("NPC_1_PENDING_AI=", 1, true))
    local ready = assert(log:find("NPC_1_OBSERVED=", 1, true)); assert(ready > pending)
    assert(log:find("NPC_1_LOCALIZATION_PENDING=true", 1, true))
    assert(not log:find("ISSUE_", 1, true)); assert(reads == 186)
end)
run_case("ninth NPC receives the next scan budget", function(f)
    for index = 1, 9 do f.enemies[index] = f.npc(index) end
end, 3, function(log, reads)
    assert(log:find("NPC_9_OBSERVED=", 1, true)); assert(reads == 140 + 9 * 46)
    assert(not log:find("ISSUE_", 1, true))
end)
run_case("player and NPC ability growth triggers resampling", function(f)
    local enemy, count = f.npc(1); f.enemies = {enemy}
    f.before_frame = function(frame)
        if frame == 3 then f.player_control.count, count.count = 145, 48 end
    end
end, 5, function(log, reads)
    assert(log:find("PLAYER_ABILITY_COLLECTED=145", 1, true))
    assert(log:find("NPC_1_ABILITY_COLLECTED=48", 1, true))
    assert(reads == 140 + 46 + 145 + 48); assert(not log:find("ISSUE_", 1, true))
end)
run_case("shrinking array is checked before indexed access", function(f)
    local enemy, count = f.npc(1, 3); f.enemies = {enemy}
    count.after_read = function() count.count = 1; count.after_read = nil end
end, 4, function(log, reads)
    assert(log:find("ability array changed; stop before indexed access", 1, true))
    assert(not log:find("out-of-bounds access", 1, true))
    assert(log:find("NPC_1_ABILITY_COLLECTED=1", 1, true)); assert(reads == 142)
end)
run_case("unready NPC exhausts retries without false pass", function(f)
    local enemy = f.npc(1, 0); enemy.Controller = nil; f.enemies = {enemy}
end, 75, function(log, reads)
    assert(log:find("NPC_1_RETRY_EXHAUSTED_AI=", 1, true))
    assert(log:find("NPC_1_RETRY_EXHAUSTED_ABILITIES=", 1, true))
    assert(not log:find("NPC_1_OBSERVED=", 1, true)); assert(reads == 140)
    assert(not log:find("ISSUE_", 1, true))
end)
run_case("bounded cache reaches late actors among 300 NPCs", function(f)
    for index = 1, 300 do f.enemies[index] = f.npc(index, 1) end
end, 40, function(log)
    assert(log:find("Monster_300", 1, true)); assert(log:find("NPC_CACHE_EVICTED=", 1, true))
    assert(not log:find("ISSUE_", 1, true))
end)
print("TOTAL: " .. passed .. " observer fixtures passed; no game control or runtime validation.")
