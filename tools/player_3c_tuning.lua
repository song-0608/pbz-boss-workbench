-- Proposed player-control settings, not evidence of native movement/skill support.
-- Mouse deltas are already per-frame displacements: never multiply by frame time.
local Tuning={}
local defaults={mouse_scale=0.22,manual_unlock_degrees=1.0,skill_buffer_seconds=0.18,
    walk_speed_cm_s=480,turn_rate_degrees_s=540}
local roles={
    ['057_wanjun']={walk_speed_cm_s=420,turn_rate_degrees_s=420},
    ['073_yanqiansui']={walk_speed_cm_s=450,turn_rate_degrees_s=480},
    ['056_youlong']={walk_speed_cm_s=520,turn_rate_degrees_s=600},
}
local limits={mouse_scale={0.05,1},manual_unlock_degrees={0.25,10},
    skill_buffer_seconds={0,0.25},walk_speed_cm_s={150,900},turn_rate_degrees_s={90,900}}
function Tuning.resolve(id,override)
    local result={}
    for key,value in pairs(defaults)do result[key]=(roles[id]or{})[key]or value end
    for key,value in pairs(override or{})do
        local range=assert(limits[key],'unknown 3C setting: '..tostring(key))
        assert(type(value)=='number'and value==value and value>=range[1]and value<=range[2],
            '3C setting outside range: '..key)
        result[key]=value
    end
    return result
end
return Tuning
