local root=assert(arg[1]);package.path=root..'/PBZBossControl/Scripts/?.lua;'..package.path
local catalog=require('boss_catalog')
local entries=catalog.list();assert(#entries==3)
assert(entries[1].id=='ahua_guitoudao'and entries[2].id=='057_wanjun'and entries[3].id=='073_yanqiansui')
local profile=catalog.profile('073_yanqiansui')
local config=catalog.configure('073_yanqiansui',profile)
local expected={slot1={'skill_01','F1','SpecialAttack_03'},heavy_01={'heavy_01','F2','SpecialAttack_04'},
 skill_02={'skill_02','F3','Skill_03'},dash={'dash','F4','Skill_04'}}
local n=0
for slot,row in pairs(config.skills)do
 n=n+1;local actual=assert(expected[slot]);assert(row.id==actual[1]and row.key==actual[2]and row.verified)
 local skill=profile.skills[row.id];assert(skill.class_path:find('GA_YanQianSui_'..actual[3]..'.',1,true))
 assert(skill.natural_completion_verified and skill.cancellation_runtime_verified)
end
assert(n==4 and profile.requires_ordinary_switching_acceptance)
assert(not profile.skills.attack_01 and not profile.skills.teleport_left)
local preview=require('workbench_catalog').list();assert(#preview==4)
for i=1,3 do assert(preview[i].playable)end
assert(preview[4].id=='056_youlong'and not preview[4].playable)
assert(preview[4].name=='发狂的水行帮主：游龙')
assert(not pcall(catalog.profile,'056_youlong'),'metadata must not unlock YouLong')
print('PASS three-Boss candidate catalog, exact native bindings, isolated profiles and locked YouLong')
