-- 用途：一次离线会话核对阿花初始化依赖及真实输入返回值；不生成、接管、移动或发动技能。
local prefix = "PBZ_CONTROL_CONTRACT:"
local function log(key, value) print(prefix .. key .. "=" .. tostring(value) .. "\n") end
local function valid(value) return value and value:IsValid() end
local function guarded(label, fn)
    local ok, why = pcall(fn)
    if not ok then log("ISSUE_" .. label, why) end
end
local function load_package(path)
    local name=assert(path:match("/([^/]+)$"))
    for _, candidate in ipairs({path,path.."."..name,path.."."..name.."_C"}) do
        local value=LoadAsset(candidate)
        if valid(value) then return value end
    end
end
local function declaration_tree(asset, label)
    local node, depth = asset, 0
    while valid(node) and depth < 10 do
        log(label .. "_CLASS_" .. depth, node:GetFullName())
        -- 用途：只列目标角色/技能继承链声明，不枚举全游戏对象或地图。
        node:ForEachProperty(function(property) log(label .. "_PROPERTY_" .. depth, property:GetFullName()) end)
        node:ForEachFunction(function(fn) log(label .. "_FUNCTION_" .. depth, fn:GetFullName()) end)
        node = node:GetSuperStruct(); depth = depth + 1
    end
end
local function asset_query()
    log("START", "Ahua initialization and input contracts only")
    local boss = load_package("/PBZCombatAsset/ActorData/Mobs/042_AHua/BP_Monster_AHua_GuiTouDao")
    assert(valid(boss), "verified Ahua asset missing")
    declaration_tree(boss, "BOSS")
    local cdo = boss:GetCDO()
    local config = cdo["Actor Config"]
    assert(valid(config), "Ahua Actor Config missing")
    log("CHARACTER_NAME", config:GetCharacterName():ToString())
    local function class_array(container, field, label)
        guarded(label, function()
            local items = container[field]
            local count = items:GetArrayNum()
            assert(count >= 0 and count <= 256, "array bound")
            log(label .. "_COUNT", count)
            for i = 1, count do
                assert(i <= items:GetArrayNum(), "array changed")
                local item = items[i]
                guarded(label .. "_ITEM_" .. i, function() log(label .. "_ITEM_" .. i, item:GetFullName()) end)
            end
        end)
    end
    class_array(cdo, "DefaultAbilities", "DEFAULT_ABILITIES")
    class_array(config, "Abilities", "CONFIG_ABILITIES")
    class_array(config, "Passive Abilities", "CONFIG_PASSIVE_ABILITIES")
    for _, field in ipairs({"Input Config", "AIConfig  Default", "DriverConfig", "Off Combat State", "In Combat State"}) do
        guarded("CONFIG_REFERENCE", function()
            local value = config[field]
            if valid(value) then log("CONFIG_REFERENCE_" .. field, value:GetFullName()) end
        end)
    end
    for _, path in ipairs({"/Script/Engine.ESpawnActorCollisionHandlingMethod", "/Script/Engine.ESpawnActorScaleMethod"}) do
        guarded("ENUM", function()
            local value = StaticFindObject(path)
            assert(valid(value), "enum not loaded: " .. path)
            value:ForEachName(function(name, number) log("ENUM", path .. "|" .. name:ToString() .. "|" .. number) end)
        end)
    end
    local skill = load_package("/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/GA_AHua_Skill_01")
    assert(valid(skill), "verified skill missing")
    declaration_tree(skill, "SKILL")
    log("ASSETS_END", "no actors spawned or modified")
end
local function input_query()
    local statics = StaticFindObject("/Script/Engine.Default__GameplayStatics")
    for _, pc in ipairs(FindAllOf("PBZPlayerController") or {}) do
        if valid(pc) and valid(pc.Pawn) and pc:GetFullName():find(":PersistentLevel.", 1, true) then
            guarded("INPUT", function()
                log("PLAYER_CONTROLLER", pc:GetFullName())
                log("PLAYER_PAWN", pc.Pawn:GetFullName())
                local rotation = pc:GetControlRotation()
                assert(type(rotation.Yaw) == "number", "rotation Yaw is not numeric")
                local dx, dy = {}, {}
                pc:GetInputMouseDelta(dx, dy)
                assert(type(dx.DeltaX) == "number" and type(dy.DeltaY) == "number", "named scalar out parameters missing")
                log("MOUSE_DELTA", dx.DeltaX .. "," .. dy.DeltaY)
                log("CONTROL_YAW", rotation.Yaw)
                for _, key in ipairs({"W", "A", "S", "D"}) do
                    local down = pc:IsInputKeyDown({ KeyName = FName(key) })
                    assert(type(down) == "boolean", "key query did not return bool")
                    log("KEY_" .. key, down)
                end
                log("PAUSED", statics:IsGamePaused(pc))
                log("MOVE_IGNORED", pc:IsMoveInputIgnored())
                log("LOOK_IGNORED", pc:IsLookInputIgnored())
                log("INPUT_PASS", "read-only UE4SS invocation; movement and possession remain untested")
            end)
        end
    end
end
ExecuteWithDelay(1500, function()
    ExecuteInGameThread(function() guarded("ASSETS", asset_query); guarded("INPUT_QUERY", input_query) end)
end)
-- 用途：进入当前场景后按F9重新读取同一组输入；没有自动探索或游戏动作。
RegisterKeyBind(Key.F9, function() ExecuteInGameThread(function()
    guarded("ASSETS", asset_query); guarded("INPUT_QUERY", input_query)
end) end)
