"""封存玩家入口、可见目标和World退役的实机结果；不把部分通过升级为完整发布。"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
from control_action_evidence import restoration_result, world_retirement_result, cancellation_result

ROOT=Path(__file__).resolve().parents[1]

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    pending=path.with_suffix('.pending');pending.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');pending.replace(path)

def closed(name):
    work=ROOT/'evidence/official-validation'/name
    post=read(work/'postcheck.json')
    if (not post['validation_restored']or not post['research_box_empty']or not post['research_loader_removed']
        or post['formal_files_changed']or post['host_config_files_changed']or not post['host_registry_unchanged']):
        raise RuntimeError('Matching clean closure required: '+name)
    log=work/'UE4SS.log'
    return work,post,log.read_text(encoding='utf-8',errors='replace'),hashlib.sha256(log.read_bytes()).hexdigest()

def main():
    now=datetime.now().astimezone();stamp=now.strftime('%Y%m%d-%H%M%S')
    checks=read(ROOT/'evidence/adaptation/ahua-delivery-local-checks.json')
    if not checks['passed']:raise RuntimeError('Passing current source checks required')
    for path,expected in checks['source_sha256'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=expected:raise RuntimeError('Source changed after tests: '+path)
    work,post,text,digest=closed('20261113-225027')
    world_work,world_post,world_text,world_digest=closed('20261113-223316')
    start=text.rfind('PBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT=1')
    segment=text[start:]
    deployment=read(work/'control-lifecycle-deployment.json')
    required=('NAVIGATION_TARGET_VISIBILITY_VERIFIED=2','PLAYER_ENTRY_READY=ahua_guitoudao',
              '[PBZBossControl] enter success=true state=ACTIVE','[PBZBossControl] target verified: ',
              'KEY_SKILL_END=skill_01|peak=1|active=0|natural=true|health_before=9000.0|health_after=8850.0')
    keys=re.findall(r'PLAYER_BINDING=(\w+)\|(\w+)\|([\w_]+)',segment)
    ordinary=(deployment['player_entry']and deployment['arena_navigation_trial']and not any(deployment[k]
        for k in ('scene_transition_trial','skill_lab','expanded','player_key_trial','death_trial')))
    player_pass=(ordinary and len(keys)==10 and len({r[1]for r in keys})==9
        and all(token in segment for token in required)and restoration_result(segment,'exit')['passed'])
    heavy=cancellation_result(text,'heavy_01')
    old=world_retirement_result(world_text)
    if not player_pass or not heavy:raise RuntimeError('Required current milestone evidence missing; preserve project status and do not release')
    report={'at':now.isoformat(),'normal_player_entry_passed':player_pass,
        'supported_ability_count':len({r[1]for r in keys}),'actual_binding_count':len(keys),
        'same_world_navigation_and_visible_targets_verified':player_pass,
        'visible_target_cycle_verified':player_pass,'normal_primary_attack_damage_verified':player_pass,
        'heavy01_active_f10_cancellation_verified':heavy,
        'skill02_active_f10_cancellation_verified':cancellation_result(text,'skill_02'),
        'old_world_retirement':old,'post_world_retakeover_passed':False,
        'native_openlevel_trial_rejected_for_normal_use':True,
        'world_trial_limitation':'Old World and owned actors disposed; direct map load left the new player falling. Menu return/continue did not recover a stationary player. No new takeover was permitted.',
        'source_checks':{'count':len(checks['checks']),'passed':True,'source_sha256':checks['source_sha256']},
        'sessions':[{ 'path':str(work),'log_sha256':digest,'formal_files_changed':post['formal_files_changed']},
                    {'path':str(world_work),'log_sha256':world_digest,'formal_files_changed':world_post['formal_files_changed']}],
        'raw_failed_actions_preserved':True,'complete_mod':False,'stable_release_created':False}
    save(ROOT/'evidence/adaptation/player-entry-milestone.json',report)
    status_path=ROOT/'项目状态.json';archive=ROOT/'evidence/status-history'/('player-entry-'+stamp)
    archive.mkdir(parents=True,exist_ok=True);shutil.copy2(status_path,archive/status_path.name)
    status=read(status_path)
    status.update(updated_at=now.isoformat(),status_summary='阿花普通玩家入口、9能力10绑定、状态层、导航与可见目标切换通过；整Mod仍有未验收项',
        awaiting_user=None,no_remaining_pbz_processes_verified=True,no_loader_deployment=True,
        latest_result_note=str(ROOT/'48-玩家入口与跨场景清理-开发中.md'),
        latest_player_entry_milestone=str(ROOT/'evidence/adaptation/player-entry-milestone.json'))
    additions=[
        '玩家main入口实测：角色选择配置、9能力10绑定、F6、可见目标F7、左键技能01真实伤害及F10完整恢复通过',
        '只读Windows状态层实机显示生命、目标、遮挡状态与实际键位；不是引擎Canvas HUD',
        '当前构建导航投影、同层分离落点和生成后双目标视线核对实机通过，普通入口默认启用',
        '重击01真实ActiveCount=1时F10取消归零，主角位置偏移0、新活动0、镜头清理通过',
        'ACTIVE原生载图时旧World和已修改对象退役、自建6对象回收通过；新场景持续下落被拒绝接管，不算完整跨World闭环']
    for item in additions:
        if item not in status['completed']:status['completed'].append(item)
    status['not_done']=[
        'Attack_01原生连招及其余适用招式、阶段条件',
        '真实血量耗尽与对象销毁瞬间仍有活动技能的恢复',
        'ACTIVE跨World后正常游戏加载与新场景重新接管完整闭环',
        '跨多种地形的导航生成稳定性',
        '组件GC确认、长时间运行与完整发布验收',
        '其他Boss']
    status['blocked_reason']='; '.join(status['not_done'])
    save(status_path,status)
    print(json.dumps({k:report[k]for k in('normal_player_entry_passed','heavy01_active_f10_cancellation_verified','actual_binding_count','complete_mod')},ensure_ascii=False))

if __name__=='__main__':main()
