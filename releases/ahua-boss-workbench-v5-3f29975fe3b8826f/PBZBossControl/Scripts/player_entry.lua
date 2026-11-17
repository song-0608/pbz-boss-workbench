-- 用途：正式玩家装配入口；外部启动器签发本轮离线凭据，开发试验按键不能混入玩家配置。
local Entry={}
function Entry.start(launch)
    assert(type(launch)=='table'and type(launch.options)=='table','external player launch required')
    local o=launch.options
    assert(type(o.attest)=='function','external session attestation required')
    local grant=o.attest()
    assert(type(grant)=='table'and grant.isolated==true and grant.offline==true
        and type(grant.expires_at)=='number'and grant.expires_at>os.time(),'active offline session required')
    assert(o.interactive and o.practice and o.camera_binding and o.combat_binding
        and o.remote_binding and o.barrier_binding and o.protection_binding and o.target_cycle and o.player_ui_binding
        and o.arena_binding and o.arena_binding.binding_verified==true,
        'complete protected player assembly required')
    assert(not(o.extra_skills or o.skill_lab or o.player_key_trial or o.death_trial or o.native_death_reason
        or o.active_skill_death_trial or o.active_skill_disposal_trial),'developer actions are not player controls')
    local selected
    for _,boss in ipairs(require('boss_catalog').list())do if boss.id==launch.boss_id then selected=boss end end
    assert(selected,'unsupported boss selection')
    local profile=require(selected.profile)
    assert(profile.exe_sha256==grant.exe_sha256,'player build mismatch')
    require('boss_catalog').configure(launch.boss_id,profile,o.keymap)
    o.player_entry=true;o.boss_id=launch.boss_id
    return require('owned_arena').start(o)
end
return Entry
