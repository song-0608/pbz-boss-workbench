local root,candidate=assert(arg[1]),assert(arg[2])
package.path=candidate..'/PBZBossControl/Scripts/?.lua;'..package.path
local catalog=require('boss_catalog')
local expected={ahua_guitoudao=28,['057_wanjun']=8,['073_yanqiansui']=8,['056_youlong']=8}
local abilities,bindings,roles=0,0,0
for _,entry in ipairs(catalog.list())do
    local profile=catalog.profile(entry.id)
    assert(expected[entry.id]==entry.abilities)
    local n=0
    for _,definition in pairs(profile.skills)do
        n=n+1
        assert(definition.activation_runtime_verified and definition.natural_completion_verified)
        assert(definition.gameplay_verified or definition.movement_runtime_verified)
        if entry.id~='ahua_guitoudao'then assert(definition.cancellation_runtime_verified)end
    end
    assert(n==expected[entry.id])
    local config=catalog.configure(entry.id,profile)
    assert(config.controls.lock_target=='MIDDLE_MOUSE_BUTTON'and config.controls.cycle_target=='F7')
    local count=0;for _ in pairs(config.skills)do count=count+1 end
    assert(count==entry.bindings_count)
    if entry.id~='ahua_guitoudao'then
        for slot,key in pairs({skill_06='F5',skill_08='F8',skill_07='F9',teleport_left='Q'})do
            assert(config.skills[slot].id==slot and config.skills[slot].key==key)
        end
    end
    abilities=abilities+n;bindings=bindings+count;roles=roles+1
    -- Native proof remains required even in the experience development candidate.
    local skill=assert(profile.skills.skill_01)
    local before=skill.activation_runtime_verified
    skill.activation_runtime_verified=false
    assert(not pcall(catalog.configure,entry.id,profile))
    skill.activation_runtime_verified=before
    if entry.id~='ahua_guitoudao'then
        before=skill.cancellation_runtime_verified;skill.cancellation_runtime_verified=false
        assert(not pcall(catalog.configure,entry.id,profile));skill.cancellation_runtime_verified=before
    end
end
assert(roles==4 and abilities==52 and bindings==53)
local seen,playable,preview={},0,0
for _,entry in ipairs(require('workbench_catalog').list())do
    assert(not seen[entry.id]);seen[entry.id]=true
    if entry.playable then
        playable=playable+1;assert(expected[entry.id])
    else
        preview=preview+1
        assert(not expected[entry.id]and entry.reason and entry.detail and entry.stage)
        assert(not pcall(catalog.profile,entry.id),'resource previews must never grant a playable profile')
    end
end
assert(playable==4 and preview==6)
assert(not pcall(catalog.profile,'unknown'))
local entries=catalog.list();entries[1].id='modified';assert(catalog.list()[1].id~='modified')
print('PASS four verified Boss profiles, 52 abilities/53 bindings, six quarantined previews, native proof gates')
