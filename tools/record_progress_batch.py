"""用途：依据保留的实机证据更新工作台；不启动游戏、不将候选修复当成已通过。"""
import csv
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
def read(path): return json.loads(path.read_text(encoding='utf-8'))
def save(path, data): path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    history = ROOT/'evidence/status-history'/now.strftime('%Y%m%d-%H%M%S')
    history.mkdir(parents=True, exist_ok=False)
    state_path = Path(read(ROOT/'runtime/latest-official-validation.json')['state_file'])
    state = read(state_path)
    post = read(ROOT/'evidence/latest-native-diagnostic-postcheck.json')
    gameplay = read(ROOT/'evidence/latest-gameplay-save-isolation.json')
    metadata = read(ROOT/'evidence/adaptation/latest-batch-character-metadata.json')
    specs = read(ROOT/'evidence/adaptation/latest-character-ability-specs.json')
    query_path = ROOT/'evidence/official-validation/20261113-011703/readonly-lua-query-evidence.json'
    query = read(query_path)
    observation_path=ROOT/'evidence/adaptation/latest-ai-observation-result.json'
    observation=read(observation_path)
    assert observation['core_observation_passed']
    assert gameplay['passed'] and gameplay['game_authored_progress_write_verified'] and gameplay['same_process_title_menu_reload_verified']
    assert metadata['player_controller_pawn_verified']
    assert query['query_pawn_pass'] and query['query_controller_pass']
    assert state['restored'] and post['research_box_empty'] and not post['formal_files_changed']
    done = [
        '通用UE4SS自主编译、自制UE5.8.1靶场、自写PBZ对象数组签名和反射布局通过',
        '固定PBZ构建的两个游戏进程通过只读Lua；不推断跨版本兼容',
        '原版副本实际写入主进度文件，载入菜单显示新时间并选择重载成功',
        '修正FProperty偏移后实测玩家Controller/Pawn双向引用、移动和能力组件',
        'Lua真实执行K2_GetPawn与GetController两个只读查询并和属性交叉核对',
        '真实Lua完整读取样本玩家140项与Luanshi敌人46项授予技能；未激活',
        '真实Lua查询敌人IsRunning=true及BT_SharedTactic_Idle；仇恨组件仍只读声明和引用',
        '图鉴确认新娘阿花位于悲泣溪谷；研究副本已进入溪谷地图，战斗实例未对应',
        '只读Lua热重载已在同一游戏进程通过，FlowLocText缓存和键可读取但中文缓存为空',
        '本批收尾56个正式文件无变化、研究箱为空、加载器撤除；不自动回档',
    ]
    todo = [
        '处理切图后尚未初始化NPC的重试与空本地化缓存；已记录真实问题，不逐项重启',
        '定位新娘阿花可进入的战斗或重战场景，将显示名称与战斗实例对应',
        'Boss暂停AI、接管/恢复、镜头和移动实机实现',
        '一招技能激活、结束和恢复验证，再形成真实玩家按键表',
    ]
    summary = '目标锁定新娘阿花；图鉴名称和悲泣溪谷位置已确认，战斗实例和重战入口未确认。只读Lua完整读取样本玩家140项和敌人46项技能，行为树运行状态及资产查询通过，热重载通过。存档隔离验收已通过限定范围，本轮56个正式文件零变化。切图未就绪NPC与空本地化缓存仍有问题；Boss接管、技能和按键表尚未实现。'
    for path in [ROOT/'项目状态.json', ROOT.parent/'profiles/pbz-offline.json']:
        shutil.copy2(path, history/path.name)
        data = read(path)
        data.update({'updated_at':now.isoformat(), 'status':'pbz-ai-observation-control-pending',
            'status_summary':summary, 'note':summary, 'completed':done, 'not_done':todo,
            'blocking_items':todo, 'blocked_reason':'新娘阿花战斗实例/入口未确认；接管和技能尚未实现',
            'target':'新娘阿花（图鉴已确认，战斗实例未确认）','user_selected_boss':'新娘阿花',
            'boss_codex_identity_verified':True,'boss_codex_region':'悲泣溪谷',
            'readonly_ai_observation_verified':True,'readonly_hot_reload_verified':True,
            'latest_ai_observation':str(observation_path),
            'observer_runtime_remaining_issues':observation['runtime_issues'],
            'game_save_isolation_verified':True, 'live_property_reference_decoding_verified':True,
            'readonly_process_event_queries_verified':True, 'boss_identity_verified':False,
            'boss_control_verified':False, 'real_bridge_available':False,
            'latest_gameplay_save_isolation':str(ROOT/'evidence/latest-gameplay-save-isolation.json'),
            'latest_lua_query_evidence':str(query_path),
            'latest_character_ability_specs':str(ROOT/'evidence/adaptation/latest-character-ability-specs.json'),
            'latest_scene_observation':str(ROOT/'evidence/adaptation/latest-batch-character-metadata.json'),
            'latest_result_note':str(ROOT/'28-阿花定位与Lua观测实测.md'),
            'next_action':'集中修复未就绪NPC分支，定位阿花战斗入口；复用已通过证据，只读脚本优先热重载，不重复原版隔离实验',
            'current_state_history':str(history)})
        if isinstance(data.get('sandbox'), dict): data['sandbox']['game_save_isolation_verified'] = True
        save(path, data)
    rows = list(csv.DictReader((ROOT/'26-待集中修复与复测.csv').open(encoding='utf-8-sig')))
    changes = {
        'META-001':('已实机通过','复用本构建双向引用与关联组件证据','evidence/adaptation/latest-batch-character-metadata.json'),
        'SAVE-001':('已实机通过范围有限','复用真实主进度写入与同进程菜单重载结果；新路径或新Mod另行核验','evidence/latest-gameplay-save-isolation.json'),
        'CALL-001':('两个只读Lua查询已通过','复用K2_GetPawn与GetController；其他函数需分别核对','evidence/official-validation/20261113-011703/readonly-lua-query-evidence.json'),
        'BOSS-001':('阿花图鉴和地区已确认战斗实例待对应','定位悲泣溪谷石蒜花丛喜堂或重战入口','evidence/official-validation/20261113-014606/bride-identity-visual-review.json'),
        'LUA-001':('延迟发现样本已实机通过','切图后未初始化NPC仍需保留重试而非永久seen','evidence/adaptation/latest-ai-observation-result.json'),
        'LUA-002':('玩家140项敌人46项有界读取已实机通过','复用本构建当前实例证据；零技能实例不算通过','evidence/adaptation/latest-ai-observation-result.json'),
        'LUA-003':('行为树查询已实机通过本地化中文未解决','FlowLocText可读Key但缓存空；不把BossName_008当已解析姓名','evidence/adaptation/latest-ai-observation-result.json'),
    }
    shutil.copy2(ROOT/'26-待集中修复与复测.csv', history/'26-待集中修复与复测.csv')
    for row in rows:
        if row['编号'] in changes:
            row['当前状态'], row['下一项工作'], row['证据'] = changes[row['编号']]
    for ident, problem, action in [
        ('LUA-001','玩家先出现而NPC尚未流送，旧脚本NPC_COUNT=0后结束','新版分阶段等待与字符串去重；不退出游戏'),
        ('LUA-002','旧ForEach把RemoteUnrealParam直接当技能结构体','改为长度核对后1基有界索引Get；本地夹具通过待实机'),
        ('LUA-003','行为树运行状态、运行资产与ActorConfig显示名称尚未由Lua读取','已核对IsRunning和GetRunningBehaviorTree返回布局；下轮合并查询'),
    ]:
        if not any(r['编号']==ident for r in rows):
            rows.append(dict(zip(rows[0].keys(),[ident,'Lua只读候选',problem,'已修复本地夹具通过待实机',action,'仅研究镜像；不激活技能不接管','adaptation/pbz-26367565/Mods/PBZObserveAI/Scripts/main.lua'])))
    with (ROOT/'26-待集中修复与复测.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    mislabeled = ROOT/'evidence/official-validation/20261113-005436/gameplay-save-after-exit.json'
    if mislabeled.is_file():
        data=read(mislabeled);data.update({'actual_state':'before_cleanup_game_still_running_in_map_menu',
            'label_correction':'Historical phase name after-exit is inaccurate; not proof of normal game exit. Cleanup is documented by state and postcheck.'})
        save(mislabeled,data)
    save(ROOT/'evidence/adaptation/latest-batch-progress.json',{'at':now.isoformat(),
        'game_save_isolation_verified':True,'reciprocal_references_verified':True,
        'two_readonly_lua_queries_verified':True,'ability_sample_count':len(specs['characters']),
        'candidate_observer_v2_core_runtime_verified':True,'all_npc_branches_verified':False,'boss_control_verified':False,
        'history':str(history)})
    print('Updated status, profile, issue log; archived prior state. Boss control remains unverified.')

if __name__=='__main__': main()
