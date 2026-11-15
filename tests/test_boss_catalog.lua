-- 用途：防止玩家角色选择装配未知Boss、未验证技能或错误角色配置；只验证模块行为。
local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local catalog=require('boss_catalog')
local profile=require('profiles.ahua')
local list=catalog.list();assert(#list==2 and list[1].id=='ahua_guitoudao'and list[2].id=='057_wanjun')
list[1].id='modified';assert(catalog.list()[1].id=='ahua_guitoudao')
local config=catalog.configure('ahua_guitoudao',profile)
local unique,count={},0
for _,definition in pairs(config.skills)do count=count+1;unique[definition.id]=true end
local abilities=0;for _ in pairs(unique)do abilities=abilities+1 end
assert(count==29 and abilities==28 and config.skills.primary_attack.id=='skill_01')
for _,id in ipairs({'skill_04','skill_07_hard','special_03_flower','special_03_flower_cd','special_02_new','special_07','heavy_02','special_03','skill_06_hard','skill_09',
    'special_move_01','special_move_back','special_move_left','special_move_right','special_05_a','special_11'})do
    profile.skills[id].cancellation_runtime_verified=false
    assert(not pcall(catalog.configure,'ahua_guitoudao',profile))
    profile.skills[id].cancellation_runtime_verified=true
end
assert(config.controls.menu_exit=='ESCAPE'and config.controls.cycle_target=='F7')
assert(not pcall(catalog.configure,'invented_boss',profile))
local old=profile.skills.skill_08.gameplay_verified;profile.skills.skill_08.gameplay_verified=false
assert(not pcall(catalog.configure,'ahua_guitoudao',profile));profile.skills.skill_08.gameplay_verified=old
assert(not config.skills.attack_01 and not config.skills.lab_attack_01)
assert(config.skills.native_combo and profile.skills.attack_01.player_key_verified==true)
local native=profile.skills.attack_01;native.player_key_verified=false
assert(not catalog.configure('ahua_guitoudao',profile).skills.native_combo)
native.player_key_verified=true
local trial=catalog.configure('ahua_guitoudao',profile)
assert(trial.skills.native_combo.id=='attack_01'and trial.skills.native_combo.key=='R')
native.scheduler_runtime_verified=false
assert(not pcall(catalog.configure,'ahua_guitoudao',profile))
native.scheduler_runtime_verified=true
for _,id in ipairs({'homing_flower','homing_flower_hard'})do
    profile.skills[id].scheduler_runtime_verified=false
    assert(not pcall(catalog.configure,'ahua_guitoudao',profile))
    profile.skills[id].scheduler_runtime_verified=true
end
local wan=catalog.profile('057_wanjun');local wconfig=catalog.configure('057_wanjun',wan)
local wcount=0;for _ in pairs(wconfig.skills)do wcount=wcount+1 end
assert(wcount==4 and not wconfig.skills.primary_attack and not wconfig.skills.native_combo)
wan.skills.skill_01.cancellation_runtime_verified=false
assert(not pcall(catalog.configure,'057_wanjun',wan))
wan.skills.skill_01.cancellation_runtime_verified=true
local seen={}
for _,row in ipairs(require('workbench_catalog').list())do
 assert(not seen[row.id],'workbench must not repeat accepted Boss as a locked preview');seen[row.id]=true
 if row.id=='057_wanjun'then assert(row.playable)end
 if row.id=='073_yanqiansui'or row.id=='056_youlong'then assert(not row.playable)end
end
print('PASS independent two-Boss registry, exact bindings, preview quarantine and missing-proof rejection')
