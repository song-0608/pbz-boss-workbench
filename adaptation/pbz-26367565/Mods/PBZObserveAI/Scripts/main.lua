-- 用途：分阶段观察玩家、敌人、AI和已授予技能；不接管、不改数值、不激活技能。
-- 用途：同一游戏会话等待敌人流送，避免为了“敌人暂时为0”退出重进。
print("PBZ_AI_OBSERVE:START_V3\n")
local scans, issues, player_seen = 0, 0, {}
local ability_counts = {} -- 用途：角色流送后技能数量可能增长；变化时补采，不跨扫描缓存UObject。
local MAX_SCANS, MAX_NPCS, MAX_ABILITIES = 180, 8, 160
local MAX_TRACKED, MAX_TRIES = 256, 12
local tracked, tracked_count, next_id, cursor, last_npc_count = {}, 0, 0, 1, nil
local function log(key, value) print("PBZ_AI_OBSERVE:" .. key .. "=" .. tostring(value) .. "\n") end
local function fullname(object) -- 用途：每次重新检查包装对象，不跨扫描保存UObject。
    assert(object and object:IsValid(), "invalid object reference")
    return object:GetFullName()
end
local function branch(label, action) -- 用途：独立失败入清单，其余读取继续。
    local ok, reason = pcall(action)
    if not ok then issues = issues + 1; log("ISSUE_" .. label, reason) end
    return ok
end
local function valid(object) return object and object:IsValid() end
local function record_for(name) -- 用途：缓存只保存名字、数字和阶段状态；不保存引擎对象。
    if tracked[name] then tracked[name].last_scan = scans; return tracked[name] end
    if tracked_count >= MAX_TRACKED then
        local oldest_name, oldest_scan = nil, math.huge
        for key, item in pairs(tracked) do
            if item.last_scan < oldest_scan then oldest_name, oldest_scan = key, item.last_scan end
        end
        tracked[oldest_name] = nil; tracked_count = tracked_count - 1
        log("NPC_CACHE_EVICTED", oldest_name)
    end
    next_id = next_id + 1
    local item = { label = "NPC_" .. next_id, last_scan = scans, stages = {} }
    tracked[name], tracked_count = item, tracked_count + 1
    log(item.label, name) -- 用途：同一脚本会话按完整实例路径编号，切图不再复用列表序号。
    return item
end
local function stage(record, key, action) -- 用途：只有本阶段成功才去重；未就绪会退避重试。
    local item = record.stages[key]
    if not item then item = { tries = 0, next_scan = 0 }; record.stages[key] = item end
    if item.done or item.exhausted or scans < item.next_scan then return end
    item.tries = item.tries + 1
    local ok, result = pcall(action)
    if ok and result == true then item.done = true; log(record.label .. "_READY_" .. key, true); return end
    if not ok then issues = issues + 1; log("ISSUE_" .. record.label .. "_" .. key, result) end
    item.next_scan = scans + math.min(item.tries, 6)
    log(record.label .. "_PENDING_" .. key, "attempt=" .. item.tries .. "; initialized=false")
    if item.tries >= MAX_TRIES then
        item.exhausted = true
        log(record.label .. "_RETRY_EXHAUSTED_" .. key, "unresolved; not a pass; may be noncombat NPC")
    end
end
local function abilities(pawn, label)
    local items = pawn.AbilitySystemComponent.ActivatableAbilities.Items
    local count = items:GetArrayNum()
    assert(math.type(count) == "integer" and count >= 0 and count <= 512, "invalid bounded ability count")
    log(label .. "_ABILITY_TOTAL", count)
    -- 用途：固定源码的数组索引从1开始。越界访问可能扩容，故在游戏线程逐次核对长度。
    -- 用途：索引Get直接返回UScriptStruct；ForEach的RemoteUnrealParam才需要:get()。
    -- 这里不用ForEach，避免其当前源码的回调栈与提前退出问题。
    local limit = math.min(count, MAX_ABILITIES)
    for index = 1, limit do
        assert(index <= items:GetArrayNum(), "ability array changed; stop before indexed access")
        local spec = items[index]
        log(label .. "_ABILITY_" .. index, fullname(spec.Ability))
    end
    log(label .. "_ABILITY_COLLECTED", limit)
    log(label .. "_ABILITY_TRUNCATED", count > limit)
    assert(count > 0, "no granted abilities; observation is not a pass")
    return count
