local root=assert(arg[1]);package.path=root..'/PBZBossControl/Scripts/?.lua;'..package.path
local C=require('boss_catalog');local entries=C.list();assert(#entries==3)
local ids={'ahua_guitoudao','057_wanjun','056_youlong'}
local abilities,bindings=0,0
for i,entry in ipairs(entries)do
    assert(entry.id==ids[i]);abilities=abilities+entry.abilities;bindings=bindings+entry.bindings_count
    local profile=C.profile(entry.id);assert(C.configure(entry.id,profile).boss_id==entry.id)
end
assert(abilities==36 and bindings==37)
assert(not pcall(C.profile,'073_yanqiansui'),'locked Boss absent from normal actor registry')
local preview=require('workbench_catalog').list();assert(#preview==4)
for i=1,3 do assert(preview[i].id==ids[i]and preview[i].playable==true)end
assert(preview[4].id=='073_yanqiansui'and preview[4].playable==false and preview[4].reason:find('暂不开放',1,true))
local p=C.profile('056_youlong');local config=C.configure('056_youlong',p)
local expected={slot1='MiddleAttack_01',heavy_01='HeavyAttack_01',skill_02='DodgeAttack_L',dash='DodgeAttack_R'}
local count=0
for slot,row in pairs(config.skills)do
    count=count+1;assert(p.skills[row.id].class_path:find('GA_YouLong_'..assert(expected[slot])..'.',1,true))
    assert(row.verified and p.skills[row.id].cancellation_runtime_verified)
end
assert(count==4 and not config.skills.primary_attack and not config.skills.native_combo)
print('PASS three supported profiles, 36 abilities/37 bindings, exact native YouLong actions and locked YanQianSui')
