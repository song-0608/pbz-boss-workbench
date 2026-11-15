"""用途：只读核对研究箱收尾、正式文件及备份；不会自动回档或结束用户进程。"""
from datetime import datetime,timezone,timedelta
import hashlib
import json
import sys
from pathlib import Path
import official_validation as v


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    policy=c.isolation.check_policy(dll)
    state=json.loads(v.state_path().read_text(encoding='utf-8'))
    proof_path=Path(state['work'])/'menu-visual-verification.json'
    menu_proof=json.loads(proof_path.read_text(encoding='utf-8')) if proof_path.is_file() else {}
    settings_proof_path=v.ROOT/'evidence/latest-game-settings-isolation.json'
    settings_proof=json.loads(settings_proof_path.read_text(encoding='utf-8')) if settings_proof_path.is_file() else {}
    gameplay_proof_path=v.ROOT/'evidence/latest-gameplay-save-isolation.json'
    gameplay_proof=json.loads(gameplay_proof_path.read_text(encoding='utf-8')) if gameplay_proof_path.is_file() else {}
    token_key=state.get('compatibility_setting')
    token_restored=(not state.get('compatibility_setting_applied') or
        (token_key in v.TOKEN_COMPATIBILITY_KEYS and c.isolation.values(dll,token_key)==state['compatibility_setting_prior']))
    now=c.baseline.formal_files();previous=state['formal_before']
    rules=policy['ClosedFilePath']
    changed=[name for name in sorted(set(now)|set(previous)) if now.get(name)!=previous.get(name)]
    host_changed=[name for name,sha in state['host_config_hashes'].items()
        if not Path(name).is_file() or hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha]
    result={'checked_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
        'validation_state':str(v.state_path()),'all_temporary_network_removed':all(rule not in policy['NetworkAccess'] for rule in v.ONLINE_RULES),
        'overlay_file_block_removed':v.STEAM_OVERLAY_DENY not in rules,
        'nvidia_overlay_blocks_removed':all(rule not in rules for rule in v.NVIDIA_OVERLAY_DENIES),
        'research_box_empty':not c.baseline.box_pids(dll),'remaining_games':c.preflight.games_running(),
        'host_steam_pids':c.host_steam_pids(dll),'formal_file_count':len(now),'formal_files_changed':changed,
        'host_config_files_changed':host_changed,'host_registry_unchanged':c.registry_host()==state['host_registry_before'],
        'backup_check':c.preflight.compare(v.ROOT/'evidence/latest-preflight.json'),
        'library_rule_count':sum(x.casefold().endswith(r'\steamlibrary\*') for x in rules),
        'game_rule_count':sum(x.casefold().endswith(r'\steamapps\common\pbz\*') for x in rules),
        'local_project_deny_count':sum(x.casefold().endswith(r'\appdata\local\projectpbz\*') for x in rules),
        'validation_restored':state.get('restored',False),'game_menu_verified':bool(menu_proof.get('menu_verified')),
        'offline_cold_start_verified':bool(menu_proof.get('offline_cold_start_verified')),
        'compatibility_setting_restored':token_restored,
        'game_settings_write_isolation_verified':bool(settings_proof.get('passed') and settings_proof.get('game_settings_write_isolation_verified')),
        'research_loader_removed':not state.get('ue4ss_deployed') or bool(state.get('research_loader_removed')),
        'game_save_isolation_verified':bool(gameplay_proof.get('passed') and gameplay_proof.get('game_authored_progress_write_verified') and gameplay_proof.get('same_process_title_menu_reload_verified')),
        'gameplay_isolation_evidence':str(gameplay_proof_path) if gameplay_proof else None,'ue4ss_deployed':False}
    target=v.ROOT/'evidence/latest-native-diagnostic-postcheck.json';v.save(target,result)
    # 用途：后续会话会覆盖latest；按键验收必须保留与本轮state匹配的收尾证明。
    v.save(Path(state['work'])/'postcheck.json',result)
    # 用途：终端仅打印计数和布尔；私有正式路径只保留在本地诊断报告。
    public={k:val for k,val in result.items() if k not in ('host_config_files_changed','formal_files_changed','backup_check','remaining_games')}
    public.update({'formal_changed_count':len(changed),'host_config_changed_count':len(host_changed),
        'remaining_game_count':len(result['remaining_games']),
        'backup_verified':result['backup_check']['backup_contents_verified'],
        'original_backup_file_changed_count':result['backup_check']['original_files_changed_count'],'report':str(target)})
    print(json.dumps(public,ensure_ascii=False,indent=2))
    if not all((result['all_temporary_network_removed'],result['overlay_file_block_removed'],result['nvidia_overlay_blocks_removed'],result['research_box_empty'],
        result['validation_restored'],token_restored,result['research_loader_removed'],not changed,not host_changed,result['host_registry_unchanged'])):
        raise RuntimeError('Native diagnostic postcheck requires review')


if __name__=='__main__':main()