end
local function inspect()
    scans = scans + 1
    ExecuteInGameThread(function() -- 用途：读取反射对象和已核对的查询函数均在游戏线程。
        if scans == 1 or scans % 12 == 0 then log("SCAN", scans) end
        local ready = false
        branch("FIND_PLAYER", function()
            for _, controller in ipairs(FindAllOf("PBZPlayerController") or {}) do
                if not controller:IsValid() then goto next_controller end
                local controller_name = fullname(controller)
                if scans == 1 then log("CONTROLLER_CANDIDATE", controller_name) end
                if controller_name:find(":PersistentLevel.", 1, true) then
                    local pawn = controller.Pawn
                    if not pawn or not pawn:IsValid() then goto next_controller end
                    local pawn_name = fullname(pawn)
                    assert(fullname(pawn.Controller) == controller_name, "controller/pawn mismatch")
                    ready = true
                    if not player_seen[pawn_name] then
                        log("PLAYER", pawn_name); log("CONTROLLER", controller_name)
                        branch("QUERY_PAWN", function()
                            assert(fullname(controller:K2_GetPawn()) == pawn_name, "K2_GetPawn mismatch")
                            log("QUERY_PAWN_PASS", pawn_name)
                        end)
                        branch("QUERY_CONTROLLER", function()
                            assert(fullname(pawn:GetController()) == controller_name, "GetController mismatch")
                            log("QUERY_CONTROLLER_PASS", controller_name)
                        end)
                        branch("PLAYER_COMPONENTS", function()
                            log("PLAYER_MOVEMENT", fullname(pawn.CharacterMovement))
                            log("PLAYER_ASC", fullname(pawn.AbilitySystemComponent))
                        end)
                        player_seen[pawn_name] = true -- 用途：保存字符串去重，不保存失效对象引用。
                    end
                    branch("PLAYER_ABILITIES", function()
                        local count=pawn.AbilitySystemComponent.ActivatableAbilities.Items:GetArrayNum()
                        if ability_counts[pawn_name]~=count then ability_counts[pawn_name]=abilities(pawn,"PLAYER") end
                    end)
                    break
                end
                ::next_controller::
            end
        end)
        if ready then
            branch("FIND_NPCS", function()
                local enemies = FindAllOf("PBZCharacter_NPC") or {}
                if last_npc_count ~= #enemies or scans % 12 == 0 then log("NPC_COUNT", #enemies) end
                last_npc_count = #enemies
                if #enemies == 0 then
                    if scans % 12 == 1 then log("NPC_PENDING", "streaming or scene has no NPC; not completed") end
                    return -- 用途：只退出本分支；末尾仍安排下一次扫描。
                end
                -- 用途：每轮最多检查8个对象，从上轮游标继续；第9个及后续对象不会饿死。
                local budget = math.min(#enemies, MAX_NPCS)
                if cursor > #enemies then cursor = 1 end
                local first = cursor
                for offset = 0, budget - 1 do
                    local index = ((first + offset - 1) % #enemies) + 1
                    local npc = enemies[index]
                    branch("NPC_SLOT_" .. index, function()
                        if not valid(npc) then return end
                        local name = fullname(npc)
                        local record = record_for(name)
                        local label = record.label
                        stage(record, "NAME", function()
                            log(label .. "_NAME", npc.CharacterName:ToString()); return true
                        end)
                        stage(record, "CONFIG_NAME", function()
                            local config = npc["Actor Config"]
                            if not valid(config) then return false end
                            log(label .. "_CONFIG", fullname(config))
                            -- 用途：实机反射证明它是FlowLocText而非FText；只读真正的FText缓存和键。
                            local text=config["Character Name"]
                            local localized = text.ValueCache:ToString()
                            log(label .. "_CONFIG_NAME", localized)
                            log(label .. "_CONFIG_NAME_KEY", text.Key:ToString())
                            log(label .. "_LOCALIZATION_PENDING", localized == "")
                            return true -- 用途：配置可读与中文姓名已解析分别记录；空缓存不冒充姓名。
                        end)
                        stage(record, "AI", function()
                            local ai = npc.Controller
                            if not valid(ai) then return false end
                            log(label .. "_CONTROLLER", fullname(ai))
                            local brain = ai.BrainComponent
                            if not valid(brain) or not valid(ai.Blackboard) then return false end
                            log(label .. "_BRAIN", fullname(brain))
                            log(label .. "_BLACKBOARD", fullname(ai.Blackboard))
                            -- 用途：两个函数均已核对本构建返回值布局，均为查询；不调用StopLogic。
                            log(label .. "_BRAIN_RUNNING", brain:IsRunning())
                            local tree = brain:GetRunningBehaviorTree()
                            if not valid(tree) then return false end
                            log(label .. "_TREE", fullname(tree))
                            return true
                        end)
                        -- 用途：就绪后技能仍会流送；数量变化时只重采技能阶段，不重复已成功的AI查询。
                        local count_ok, count = pcall(function()
                            return npc.AbilitySystemComponent.ActivatableAbilities.Items:GetArrayNum()
                        end)
                        if count_ok and record.ability_count and record.ability_count ~= count then
                            record.stages.ABILITIES, record.observed, record.ability_count = nil, nil, nil
                        end
                        stage(record, "ABILITIES", function()
                            if not count_ok or count == 0 then return false end
                            record.ability_count = abilities(npc, label)
                            return true
                        end)
                        if not record.observed and record.stages.CONFIG_NAME.done and record.stages.AI.done
                            and record.stages.ABILITIES.done then
                            record.observed = true
                            log(label .. "_OBSERVED", "config/AI/abilities ready; identity not inferred")
                        end
                    end)
                end
                cursor = ((first + budget - 1) % #enemies) + 1
                if #enemies > budget and scans % 12 == 1 then log("NPC_SCAN_ROTATING", #enemies) end
                if scans % 12 == 0 then
                    for name, record in pairs(tracked) do
                        if scans - record.last_scan > 36 then tracked[name] = nil; tracked_count = tracked_count - 1 end
                    end
                end
            end)
        end
        if scans < MAX_SCANS then ExecuteWithDelay(5000, inspect)
        else log("BATCH_STOP", "scan budget reached; issues=" .. issues .. "; no boss control") end
    end)
end
ExecuteWithDelay(3000, inspect)
