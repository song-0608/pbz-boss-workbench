"""用途：从实际日志和收尾报告记录首个控制里程碑，保留未完成标记，不用模拟结果冒充实机。"""
from datetime import datetime
import json
from pathlib import Path
import re
import csv

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'evidence/official-validation/20261113-101145'


def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    log=(WORK/'UE4SS.log').read_text(encoding='utf-8-sig')
    parts=log.split('PBZ_CONTROL_LIFECYCLE:DEFERRED_ACTOR=')[1:]
    motion=next((p for p in parts if 'PBZ_CONTROL_LIFECYCLE:MOVEMENT_DELTA_XY=' in p), '')
    interactive=next((p for p in reversed(parts) if 'PBZ_CONTROL_LIFECYCLE:INTERACTIVE_READY=' in p), '')
    number=re.search(r'MOVEMENT_DELTA_XY=([0-9.]+)',motion)
    delta=float(number[1]) if number else None
    checks={
        'identity_name_from_asset':'PBZ_CONTROL_CONTRACT:CHARACTER_NAME=新娘阿花' in log,
        'temporary_actor_spawned':bool(parts),
        'native_possession_and_restore':all(t in motion for t in ('TAKEOVER=true|','RESTORE=true|','PLAYER_PAWN_RESTORED=BP_Renewal_Hun_C')),
        'position_changed':delta is not None and delta>0,
        'first_skill_activated_and_finished':all(t in motion for t in ('SKILL_START=true|','SKILL_FINISHED_NATURALLY=true')),
        'f6_enter': 'enter success=true state=ACTIVE' in interactive,
        'w_observed_by_input_driver':'W_KEY_OBSERVED=true' in interactive,
        'f1_skill': 'slot1 success=true state=ACTIVE' in interactive,
        'automatic_restore_and_cleanup':all(t in interactive for t in ('stop success=true state=OFF','DESTROY_REQUESTED=true','INTERACTIVE_END=')),
    }
    if not all(checks.values()):raise RuntimeError('Required milestone evidence is incomplete')
    post=json.loads((ROOT/'evidence/latest-native-diagnostic-postcheck.json').read_text(encoding='utf-8'))
    if not post['research_box_empty'] or post['formal_files_changed'] or not post['research_loader_removed']:
        raise RuntimeError('Cleanup and unchanged formal files required before recording milestone')
    result={'at':datetime.now().astimezone().isoformat(),'checks':checks,'minimal_control_loop_verified':True,
        'boss_control_verified':False,'full_player_release_ready':False,'movement_delta_xy_game_units':delta,
        'granted_ability_count_observed':37,'camera_visual_verified':False,'camera_issue':'Camera clips inside the boss model; third-person camera not accepted',
        'f10_physical_key_verified':False,'skill_damage_targeting_verified':False,'skill_cancellation_runtime_verified':False,
        'source_log':str(WORK/'UE4SS.log'),'postcheck':str(ROOT/'evidence/latest-native-diagnostic-postcheck.json'),
        'formal_changed_count':0,'formal_files_checked':post['formal_file_count'],
        'readme':str(ROOT/'31-阿花最小控制原型实测.md')}
    target=ROOT/'evidence/adaptation/ahua-minimal-control-milestone.json';save(target,result)
    updates={'status':'pbz-ahua-minimal-control-camera-pending','boss_identity_verified':True,
        'status_summary':'阿花最小操控原型已实机通过：临时生成、接管、移动、技能01及恢复；镜头穿模，完整玩家版未交付。',
        'blocked_reason':'当前首要问题为第三人称镜头；F10物理键、技能伤害/目标和中断、完整角色生命周期仍待验收。',
        'native_control_bridge_implemented':True,'boss_minimal_control_loop_verified':True,'boss_control_verified':False,
        'boss_camera_visual_verified':False,'first_skill_native_activation_verified':True,'first_skill_natural_completion_verified':True,
        'input_binding_status':'F6_W_F1_isolated_probe_passed_F10_pending','runtime_launch_allowed':False,
        'real_bridge_available':False,'research_loader_currently_deployed':False,'research_loader_removed':True,
        'latest_control_milestone':str(target),'latest_result_note':result['readme'],
        'latest_formal_file_check_at':post['checked_at'],'latest_formal_file_check_changed_count':0,
        'blocking_items':['第三人称跟随镜头、旋转和碰撞：实机存在模型内视角','F10物理键、主动中断、死亡切图及长期稳定性验收','第一招伤害/碰撞/目标选择，然后扩充完整技能和角色选择','玩家版入口、安装卸载和使用清单'],
        'next_action':'先修阿花第三人称镜头并合并验收F10、中断和目标选择；不再探图或重复未受影响的存档隔离测试。',
        'note':'最小控制原型已实机通过；镜头有明确缺陷，正式入口保持禁用，未声称完整Mod完成。'}
    for path in (ROOT/'项目状态.json',ROOT.parent/'profiles/pbz-offline.json'):
        data=json.loads(path.read_text(encoding='utf-8'));data.update(updates);save(path,data)
    abilities=re.findall(r'PBZ_CONTROL_LIFECYCLE:GRANTED_ABILITY=([^\r\n]+)',interactive)
    with (ROOT/'32-阿花能力清单-非全部可玩.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['序号','真实能力类','原型按键','验收状态'])
        for index,name in enumerate(dict.fromkeys(abilities),1):
            first=name.endswith('/GA_AHua_Skill_01.GA_AHua_Skill_01_C')
            writer.writerow([index,name,'F1（仅限时实验）' if first else '',
                '激活和自然结束通过；伤害与目标待验收' if first else '只确认已授予；未绑定按键；含被动工具和子技能'])
    path=ROOT/'26-待集中修复与复测.csv'
    with path.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream))
    replacements={
        'BOSS-001':['BOSS-001','身份识别','阿花资源及活体身份需核对','已实机确认','后续仅按已确认角色配置扩展','不再以探图定位为主线','evidence/adaptation/ahua-minimal-control-milestone.json'],
        'CONTROL-001':['CONTROL-001','玩法桥接','最小控制链已通过但镜头穿入模型','原型通过；正式入口禁用','先修第三人称镜头；合并F10中断和生命周期验收','最小原型不是完整玩家版','31-阿花最小控制原型实测.md'],
    }
    rows=[replacements.get(row[0],row) for row in rows]
    with path.open('w',encoding='utf-8-sig',newline='') as stream:csv.writer(stream).writerows(rows)
    path=ROOT/'02-玩家按键表-未实现.csv'
    with path.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream))
    for row in rows[1:]:
        if row[1]=='F6':row[0]='限时研究原型实测';row[-1]='接管临时阿花通过；当前会话已结束，正常游戏无此功能'
        elif row[1]=='F1':row[0]='限时研究原型实测';row[3]='GA_AHua_Skill_01';row[-1]='仅研究原型激活通过；完整伤害和目标未验收，正式入口禁用'
        elif row[1]=='WASD':row[0]='部分实测';row[-1]='W逐帧读取通过；自动方向输入有真实位移，其他按键尚未逐项验收'
        elif row[1]=='鼠标移动':row[0]='未通过';row[-1]='镜头穿入阿花模型；独立第三人称跟随和碰撞待修'
    with path.open('w',encoding='utf-8-sig',newline='') as stream:csv.writer(stream).writerows(rows)
    print('Actual Ahua control milestone recorded; full release remains incomplete; formal changed count: 0.')


if __name__=='__main__':main()
