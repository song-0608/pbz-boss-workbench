-- Boss differences belong here; native spawning keeps one shared lifecycle.
-- These rules select terrain algorithms only. They never grant playability.
local M={}
local rules={
    ahua_guitoudao={layout_module='arena_layout'},
    ['057_wanjun']={layout_module='arena_layout'},
    ['073_yanqiansui']={layout_module='yanqiansui_clearance_core',clearance_cm=900,clearance_samples=24},
    ['056_youlong']={layout_module='arena_layout'},
}
function M.resolve(profile)
    assert(type(profile)=='table' and type(profile.id)=='string','explicit Boss profile required')
    local rule=assert(rules[profile.id],'Boss terrain policy not reviewed: '..tostring(profile.id))
    local result={}
    for key,value in pairs(rule)do result[key]=value end
    return result
end
function M.choose(profile,req,...)
    local rule=M.resolve(profile)
    assert(type(req)=='function','private terrain dependency loader required')
    local layout,why=req(rule.layout_module).choose(...)
    if not layout then return nil,why end
    if rule.clearance_cm then
        assert(layout.clearance_cm==rule.clearance_cm and layout.clearance_samples==rule.clearance_samples,
            'Boss terrain clearance differs from reviewed policy')
    end
    return layout
end
return M
