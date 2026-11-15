local root=assert(arg[1]);package.path=root..'/PBZBossControl/Scripts/?.lua;'..package.path
local catalog=require('boss_catalog');local entries=catalog.list();assert(#entries==4)
local counts={ahua_guitoudao=28,['057_wanjun']=4,['073_yanqiansui']=4,['056_youlong']=4}
local abilities,bindings=0,0
for _,entry in ipairs(entries)do
    assert(counts[entry.id]==entry.abilities);abilities=abilities+entry.abilities;bindings=bindings+entry.bindings_count
    local profile=catalog.profile(entry.id);local config=catalog.configure(entry.id,profile)
    assert(config.boss_id==entry.id)
end
assert(abilities==40 and bindings==41)
local profile=catalog.profile('056_youlong');assert(profile.class_path:find('YouLong_Harpoon',1,true))
assert(profile.config_path:find('ActorC_YouLong_Harpoon',1,true)and profile.requires_ordinary_switching_acceptance)
local config=catalog.configure('056_youlong',profile)
local expected={slot1='MiddleAttack_01',heavy_01='HeavyAttack_01',skill_02='DodgeAttack_L',dash='DodgeAttack_R'}
local n=0
for slot,row in pairs(config.skills)do
    n=n+1;assert(profile.skills[row.id].class_path:find('GA_YouLong_'..assert(expected[slot])..'.',1,true))
    assert(row.verified and profile.skills[row.id].cancellation_runtime_verified)
end
assert(n==4 and not config.skills.native_combo and not config.skills.primary_attack)
local preview=require('workbench_catalog').list();assert(#preview==4)
local seen={};for _,entry in ipairs(preview)do assert(not seen[entry.id]);seen[entry.id]=true;assert(entry.playable)end
assert(not pcall(catalog.profile,'unknown'))
print('PASS four-Boss candidate: exact profiles, 40 abilities/41 bindings, native YouLong actions, no duplicate previews')
