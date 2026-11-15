"""用途：仅在本轮实机日志、人工画面复核与收尾检查齐全时，记录镜头里程碑并更新工作台。"""
import argparse
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import official_validation as v


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--visual-reviewed',action='store_true')
    args=parser.parse_args()
    if not args.visual_reviewed:raise RuntimeError('Review actual third-person screenshots first')
    state=json.loads(v.state_path().read_text(encoding='utf-8'))
    work=Path(state['work'])
    post=json.loads((v.ROOT/'evidence/latest-native-diagnostic-postcheck.json').read_text(encoding='utf-8'))
    if post['validation_state']!=str(v.state_path()) or not state.get('restored') or not post['research_box_empty'] or post['formal_files_changed'] or not post['research_loader_removed']:
        raise RuntimeError('Matching completed cleanup and unchanged formal files required')
    control=(work/'camera-control-batch.log').read_text(encoding='utf-8')
    look=(work/'camera-look-batch.log').read_text(encoding='utf-8')
    full=(work/'UE4SS.log').read_text(encoding='utf-8-sig')
    checks={
        'native_camera_contract':json.loads((work/'camera-native-contract.json').read_text(encoding='utf-8'))['passed'],
        'camera_binding_recorded':(work/'camera-binding.json').is_file(),
        'f6_possession':'enter success=true state=ACTIVE' in control,
        'first_skill_keyboard_activation':'slot1 success=true state=ACTIVE' in control,
        'first_skill_cancel_during_active':all(s in control for s in ('CANCEL_ACTIVE_BEFORE=1','CANCEL_RESULT=true|active=0')),
        'f10_keyboard_restoration':'exit success=true state=OFF' in control,
        'look_and_w_exercise':'W_KEY_OBSERVED=true' in look and (work/'camera-look-inputs.json').is_file(),
        'collision_retraction_observed':all(s in full for s in ('CAMERA_COLLISION_FIX=true','CAMERA_COLLISION_FIX=false')),
        'bounded_experiment_finished':'stop success=true state=OFF' in full and 'INTERACTIVE_END=' in full,
    }
    if not all(checks.values()):raise RuntimeError('Incomplete evidence: '+repr(checks))
    yaw=[float(x)for x in re.findall(r'CAMERA_CONTROL_YAW=([-0-9.]+)',look)]
    arm=[float(x)for x in re.findall(r'CAMERA_ARM_YAW=([-0-9.]+)',look)]
    if len(yaw)<2 or len(yaw)!=len(arm) or any(abs((a-b+180)%360-180)>.01 for a,b in zip(yaw,arm)):
        raise RuntimeError('Camera rotation evidence mismatch')
    inputs=json.loads((work/'camera-look-inputs.json').read_text(encoding='utf-8'))
    if not any(x.get('pressed')=='control_look' for x in inputs):raise RuntimeError('Missing physical mouse exercise')
    positions=re.findall(r'CAMERA_COMPONENT_POSITION=([^\r\n]+)',look)
    rendered=re.findall(r'CAMERA_RENDERED_POSITION=([^\r\n]+)',look)
    checks['rendered_camera_matches_component']=len(positions)>=2 and len(positions)==len(rendered) and all(a==b for a,b in zip(positions,rendered))
    if not checks['rendered_camera_matches_component']:raise RuntimeError('Latest rendered camera observations mismatch')
    screenshots=['camera-active-preview.png','camera-after-look-move-preview.png','camera-after-exit-preview.png']
    result={'at':datetime.now().astimezone().isoformat(),'session':str(work),'checks':checks,
        'camera_visual_reviewed':True,'camera_visual_verified':True,'f10_physical_key_verified':True,
        'first_skill_cancellation_runtime_verified':True,'skill_damage_targeting_verified':False,
        'camera_component_unregister_verified':False,'full_player_release_ready':False,
        'cleanup_note':'Destroy calls completed; camera and boom still queryable after 0.5s. Unregistration/GC remains unverified. Research process has ended.',
        'screenshot_sha256':{name:hashlib.sha256((work/name).read_bytes()).hexdigest()for name in screenshots},
        'source_log_sha256':hashlib.sha256((work/'UE4SS.log').read_bytes()).hexdigest(),
        'granted_counts_observed':sorted({int(x)for x in re.findall(r'GRANTED_COUNT=(\d+)',full)}),
        'formal_files_checked':post['formal_file_count'],'formal_changed_count':0,'research_box_empty':True,
        'local_fixture_report':str(v.ROOT/'evidence/adaptation/control-runtime-local-checks.json')}
    target=v.ROOT/'evidence/adaptation/ahua-camera-control-milestone.json';v.save(target,result)
    summary='阿花第三人称镜头、鼠标转向、F6/W/F1及出招中F10恢复已实机通过；完整目标伤害与生命周期仍待完成。'
    updates={
        'updated_at':result['at'],'status':'pbz-ahua-camera-and-skill-cancel-passed','status_summary':summary,
        'target':'新娘阿花（真实资源与临时战斗实例已确认）',
        'blocked_reason':'下一步为敌我关系、目标与完整伤害；摄像机组件注销、技能遗留效果及死亡切图清理仍待验收。',
        'boss_camera_visual_verified':True,'f10_physical_key_verified':True,'first_skill_cancellation_runtime_verified':True,
        'camera_component_unregister_verified':False,'boss_control_verified':False,'runtime_launch_allowed':False,
        'input_binding_status':'F6_W_mouse_F1_F10_bounded_offline_probe_passed',
        'latest_camera_milestone':str(target),'latest_result_note':str(v.ROOT/'33-阿花镜头与技能退出实测.md'),
        'latest_camera_screenshot':str(work/'camera-after-look-move-preview.png'),
        'next_action':'修复Boss敌我与目标选择，验收首招命中/伤害；集中处理组件与技能效果清理，再扩技能和玩家入口。',
        'blocking_items':['敌我与目标选择，第一招对指定敌人的真实命中/伤害','摄像机组件注销、技能遗留效果、死亡切图与长期稳定性','其余技能逐项验收、玩家入口及安装卸载'],
        'not_done':['敌我、目标、完整伤害与命中','其余技能、连段与阶段条件','组件注销和技能效果、死亡切图及长期生命周期','玩家入口、Boss选择、按键提示和安装卸载'],
        'official_validation_active':False,'research_loader_currently_deployed':False,'research_loader_removed':True,
        'latest_formal_file_check_at':post['checked_at'],'latest_formal_file_check_changed_count':0,
        'note':'镜头与首招中断通过属于有界实机原型；完整可玩Mod尚未交付。'}
    for path in (v.ROOT/'项目状态.json',v.ROOT.parent/'profiles/pbz-offline.json'):
        if path.is_file():
            data=json.loads(path.read_text(encoding='utf-8'));data.update(updates)
            if 'completed'in data and summary not in data['completed']:data['completed'].append(summary)
            v.save(path,data)
    # 用途：历史报告保留，统一入口指向新结果，避免旧“镜头未修”继续被当作当前状态。
    banner='> 最新进展：第三人称镜头、鼠标转向、F10与技能01主动中断已实机通过。当前结果见[第33号说明](33-阿花镜头与技能退出实测.md)；完整玩家版仍在开发。\n\n'
    for name in ('00-项目目标与现状.md','01-实施清单.md','30-Boss可玩Mod交付目标.md','31-阿花最小控制原型实测.md'):
        path=v.ROOT/name;old=path.read_text(encoding='utf-8-sig')
        if not old.startswith(banner):path.write_text(banner+old,encoding='utf-8')
    (v.ROOT/'04-当前结果与下一关.md').write_text('# 当前结果与下一关\n\n'+summary+'\n\n双击“打开研究工作台.cmd”：6查看最新实测，8查看第三人称截图，9运行本地回归，不启动游戏。\n\n先读[第33号实测](33-阿花镜头与技能退出实测.md)，源码在mod/PBZBossControl/Scripts，简历素材在[第34号](34-简历与面试素材-开发中.md)。\n\n正式入口仍禁用；正常游戏不能使用实验键位。下一步先处理敌我、目标与首招完整伤害，再批量扩招式和玩家版入口。\n\n本轮结束：56个已检查正式文件无变化，研究箱为空、加载器撤除，没有回写或回档。\n',encoding='utf-8')
    key_path=v.ROOT/'02-玩家按键表-未实现.csv'
    with key_path.open(encoding='utf-8-sig',newline='')as stream:
        reader=csv.DictReader(stream);key_fields=reader.fieldnames;key_rows=list(reader)
    for row in key_rows:
        if row['拟定按键']=='F10':
            row.update({'状态':'限时研究原型实测','当前备注':'技能01活动中F10取消并恢复主角通过；仅限时实验有效，正式入口禁用'})
        elif row['拟定按键']=='鼠标移动':
            row.update({'状态':'限时研究原型实测','当前备注':'独立第三人称跟随、真实鼠标转向与有限场景避让通过；组件注销及长期运行待验收'})
        elif row['拟定按键']=='F1':
            row['当前备注']='真实按键激活及活动中F10取消通过；自然结束有历史证据，目标和完整伤害未验收'
    with key_path.open('w',encoding='utf-8-sig',newline='')as stream:
        writer=csv.DictWriter(stream,fieldnames=key_fields);writer.writeheader();writer.writerows(key_rows)
    # 用途：最新活体的能力清单按原顺序保存；动态授予数量会变化，不称作已支持招式。
    latest=full.rsplit('PBZ_CONTROL_LIFECYCLE:DEFERRED_ACTOR=',1)[-1]
    abilities=re.findall(r'PBZ_CONTROL_LIFECYCLE:GRANTED_ABILITY=[^ ]+ ([^\r\n]+)',latest)
    with (v.ROOT/'35-阿花技能验收矩阵-非发布键位.csv').open('w',encoding='utf-8-sig',newline='')as stream:
        writer=csv.writer(stream)
        writer.writerow(['序号','真实资源类','已授予样本','原型按键','激活','自然结束','主动中断','敌方目标与完整伤害','玩家版发布','备注'])
        for index,path in enumerate(abilities,1):
            first=path.endswith('/GA_AHua_Skill_01.GA_AHua_Skill_01_C')
            writer.writerow([index,path,'本轮最新活体中已读取','F1（仅实验）'if first else '未绑定',
                '实机通过'if first else '未验收','历史实机通过'if first else '未验收',
                'F10实机通过'if first else '未验收','未验收','否','包含被动/工具/动态能力；内部资源名不是面向玩家的招式名称'])
    issue_path=v.ROOT/'26-待集中修复与复测.csv'
    with issue_path.open(encoding='utf-8-sig',newline='')as stream:
        reader=csv.DictReader(stream);fields=reader.fieldnames;rows=list(reader)
    for row in rows:
        if row['编号']=='CONTROL-001':row.update({'真实问题或现象':'镜头穿模修复；F10及技能01中断已通过','当前状态':'最小链与镜头通过；正式入口禁用','下一项工作':'目标/敌我/完整伤害及长期生命周期','证据':'33-阿花镜头与技能退出实测.md'})
    additions=[('TARGET-001','玩法目标','Boss仍保留敌方身份，可能攻击原主角；技能效果有残留','待修复','核对敌我与目标接口，再验证首招完整伤害'),
        ('CAMERA-002','生命周期','销毁请求后0.5秒相机与臂仍可查询；注销和GC未核对','待验收','核对原生销毁/注销状态，不把IsValid当作存活证明'),
        ('SKILL-002','技能扩展','最新活体有38项能力，不等于38招可玩','待验收','依照第35号矩阵逐项验证后绑定按键')]
    for key,category,problem,status,next_step in additions:
        if not any(row['编号']==key for row in rows):rows.append(dict(zip(fields,[key,category,problem,status,next_step,'仅限离线研究副本，不修改正式进度','33-阿花镜头与技能退出实测.md'])))
    with issue_path.open('w',encoding='utf-8-sig',newline='')as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    print(json.dumps({'report':str(target),'checks':checks,'full_player_release_ready':False},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
