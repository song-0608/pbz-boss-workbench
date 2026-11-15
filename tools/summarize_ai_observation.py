"""用途：从本轮真实UE4SS日志提取技能清单与AI证据，区分已读取和未实现的操作。"""
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
import official_validation as v
from observer_log_parser import parse_observation


def summarize():
    state=json.loads(v.state_path().read_text(encoding='utf-8'));work=Path(state['work'])
    if state.get('restored'):
        path=work/'UE4SS.log'
    else:
        c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
        c.isolation.check_policy(dll,allow_offline_validation=True)
        if c.host_steam_pids(dll):raise RuntimeError('Preserve host Steam')
        v.verify_build(state['ue4ss_loader_manifest'])
        path=c.isolation.virtual_file(c.isolation.get_root(dll),c.baseline.GAME/'platform/steam/ue4ss/UE4SS.log')
    lines=[x for x in path.read_text(encoding='utf-8',errors='replace').splitlines() if 'PBZ_AI_OBSERVE:' in x]
    parsed=parse_observation(lines)
    current,rows,issues,last_counts,per_instance=(parsed[k] for k in ('current','rows','issues','counts','per_instance'))
    # 用途：记录本轮真正部署的脚本哈希，不能把刚改过的源码冒充上一轮实测版本。
    deployed=[row['sha256'] for row in state.get('ue4ss_loader_manifest',[])
              if Path(row['physical_path']).as_posix().endswith('/Mods/PBZObserveAI/Scripts/main.lua')]
    with (work/'granted-abilities-observed.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['观察对象','实例','采集序号','授予技能对象','已激活实测','玩家按键'])
        writer.writeheader();writer.writerows(rows)
    proof={'at':v.utc8(),'state_file':str(v.state_path()),'work':str(work),
        'query_pawn_verified':any('QUERY_PAWN_PASS=' in x for x in current),
        'query_controller_verified':any('QUERY_CONTROLLER_PASS=' in x for x in current),
        'observer_version':parsed['version'],
        'npc_lua_observed':any(re.match(r'NPC_\d+_OBSERVED=',x) for x in current),
        'brain_running_query_verified':any('_BRAIN_RUNNING=true' in x for x in current),
        'running_behavior_tree_query_verified':any('_TREE=BehaviorTree ' in x for x in current),
        'player_140_specs_read':any('PLAYER_ABILITY_COLLECTED=140' in x for x in current),
        'npc_46_specs_read':any(re.match(r'NPC_\d+_ABILITY_COLLECTED=46$',x) for x in current),
        'runtime_issues':issues,'collected_counts':last_counts,'csv_rows':len(rows),
        'per_instance':per_instance,
        'hot_reload_observed':parsed['starts']>1,'script_sha256':deployed[0] if len(deployed)==1 else None,
        'source_candidate_sha256':hashlib.sha256((v.ROOT/'adaptation/pbz-26367565/Mods/PBZObserveAI/Scripts/main.lua').read_bytes()).hexdigest(),
        'localization_name_resolved':any(i['queries'].get('CONFIG_NAME','') for i in per_instance.values()),
        'localization_note':'Only nonempty FlowLocText.ValueCache is a resolved name; Key alone never identifies the boss',
        'boss_identity_verified':False,'boss_control_verified':False,'skill_activation_verified':False,
        'scope':'Latest observer segment only. Historical sample checks require player 140 and NPC 46 reads; these counts are not universal success criteria for other characters. Pending or exhausted stages are not a pass. CSV rows are samples, not unique playable skills or a key map.'}
    proof['core_observation_passed']=all(proof[k] for k in ['query_pawn_verified','query_controller_verified',
        'npc_lua_observed','brain_running_query_verified','running_behavior_tree_query_verified',
        'player_140_specs_read','npc_46_specs_read'])
    v.save(work/'ai-observation-result.json',proof)
    v.save(v.ROOT/'evidence/adaptation/latest-ai-observation-result.json',proof)
    v.save(work/'observer-filtered-log.json',{'at':v.utc8(),'lines':lines})
    print(json.dumps(proof,ensure_ascii=False,indent=2))

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');summarize()
