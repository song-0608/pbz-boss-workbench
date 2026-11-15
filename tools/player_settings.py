"""用途：玩家角色选择与键位编辑器共用的严格数据配置；只接受已登记角色。"""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BOSSES={'ahua_guitoudao':'新娘阿花','057_wanjun':'巨锤客：万钧','073_yanqiansui':'琴女烟千岁'}
LABELS={'enter':'开始操控','exit':'恢复主角','cycle_target':'切换目标','primary_attack':'主攻击快捷键（技能01）',
        'slot1':'技能01','heavy_01':'重击01','skill_02':'技能02','dash':'冲刺','skill_06':'技能06',
        'skill_08':'技能08','skill_07':'技能07','teleport_left':'左侧瞬移','teleport_right':'右侧瞬移','native_combo':'原生连招'}
DESCRIPTIONS={
    'special_move_01':'位移01：原生位移与自然结束、活动中F10取消通过；本轮没有观察到伤害。普通C键待验。',
    'special_move_back':'原生后向位移：实测位移、自然结束和活动中F10取消通过；需要可见目标，落点受地形影响。普通V键待验。',
    'special_move_left':'原生左向位移：实测位移、自然结束和活动中F10取消通过；需要可见目标，落点受地形影响。普通B键待验。',
    'special_move_right':'原生右向位移：实测位移、自然结束和活动中F10取消通过；需要可见目标，落点受地形影响。普通G键待验。',
    'special_05_a':'特殊05A：真实伤害、位移、自然结束和活动中取消通过；普通H键待验，命中受距离和地形影响。',
    'special_11':'特殊11：本轮观察到约890单位位移、自然结束和活动中取消；没有观察到伤害，按原生位移开放。普通空格键待验。',
    'homing_flower':'追踪花原生连招：真实伤害、完整父子自然结束和活动中取消通过；普通Z键自然结束及F10恢复已实测。',
    'homing_flower_hard':'强化追踪花原生连招：真实伤害、完整父子自然结束和活动中取消通过；普通X键自然结束及F10恢复已实测。',
    'heavy_02':'重击02：真实伤害、自然结束和活动中F10取消通过；普通7键自然结束及恢复已实测。',
    'special_03':'特殊03：真实伤害、自然结束和活动中F10取消通过；普通8键自然结束及恢复已实测。',
    'skill_06_hard':'技能06强化：真实伤害、自然结束和活动中F10取消通过；普通9键自然结束及恢复已实测。',
    'skill_09':'技能09：真实伤害、自然结束和活动中F10取消通过；普通T键自然结束及恢复已实测。',
    'skill_04':'技能04：实际伤害、自然结束及活动中F10取消已通过。需要可见目标；命中受距离和地形影响。',
    'skill_07_hard':'技能07强化：实际伤害、自然结束及活动中F10取消已通过。保留游戏原生冷却和状态限制。',
    'special_03_flower':'花朵03：实际伤害、自然结束及活动中F10取消已通过。需要有效可见目标。',
    'special_03_flower_cd':'花朵03变体：实际伤害、自然结束及活动中F10取消已通过。保留本变体的原生限制。',
    'special_02_new':'特殊02：有位移和实际伤害样本，活动中F10取消已通过；距离和地形会影响是否命中。',
    'special_07':'特殊07：有位移和实际伤害样本，活动中F10取消已通过；需要有效可见目标。',
    'native_combo':'原生Attack_01连招：保留游戏冷却、位移、招式选择和结束。默认R键实测自然结束、真实伤害及重招活动中F10取消。需要有效可见目标；命中受距离和地形影响。',
    'primary_attack':'与技能01使用同一真实能力；不是Attack_01连招。已观察目标掉血、自然结束与活动中取消。',
    'slot1':'技能01：需要有效敌对目标。已观察真实伤害、自然结束与活动中F10取消；命中受距离和地形影响。',
    'heavy_01':'重击01：需要有效敌对目标。真实激活、自然结束、配对掉血及活动中F10取消已通过。',
    'skill_02':'技能02：需要有效敌对目标。真实激活、自然结束、配对掉血及活动中F10取消已通过。',
    'dash':'冲刺：原生位移能力，实测约498单位并自然结束。距离受地形影响，不作为伤害招式。',
    'skill_06':'技能06：需要有效敌对目标。独立样本9000→8350并自然结束；不代表固定伤害或必定命中。',
    'skill_08':'技能08：从已核对的连招子树发现的独立叶招式。伤害、自然结束及活动中取消已通过；不是完整连招树。',
    'skill_07':'技能07：真实伤害、自然结束及活动中F10取消已通过。仍受游戏冷却和状态限制。',
    'teleport_left':'左侧瞬移：围绕有效目标的原生位移；自然结束及活动中取消已通过，落点受地形影响。',
    'teleport_right':'右侧瞬移：围绕有效目标的原生位移；自然结束及活动中取消已通过，落点受地形影响。',
    'enter':'接管前保存主角、输入、镜头与AI状态；只允许当前离线隔离会话中已核对的自建Boss。',
    'exit':'请求取消本Mod启动的能力，并恢复主角、输入和镜头；只有实际回读通过才记为恢复成功。',
    'cycle_target':'筛选同World、存活、真实敌对、30米内且视线可达的目标。出招中不能切换，切换结果等待真实回读。',
}
LABELS.update(skill_04='技能04',skill_07_hard='技能07强化',special_03_flower='花朵03',
              special_move_01='位移01',special_move_back='原生后向位移',special_move_left='原生左向位移',
              special_move_right='原生右向位移',special_05_a='特殊05A',special_11='特殊11位移',
              special_03_flower_cd='花朵03变体',special_02_new='特殊02',special_07='特殊07',
              heavy_02='重击02',special_03='特殊03',skill_06_hard='技能06强化',skill_09='技能09',
              homing_flower='追踪花连招',homing_flower_hard='强化追踪花连招')

def validate(data):
    if not isinstance(data,dict)or set(data)!={'boss_id'}or not isinstance(data['boss_id'],str)or data['boss_id']not in BOSSES:
        raise ValueError('只允许选择已登记并有独立配置的Boss')
    return data

def read():
    return validate(json.loads((ROOT/'玩家设置.json').read_text(encoding='utf-8-sig')))


def editor_skill_labels(boss_id):
    """这里只决定编辑器展示，不授予或启用任何运行时能力。"""
    validate({'boss_id':boss_id})
    if boss_id=='057_wanjun':
        return {'slot1':'万钧重锤攻击','heavy_01':'万钧左闪攻击',
                'skill_02':'万钧右闪攻击','dash':'万钧左侧攻击'}
    if boss_id=='073_yanqiansui':
        return {'slot1':'烟千岁特殊攻击03','heavy_01':'烟千岁特殊攻击04',
                'skill_02':'烟千岁技能03','dash':'烟千岁技能04'}
    import player_keymap
    return {slot:LABELS[slot]for slot in player_keymap.read()['skills']}

def save(path,data):
    pending=path.with_suffix('.pending')
    pending.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    pending.replace(path)
