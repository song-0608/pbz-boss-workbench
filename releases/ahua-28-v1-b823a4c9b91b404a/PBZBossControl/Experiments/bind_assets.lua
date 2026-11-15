-- 用途：只加载名字目录已经出现的阿花资产元数据；不生成角色、不接管、不发动技能。
-- 这是单次接口实验，不是正式Mod入口；由声明的离线研究脚本临时承载并记录哈希。
local function binding_log(key, value)
    print("PBZ_CONTROL_BINDING:" .. key .. "=" .. tostring(value) .. "\n")
end
local function binding_valid(object) return object and object:IsValid() end
local function load_observed_package(package_path)
    local asset_name = assert(package_path:match("/([^/]+)$"))
    -- 用途：查资源注册表以确认同一已知包的对象名；未找到就记录，绝不猜类直接Spawn。
    for _, path in ipairs({ package_path, package_path .. "." .. asset_name, package_path .. "." .. asset_name .. "_C" }) do
        local asset = LoadAsset(path)
        if binding_valid(asset) then binding_log("LOADED_ASSET", asset:GetFullName()); return asset end
    end
    binding_log("PACKAGE_UNRESOLVED", package_path)
end
ExecuteWithDelay(1500, function()
    ExecuteInGameThread(function()
        binding_log("START", "observed package metadata only; no spawning/possession/activation")
        local packages = {
            "/PBZCombatAsset/ActorData/Mobs/042_AHua/BP_Monster_AHua_GuiTouDao",
            "/PBZCombatAsset/ActorData/Mobs/042_AHua/ActorData/ActorC_AHua_GuiTouDao",
            "/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/GA_AHua_Skill_01",
        }
        for index, path in ipairs(packages) do
            local ok, error = pcall(function()
                local asset = load_observed_package(path)
                if not binding_valid(asset) then return end
                binding_log("ASSET_" .. index .. "_CLASS", asset:GetClass():GetFullName())
                if asset:IsA("/Script/CoreUObject.Class") then
                    local parent = asset:GetSuperStruct()
                    local depth = 0
                    while binding_valid(parent) and depth < 6 do
                        binding_log("ASSET_" .. index .. "_PARENT_" .. depth, parent:GetFullName())
                        parent = parent:GetSuperStruct()
                        depth = depth + 1
                    end
                    asset:ForEachFunction(function(fn)
                        binding_log("ASSET_" .. index .. "_FUNCTION", fn:GetFullName())
                    end)
                    local cdo = asset:GetCDO()
                    if binding_valid(cdo) then
                        binding_log("ASSET_" .. index .. "_CDO", cdo:GetFullName())
                        if index == 1 then
                            local config = cdo["Actor Config"]
                            if binding_valid(config) then binding_log("BOSS_ACTOR_CONFIG", config:GetFullName()) end
                        end
                    end
                elseif index == 2 then
                    -- 用途：调用已核对参数声明的只读姓名接口，在同一回调里解析本地化显示名。
                    local resolved_name = asset:GetCharacterName()
                    binding_log("RESOLVED_CHARACTER_NAME", resolved_name:ToString())
                    local name = asset["Character Name"]
                    binding_log("CONFIG_NAME", name.ValueCache:ToString())
                    binding_log("CONFIG_NAME_KEY", name.Key:ToString())
                end
            end)
            if not ok then binding_log("ISSUE_ASSET_" .. index, error) end
        end
        binding_log("END", "no gameplay functions called")
    end)
end)
