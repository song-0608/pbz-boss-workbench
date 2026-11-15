-- 离线执行真实玩家目录，导出实际登记能力；无需游戏或引擎调用。
local root=assert(arg[1])
package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local profile=require('profiles.ahua')
local config=require('boss_catalog').configure(profile.id,profile)
local slots={};for slot in pairs(config.skills)do slots[#slots+1]=slot end;table.sort(slots)
for _,slot in ipairs(slots)do
    local row=config.skills[slot];local definition=profile.skills[row.id]
    print(table.concat({'CAP',slot,row.id,row.key,definition.name,definition.class_path,
        tostring(definition.gameplay_verified==true),tostring(definition.movement_runtime_verified==true),
        tostring(definition.natural_completion_verified==true),tostring(definition.cancellation_runtime_verified==true)},'\t'))
end
