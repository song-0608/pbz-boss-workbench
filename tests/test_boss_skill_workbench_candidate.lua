local root=assert(arg[1]);package.path=root..'/PBZBossControl/Scripts/?.lua;'..package.path
local catalog=require('boss_catalog')
local expected={ahua_guitoudao=28,['057_wanjun']=8,['073_yanqiansui']=8,['056_youlong']=8}
local abilities,bindings,roles=0,0,0
for _,entry in ipairs(catalog.list())do
 local profile=catalog.profile(entry.id)
 assert(expected[entry.id]==entry.abilities)
 local n=0;for _,definition in pairs(profile.skills)do
  n=n+1
  assert(definition.activation_runtime_verified and definition.natural_completion_verified)
  assert(definition.cancellation_runtime_verified and (definition.gameplay_verified or definition.movement_runtime_verified))
 end
 assert(n==expected[entry.id])
 local config=catalog.configure(entry.id,profile)
 local count=0;for _ in pairs(config.skills)do count=count+1 end
 assert(count==entry.bindings_count)
 if entry.id~='ahua_guitoudao'then
  for slot,key in pairs({skill_06='F5',skill_08='F8',skill_07='F9',teleport_left='Q'})do
   assert(config.skills[slot].id==slot and config.skills[slot].key==key)
  end
 end
 abilities=abilities+n;bindings=bindings+count;roles=roles+1
end
assert(roles==4 and abilities==52 and bindings==53)
for _,entry in ipairs(require('workbench_catalog').list())do assert(entry.playable)end
print('Four Bosses, 52 native abilities, 53 ordinary bindings verified')
