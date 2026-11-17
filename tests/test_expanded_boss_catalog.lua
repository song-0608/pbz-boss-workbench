local package_root=assert(arg[1]);local expected=dofile(assert(arg[2]))
package.path=package_root..'/PBZBossControl/Scripts/?.lua;'..package.path
local Catalog=require('boss_catalog');local listed=Catalog.list();local by_id={}
for _,entry in ipairs(listed)do assert(not by_id[entry.id]);by_id[entry.id]=entry end
assert(#listed==4+#expected)
for _,row in ipairs(expected)do
 local entry=assert(by_id[row.id]);local profile=Catalog.profile(row.id)
 assert(profile.id==row.id and profile.display_name==row.name and entry.name==row.name)
 assert(profile.class_path==row.class_path and profile.config_path==row.config_path)
 local config=Catalog.configure(row.id,profile)
 assert(config.controls.lock_target=='MIDDLE_MOUSE_BUTTON')
 local count,seen=0,{}
 for _,binding in pairs(config.skills)do
  count=count+1;local skill=assert(profile.skills[binding.id]);assert(not seen[binding.id]);seen[binding.id]=true
  assert(skill.class_path==row.skills[binding.id] and skill.name and #skill.name>0)
  assert(skill.cancellation_runtime_verified and skill.natural_completion_verified)
  assert(binding.key=='F1'or binding.key=='F2'or binding.key=='F3'or binding.key=='F4')
 end
 assert(count==row.count and count==entry.abilities and count==entry.bindings_count)
end
local chooser=require('workbench_catalog').list();local seen={}
for _,entry in ipairs(chooser)do
 assert(not seen[entry.id]);seen[entry.id]=true
 if by_id[entry.id]then assert(entry.playable==true)else assert(entry.playable==false)end
end
assert(#chooser==10)
local text=require('player_boss_picker').render(chooser,#chooser,expected[#expected].id,'',false)
assert(type(text)=='string'and #text>0)
print('PASS exact independent profiles, unique selection entries, action counts and locked previews')
