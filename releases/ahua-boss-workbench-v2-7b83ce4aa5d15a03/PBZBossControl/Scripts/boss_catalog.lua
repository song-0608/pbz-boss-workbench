-- 用途：玩家入口只展示登记的角色，以独立配置的真实验收字段装配技能；未登记Boss不能靠改字符串启用。
local Catalog = {}
local entries = {
    {id='ahua_guitoudao',name='新娘阿花',profile='profiles.ahua',abilities=28,bindings_count=29},
    {id='057_wanjun',name='巨锤客：万钧',profile='profiles.wanjun',bindings='profiles.wanjun_bindings',abilities=4,bindings_count=4},
    {id='056_youlong',name='发狂的水行帮主：游龙',profile='profiles.youlong',bindings='profiles.youlong_bindings',abilities=4,bindings_count=4},
}
local bindings = {
    {slot='slot1',id='skill_01',key='F1'},
    {slot='heavy_01',id='heavy_01',key='F2'},
    {slot='skill_02',id='skill_02',key='F3'},
    {slot='dash',id='dash',key='F4'},
    {slot='skill_06',id='skill_06',key='F5'},
    {slot='skill_08',id='skill_08',key='F8'},
    {slot='skill_07',id='skill_07',key='F9'},
    {slot='teleport_left',id='teleport_left',key='Q'},
    {slot='teleport_right',id='teleport_right',key='E'},
    {slot='primary_attack',id='skill_01',key='LEFT_MOUSE_BUTTON'},
    {slot='native_combo',id='attack_01',key='R',requires_player_key=true},
    {slot='skill_04',id='skill_04',key='ONE',requires_cancel=true},
    {slot='skill_07_hard',id='skill_07_hard',key='TWO',requires_cancel=true},
    {slot='special_03_flower',id='special_03_flower',key='THREE',requires_cancel=true},
    {slot='special_03_flower_cd',id='special_03_flower_cd',key='FOUR',requires_cancel=true},
    {slot='special_02_new',id='special_02_new',key='FIVE',requires_cancel=true},
    {slot='special_07',id='special_07',key='SIX',requires_cancel=true},
    {slot='heavy_02',id='heavy_02',key='SEVEN',requires_cancel=true},
    {slot='special_03',id='special_03',key='EIGHT',requires_cancel=true},
    {slot='skill_06_hard',id='skill_06_hard',key='NINE',requires_cancel=true},
    {slot='skill_09',id='skill_09',key='T',requires_cancel=true},
    {slot='homing_flower',id='homing_flower',key='Z',requires_cancel=true,requires_scheduler=true},
    {slot='homing_flower_hard',id='homing_flower_hard',key='X',requires_cancel=true,requires_scheduler=true},
    {slot='special_move_01',id='special_move_01',key='C',requires_cancel=true},
    {slot='special_move_back',id='special_move_back',key='V',requires_cancel=true},
    {slot='special_move_left',id='special_move_left',key='B',requires_cancel=true},
    {slot='special_move_right',id='special_move_right',key='G',requires_cancel=true},
    {slot='special_05_a',id='special_05_a',key='H',requires_cancel=true},
    {slot='special_11',id='special_11',key='SPACE',requires_cancel=true},
}

function Catalog.list()
    local result={}
    for _,entry in ipairs(entries)do
        result[#result+1]={id=entry.id,name=entry.name,profile=entry.profile,
            abilities=entry.abilities,bindings_count=entry.bindings_count}
    end
    return result
end

function Catalog.profile(id)
    for _,entry in ipairs(entries)do
        if entry.id==id then return require(entry.profile),entry end
    end
    error('unsupported Boss profile: '..tostring(id))
end

function Catalog.configure(id, profile, keymap)
    local selected
    for _,entry in ipairs(entries)do if entry.id==id then selected=entry end end
    assert(selected and type(profile)=='table'and profile.id==id,'unknown or mismatched boss selection')
    assert(profile.identity_verified==true and type(profile.exe_sha256)=='string','verified boss identity required')
    local config={expected_exe_sha256=profile.exe_sha256,boss_id=id,boss_display_name=selected.name,
        controls={enter='F6',exit='F10',menu_exit='ESCAPE',cycle_target='F7'},skills={}}
    local selected_bindings=selected.bindings and require(selected.bindings)or bindings
    for _,row in ipairs(selected_bindings)do
        local definition=assert(profile.skills[row.id],'catalog skill absent from profile: '..row.id)
        if not row.requires_player_key or definition.player_key_verified==true then
        if row.requires_cancel then
            assert(definition.cancellation_runtime_verified==true,'catalog skill lacks cancellation evidence: '..row.id)
        end
        if row.id=='attack_01'or row.requires_scheduler then
            assert(definition.scheduler_runtime_verified==true and definition.cancellation_runtime_verified==true,
                'native combo lacks scheduler/cancellation evidence')
        end
        assert(definition.binding_verified==true and definition.activation_runtime_verified==true
            and definition.natural_completion_verified==true
            and (definition.gameplay_verified==true or definition.movement_runtime_verified==true),
            'catalog skill lacks gameplay evidence: '..row.id)
        if row.slot=='primary_attack'then
            assert(profile.input and profile.input.primary_attack_key_verified==true,'primary attack shortcut unverified')
        end
        config.skills[row.slot]={id=row.id,key=row.key,name=definition.name,verified=true}
        end
    end
    if keymap then require('keymap').apply(config,keymap)end
    return config
end

return Catalog
