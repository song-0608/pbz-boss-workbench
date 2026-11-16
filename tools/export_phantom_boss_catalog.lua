-- Read verified, hash-checked release profiles, without loading the player entry point.
local root = assert(arg[1])
package.path = root .. '/PBZBossControl/Scripts/?.lua;' .. package.path
local catalog = require('boss_catalog')
local function quote(s)
    assert(type(s)=='string' and not s:find('[%z\1-\31"\\]'), 'unexpected catalog string')
    return '"'..s..'"'
end
local out = {}
for _,entry in ipairs(catalog.list()) do
    local profile = catalog.profile(entry.id)
    local config = catalog.configure(entry.id,profile)
    local actions = {}
    for _,binding in pairs(config.skills) do
        local path=assert(profile.skills[binding.id].class_path)
        actions[binding.id]=path
    end
    local names={}; for name in pairs(actions) do names[#names+1]=name end; table.sort(names)
    assert(#names==entry.abilities,'ability count differs from accepted catalog')
    local rows={}; for _,name in ipairs(names) do rows[#rows+1]=quote(name)..':'..quote(actions[name]) end
    out[#out+1]=quote(entry.id)..':{"class_path":'..quote(profile.class_path)..',"actions":{'..table.concat(rows,',')..'}}'
end
print('BWB_CATALOG_JSON={'..table.concat(out,',')..'}')
