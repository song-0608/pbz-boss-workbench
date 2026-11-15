"""用途：从本轮原始日志与收尾结果登记局部成果；不会启动游戏或将目标失败改为通过。"""
import hashlib
import json
from pathlib import Path
import official_validation as v

def main():
    s=json.loads(v.state_path().read_text(encoding='utf-8'));work=Path(s['work'])
    if not s.get('restored'):raise RuntimeError('Finish isolated session before recording delivery state')
    log=(work/'UE4SS.log').read_text(encoding='utf-8',errors='replace')
    post=json.loads((v.ROOT/'evidence/latest-native-diagnostic-postcheck.json').read_text(encoding='utf-8'))
    local=json.loads((v.ROOT/'evidence/adaptation/control-runtime-local-checks.json').read_text(encoding='utf-8'))
    if post['validation_state']!=s['state_file']:raise RuntimeError('Fresh matching postcheck required')
    sources={p.relative_to(v.ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (v.ROOT/'mod/PBZBossControl/Scripts').rglob('*.lua')}
    result={'at':v.utc8(),'session':s['state_file'],'evidence_log':str(work/'UE4SS.log'),
        'player_faction':'Faction.Player'if 'PBZ_COMBAT_CONTRACT:PLAYER_FACTION=Faction.Player'in log else None,
        'faction_switch_runtime_verified':'PBZ_CONTROL_LIFECYCLE:FACTION_SWITCH=Faction.Enemy->Faction.Player'in log
            and 'PBZ_CONTROL_LIFECYCLE:FACTION_FRIENDLY_VERIFIED=true'in log,
        'faction_restore_runtime_reported':'PBZ_CONTROL_LIFECYCLE:RESTORE=true|nil'in log,
        'target_component_acceptance_observed':'|has=true'in log,
        'ability_target_query_mismatch_observed':'PBZ_COMBAT_TARGET:QUERY=None|ignore_soft=None'in log,
        'target_runtime_verified':False,'damage_runtime_verified':False,'all_skills_playable':False,
        'fixed_delay_initialization_verified':False,'settled_target_path_runtime_verified':False,
        'formal_file_count':post['formal_file_count'],'formal_changed_count':len(post['formal_files_changed']),
        'research_box_empty':post['research_box_empty'],'research_loader_removed':post['research_loader_removed'],
        'local_regression_passed':local['passed'],'local_regression_tests':92,
        'current_source_sha256':sources,
        'runtime_manifest':s['ue4ss_loader_manifest'],
        'source_revision_note':'Final restoration readback and delayed-target fixtures were checked locally after the last live deployment; they are not claimed as runtime-tested.',
        'completed_mod':False}
    v.save(work/'combat-milestone.json',result)
    v.save(v.ROOT/'evidence/adaptation/ahua-combat-milestone.json',result)
    status_path=v.ROOT/'项目状态.json';status=json.loads(status_path.read_text(encoding='utf-8'))
    status.update({'updated_at':v.utc8(),'status_summary':'阿花接管、镜头、首招取消及玩家阵营切换恢复已有实机证据；技能目标查询不一致，完整Boss可玩Mod仍开发中。',
        'blocked_reason':'锁定组件接受敌人但GetLockingTarget返回空；临时阿花初始化/失效原因待定位；未验证命中伤害。',
        'next_action':'先修临时Boss就绪与生命周期，再打通实际技能目标来源和真实伤害；不再推进地图。',
        'latest_result_note':str(v.ROOT/'36-阿花阵营与技能目标实测.md'),
        'latest_combat_evidence':str(v.ROOT/'evidence/adaptation/ahua-combat-milestone.json'),
        'boss_faction_roundtrip_verified':result['faction_switch_runtime_verified']and result['faction_restore_runtime_reported'],
        'boss_target_runtime_verified':False,'boss_damage_runtime_verified':False,
        'boss_control_verified':False,'real_bridge_available':False,'no_loader_deployment':True,
        'no_remaining_pbz_processes_verified':post['research_box_empty'],'local_regression_test_count':92,
        'not_done':['Boss就绪与生命周期稳定性','实际技能目标与命中伤害','其余技能、连段和阶段条件','清理、死亡切图及玩家版入口']})
    v.save(status_path,status)
    print(json.dumps({k:result[k]for k in ('faction_switch_runtime_verified','target_runtime_verified','damage_runtime_verified','formal_file_count','formal_changed_count','research_box_empty','local_regression_passed','completed_mod')},ensure_ascii=False))

if __name__=='__main__':main()
