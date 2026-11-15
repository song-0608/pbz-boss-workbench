-- 用途：开发专用候选技能试验台；F9选择、F8试放，和玩家默认键位分开。
-- “绑定已核对”只说明本次活体确实拥有该能力，不代表招式或伤害已验收。
local Lab = {}
Lab.__index = Lab
local base = '/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/'
Lab.candidates = {
    { id='attack_01', asset='New/GA_AHua_Attack_01', name='候选普攻01', disabled=true,
      reason='实机反射确认为RunSubtreeAbility连招调度入口，非独立普攻；曾不结束且取消失败，保持隔离' },
    { id='skill_04', asset='New/GA_AHua_Skill_04', name='候选技能04' },
    { id='skill_06', asset='New/GA_AHua_Skill_06', name='候选技能06' },
    { id='special_05_a', asset='GA_AHua_Special_05_A', name='候选特殊05A' },
    -- 用途：来自Attack_01精确子树AbilityToActivate引用；仍须本次唯一授予、结束和伤害实测。
    { id='skill_08', asset='New/GA_AHua_Skill_08', name='子树叶招式08' },
    { id='skill_05_hard', asset='New/GA_AHua_Skill_05_Hard', name='子树叶招式05Hard' },
    { id='ca_01_teleport_redeye', asset='New/GA_AHua_CA_01_GEx_Teleport_RedEye', name='子树叶招式CA01' },
    { id='teleport_left', asset='New/GA_AHua_Teleport_Left', name='阿花左侧瞬移' },
    { id='teleport_right', asset='New/GA_AHua_Teleport_Right', name='阿花右侧瞬移' },
    { id='skill_07', asset='New/GA_AHua_Skill_07', name='候选技能07' },
    { id='skill_09', asset='New/GA_AHua_Skill_09', name='候选技能09' },
    -- 20261114-031228只读继承核对：以下为独立ActionAbility候选，不代表可玩通过。
    { id='heavy_02', asset='GA_AHua_Heavy_02', name='候选重击02' },
    { id='special_03', asset='GA_AHua_Special_03', name='候选特殊03' },
    { id='special_11', asset='GA_AHua_Special_11', name='候选特殊11' },
    { id='special_02_new', asset='GA_AHua_Special_02_New', name='候选特殊02' },
    { id='special_07', asset='GA_AHua_Special_07', name='候选特殊07' },
    { id='special_move_01', asset='GA_AHua_SpecialMove_01', name='候选位移01' },
    { id='special_move_back', asset='Child/GA_AHua_SpecialMove_B', name='候选后向位移' },
    { id='special_move_left', asset='Child/GA_AHua_SpecialMove_L', name='候选左向位移' },
    { id='special_move_right', asset='Child/GA_AHua_SpecialMove_R', name='候选右向位移' },
    { id='skill_06_hard', asset='New/GA_AHua_Skill_06_Hard', name='候选技能06强化' },
    { id='skill_07_hard', asset='New/GA_AHua_Skill_07_Hard', name='候选技能07强化' },
    { id='special_attack_12', asset='New/GA_AHua_SpecialAttack_12', name='候选特殊攻击12' },
    { id='special_03_flower', asset='Child/GA_AHua_Special_03_B_Flower', name='候选花朵03' },
    { id='special_03_flower_cd', asset='Child/GA_AHua_Special_03_B_Flower_CD', name='候选花朵03冷却变体' },
    { id='homing_flower',asset='New/GA_AHua_Homing_Flower',name='候选追踪花连招',disabled=true },
    { id='homing_flower_hard',asset='New/GA_AHua_Homing_Flower_Hard',name='候选追踪花强化连招',disabled=true },
}

function Lab.configure(profile, config, granted_paths, blocked_paths, scheduler_trial)
    -- 用途：只接受本次已授予列表的精确完整类名；重复授予也拒绝，不猜句柄。
    local counts, slots = {}, {}
    for _,path in ipairs(granted_paths) do counts[path]=(counts[path] or 0)+1 end
    for _,candidate in ipairs(Lab.candidates) do
        local class_name=assert(candidate.asset:match('([^/]+)$'))
        local path=base..candidate.asset..'.'..class_name..'_C'
        local explicit_combo=scheduler_trial==true and(candidate.id=='attack_01'or require('subtree_contracts')[candidate.id]~=nil)
        if counts[path]==1 and (not candidate.disabled or explicit_combo) and not(blocked_paths and blocked_paths[path])then
            local slot='lab_'..candidate.id
            if profile.skills[candidate.id] then
                assert(profile.skills[candidate.id].class_path==path,'candidate conflicts with player profile')
            else
                profile.skills[candidate.id]={name=candidate.name,class_path=path,binding_verified=true,
                    active_count_field='ActiveCount',cancel_binding_verified=true,
                    cancel_function='K2_CancelAbility',requires_target=true,gameplay_verified=false}
            end
            config.skills[slot]={id=candidate.id,verified=true,lab_only=true}
            slots[#slots+1]=slot
        end
    end
    assert(#slots>0,'no unique granted candidate skills; lab remains unavailable')
    config.skill_lab={next_key='F9',cast_key='F8',slots=slots}
    return slots
end

function Lab.new(session, slots)
    assert(type(slots)=='table' and #slots>0,'candidate slots required')
    local seen={}
    for _,slot in ipairs(slots) do
        local d=session.config.skills[slot]
        assert(not seen[slot] and d and d.verified==true and d.lab_only==true
            and type(d.id)=='string' and d.id~='','invalid candidate slot')
        seen[slot]=true
    end
    return setmetatable({session=session,slots=slots,index=1},Lab)
end

function Lab:selected() return self.slots[self.index] end

function Lab:next()
    -- 用途：技能中禁止更换，保证日志里的选中项始终对应本次真实出招。
    local s=self.session
    if s.state~='ACTIVE' then return false,'not controlling a boss' end
    if s.current_skill or s.pending_target then return false,'finish skill/target change before selecting' end
    self.index=self.index % #self.slots+1
    return true,s.config.skills[self:selected()].id
end

function Lab:cast()
    -- 用途：复用现有冷却、真实目标、离线构建和退出恢复逻辑，不直接调用未知接口。
    return self.session:skill(self:selected())
end

return Lab
