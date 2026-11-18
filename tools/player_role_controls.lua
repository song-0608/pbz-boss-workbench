-- Add a primary shortcut only for a role with a natively accepted damage action.
-- This does not invent a normal-attack combo or mark a new ability as verified.
local Controls={}
local primary={['057_wanjun']='skill_01',['073_yanqiansui']='skill_01',
    ['056_youlong']='skill_01',['058_maddoctor']='skill_01'}
function Controls.apply(config,profile)
    local id=primary[profile.id]
    if not id then return config end
    assert(not config.skills.primary_attack,'primary shortcut already present')
    local d=assert(profile.skills[id],'primary ability absent')
    assert(d.binding_verified==true and d.activation_runtime_verified==true and d.natural_completion_verified==true
        and d.cancellation_runtime_verified==true and d.gameplay_verified==true,
        'primary shortcut requires accepted native damage and cancellation')
    config.skills.primary_attack={id=id,key='LEFT_MOUSE_BUTTON',
        name='主攻击：'..d.name,verified=true}
    return config
end
return Controls
