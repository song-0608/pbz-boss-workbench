local bindings=(function()
-- Four independently accepted native actions only.
return {{["slot"]="slot1",["id"]="skill_01",["key"]="F1",["requires_cancel"]=true},{["slot"]="heavy_01",["id"]="heavy_01",["key"]="F2",["requires_cancel"]=true},{["slot"]="skill_02",["id"]="skill_02",["key"]="F3",["requires_cancel"]=true},{["slot"]="dash",["id"]="dash",["key"]="F4",["requires_cancel"]=true}}

end)()
local extra={{["slot"]="skill_06",["id"]="skill_06",["key"]="F5",["requires_cancel"]=true},{["slot"]="skill_08",["id"]="skill_08",["key"]="F8",["requires_cancel"]=true},{["slot"]="skill_07",["id"]="skill_07",["key"]="F9",["requires_cancel"]=true},{["slot"]="teleport_left",["id"]="teleport_left",["key"]="Q",["requires_cancel"]=true}}
local slots,keys={},{}
for _,row in ipairs(bindings)do slots[row.slot]=true;keys[row.key]=true end
for _,row in ipairs(extra)do
 assert(not slots[row.slot] and not keys[row.key],'Duplicate expanded binding')
 slots[row.slot]=true;keys[row.key]=true;bindings[#bindings+1]=row
end
return bindings
