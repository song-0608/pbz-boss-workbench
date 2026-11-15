"""用途：读取玩家可编辑的按键表；只生成固定结构的Lua数据，不执行用户输入的代码。"""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CONTROLS={'enter','exit','cycle_target'}
SKILLS={'primary_attack','slot1','heavy_01','skill_02','dash','skill_06','skill_08',
        'skill_07','teleport_left','teleport_right'}
OPTIONAL_SKILLS={'native_combo','skill_04','skill_07_hard','special_03_flower',
                 'special_03_flower_cd','special_02_new','special_07','heavy_02','special_03','skill_06_hard','skill_09','homing_flower','homing_flower_hard',
                 'special_move_01','special_move_back','special_move_left','special_move_right','special_05_a','special_11'}
OPTIONAL_DEFAULTS={'native_combo':'R','skill_04':'ONE','skill_07_hard':'TWO',
                   'special_03_flower':'THREE','special_03_flower_cd':'FOUR',
                   'special_02_new':'FIVE','special_07':'SIX','heavy_02':'SEVEN','special_03':'EIGHT',
                   'skill_06_hard':'NINE','skill_09':'T','homing_flower':'Z','homing_flower_hard':'X',
                   'special_move_01':'C','special_move_back':'V','special_move_left':'B','special_move_right':'G',
                   'special_05_a':'H','special_11':'SPACE'}
ALLOWED=({f'F{i}' for i in range(1,13)}-{'F11'})|{'Q','E','R','T','Z','X','C','V','B','G','H',
        'ONE','TWO','THREE','FOUR','FIVE','SIX','SEVEN','EIGHT','NINE',
        'SPACE','LEFT_MOUSE_BUTTON','RIGHT_MOUSE_BUTTON','MIDDLE_MOUSE_BUTTON'}


def ability_for_slot(slot):
    if slot not in SKILLS | OPTIONAL_SKILLS:
        raise ValueError('Unregistered player skill slot')
    return {'primary_attack':'skill_01','slot1':'skill_01','native_combo':'attack_01'}.get(slot,slot)

def validate(data):
    # 用途：WASD、Esc、系统组合键不纳入可改列表；重复绑定在写入游戏前就明确报错。
    if not isinstance(data,dict) or set(data)!={'controls','skills'}:
        raise ValueError('键位文件必须包含controls和skills两组')
    found={}
    for group,required in (('controls',CONTROLS),('skills',SKILLS)):
        values=data[group]
        valid_fields=(isinstance(values,dict)and(required<=set(values)<=required|OPTIONAL_SKILLS if group=='skills'else set(values)==required))
        if not valid_fields:
            raise ValueError('键位项目缺少或包含未知项：'+group)
        effective_values={**OPTIONAL_DEFAULTS,**values}if group=='skills'else values
        for action,key in effective_values.items():
            if key=='INS':
                raise ValueError('Insert 为 Boss 工作台保留，请为 '+action+' 选择其他按键')
            if key=='F11':
                raise ValueError('F11 为游戏窗口热键保留，Boss 工作台使用 Insert，请为 '+action+' 选择其他按键')
            if not isinstance(key,str) or key not in ALLOWED:
                raise ValueError('不支持的按键：'+group+'.'+action)
            if key in found:
                raise ValueError('重复按键：'+key+'，用于'+found[key]+'和'+action)
            found[key]=action
    return data

def read():
    return effective(json.loads((ROOT/'玩家键位.json').read_text(encoding='utf-8-sig')))


def effective(data):
    """旧配置遗漏的新动作仍使用目录默认键；编辑器和冲突检查显示同一组实际键。"""
    validate(data)
    return {'controls':dict(data['controls']),'skills':{**OPTIONAL_DEFAULTS,**data['skills']}}

def lua(data):
    data=effective(data)
    return '{'+','.join(group+'={'+','.join(name+'='+json.dumps(key) for name,key in sorted(data[group].items()))+'}'
                        for group in ('controls','skills'))+'}'
