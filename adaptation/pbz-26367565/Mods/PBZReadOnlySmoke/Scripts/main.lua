-- 用途：在 PBZ 研究副本验证自己的 UE4SS 适配；所有游戏对象操作均为读取。
-- 用途：这里没有改血、接管 Boss、调用技能、加载存档或网络请求。
print("PBZ_READONLY_SMOKE:START\n") -- 用途：只证明 Lua 文件开始执行，不能算验收通过。

local attempts = 0 -- 用途：限制等待世界加载的重试次数，避免无限循环。

local function inspect_once() -- 用途：把一组相关的只读检查组织成一次可解释的测试。
    attempts = attempts + 1 -- 用途：记录本次是第几次尝试。
    ExecuteInGameThread(function() -- 用途：通过引擎 Tick 在游戏线程读取对象。
        local ok, reason = pcall(function() -- 用途：捕获 Lua 层错误并写出明确失败信息。
            local actor = StaticFindObject("/Script/Engine.Actor") -- 用途：按完整路径查找 Actor 类。
            assert(actor:IsValid(), "Actor class unavailable") -- 用途：无效指针不继续使用。
            assert(actor:GetFullName() == "Class /Script/Engine.Actor", "Actor name mismatch") -- 用途：交叉检查名称和类信息。
            print("PBZ_READONLY_SMOKE:ACTOR=" .. actor:GetFullName() .. "\n") -- 用途：记录真实读取结果。

            local properties = 0 -- 用途：统计 Actor 自身的反射属性，验证 FField 链。
            actor:ForEachProperty(function(property) -- 用途：按引擎链表读取，不猜测属性地址。
                properties = properties + 1 -- 用途：累计实际读到的属性数。
                if properties <= 3 then -- 用途：只输出前三个名称，控制日志大小。
                    print("PBZ_READONLY_SMOKE:PROPERTY=" .. property:GetFullName() .. "\n")
                end
                assert(properties <= 512, "Unexpected Actor property count") -- 用途：发现循环或错误布局即报告失败。
                return -- 用途：返回 nil 继续遍历；当前源码绑定对 false 存在重复弹栈问题。
            end)
            assert(properties > 0, "Actor property chain empty") -- 用途：空链不能误认为验证通过。
            print("PBZ_READONLY_SMOKE:PROPERTY_COUNT=" .. tostring(properties) .. "\n")

            local character = StaticFindObject("/Script/Engine.Default__Character") -- 用途：使用原生类默认对象，不触碰玩家实例。
            assert(character:IsValid(), "Character CDO unavailable")
            local jump_count = character.JumpMaxCount -- 用途：通过反射读取整数，验证属性类型与偏移。
            assert(type(jump_count) == "number" and jump_count >= 0 and jump_count <= 100, "Invalid JumpMaxCount")
            print("PBZ_READONLY_SMOKE:JUMP_MAX_COUNT=" .. tostring(jump_count) .. "\n")
            local movement = character.CharacterMovement -- 用途：验证对象类型属性读取，不修改移动。
            assert(movement:IsValid(), "CharacterMovement unavailable")
            print("PBZ_READONLY_SMOKE:MOVEMENT=" .. movement:GetFullName() .. "\n")

            local world = FindFirstOf("World") -- 用途：读取当前世界实例，验证运行时对象查找。
            assert(world:IsValid(), "World unavailable")
            print("PBZ_READONLY_SMOKE:WORLD=" .. world:GetFullName() .. "\n")
            print("PBZ_READONLY_SMOKE:PASS\n") -- 用途：只有全部检查完成才写成功标记。
        end)
        if not ok then -- 用途：只有明确失败才重试；C++ 崩溃不能被 pcall 捕获。
            print("PBZ_READONLY_SMOKE:ATTEMPT_FAILED=" .. tostring(reason) .. "\n")
            if attempts < 3 then -- 用途：最多尝试三次。
                ExecuteWithDelay(3000, inspect_once) -- 用途：给菜单世界加载留出时间。
            else
                print("PBZ_READONLY_SMOKE:FAIL\n") -- 用途：明确区分失败和成功。
            end
        end
    end)
end

ExecuteWithDelay(2000, inspect_once) -- 用途：Mod 启动后稍等两秒再进行首轮读取。
