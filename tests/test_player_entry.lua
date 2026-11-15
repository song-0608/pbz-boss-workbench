local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local captured
package.loaded.owned_arena={start=function(options)captured=options;return 'started'end}
local Entry=require('player_entry');local profile=require('profiles.ahua')
local function launch()
    return{boss_id=profile.id,options={attest=function()return{isolated=true,offline=true,expires_at=os.time()+30,exe_sha256=profile.exe_sha256}end,
        interactive=true,practice=true,camera_binding={},combat_binding={},remote_binding={},barrier_binding={},
        protection_binding={},target_cycle=true,player_ui_binding={},arena_binding={binding_verified=true}}}
end
assert(Entry.start(launch())=='started'and captured.player_entry==true and captured.boss_id==profile.id)
for _,key in ipairs({'attest','camera_binding','combat_binding','remote_binding','barrier_binding','protection_binding','target_cycle','player_ui_binding','arena_binding'})do
    local value=launch();value.options[key]=nil;captured=nil
    assert(not pcall(Entry.start,value)and captured==nil,'missing '..key..' reached assembly')
end
local value=launch();value.options.arena_binding.binding_verified=false
assert(not pcall(Entry.start,value))
for _,key in ipairs({'extra_skills','skill_lab','player_key_trial','death_trial','native_death_reason','active_skill_death_trial','active_skill_disposal_trial'})do
    value=launch();value.options[key]=true;assert(not pcall(Entry.start,value),'developer actions reached player assembly')
end
value=launch();value.boss_id='unknown';assert(not pcall(Entry.start,value))
value=launch();value.options.attest=function()return{isolated=true,offline=true,expires_at=os.time()-1,exe_sha256=profile.exe_sha256}end
assert(not pcall(Entry.start,value))
print('Player entry requires current offline credentials, registered boss, complete protection and navigation; rejects developer controls')
