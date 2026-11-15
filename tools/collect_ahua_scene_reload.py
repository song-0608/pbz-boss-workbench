"""用途：收尾后验证同进程场景重载、身份重新捕获、真实出招及恢复；不修改实机原始结果。"""
import hashlib
import json
from pathlib import Path
import sys
from control_action_evidence import reload_retakeover_result
ROOT=Path(__file__).resolve().parents[1]


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def main():
    owner=read(ROOT/'runtime/ahua-practice.json');state=read(Path(owner['state_file']));work=Path(state['work'])
    if owner['phase']!='closed'or not state.get('restored'):raise RuntimeError('Completed matching research session required')
    post=read(work/'postcheck.json')
    if post['validation_state']!=owner['state_file']or post['formal_files_changed']or not post['research_box_empty']:
        raise RuntimeError('Matching formal-file and research closure postcheck required')
    witness=read(work/'scene-reload-witness.json')
    if witness['state_file']!=owner['state_file']:raise RuntimeError('Scene reload witness belongs to another session')
    before_path=work/'before-scene-reload.log';before=before_path.read_text(encoding='utf-8',errors='replace')
    log=work/'UE4SS.log';text=log.read_text(encoding='utf-8',errors='replace')
    if hashlib.sha256(before_path.read_bytes()).hexdigest()!=witness['pre_reload_log_sha256']:
        raise RuntimeError('Pre-reload evidence changed')
    if before!=text[:witness['pre_reload_log_end']]:raise RuntimeError('Final log does not preserve pre-reload evidence')
    start,end=witness['post_reload_log_start'],witness['post_reload_log_end']
    if not witness['pre_reload_log_end']<=start<end<=len(text):raise RuntimeError('Invalid bounded scene test interval')
    proof=reload_retakeover_result(before[witness['pre_reload_log_start']:],text[start:end])
    actions=read(work/'settings-menu-actions.json');purposes=[a['purpose']for a in actions]
    proof['original_menu_confirm_then_continue']=('control_menu_confirm'in purposes and 'control_menu_continue'in purposes
        and purposes.index('control_menu_confirm')<purposes.index('control_menu_continue'))
    proof['same_game_process']=bool(witness.get('same_game_process')and witness['pre_reload_game_pid']==witness['post_reload_game_pid'])
    proof['passed']=proof['passed']and proof['original_menu_confirm_then_continue']and proof['same_game_process']
    report={'session':str(work),'witness':witness,'proof':proof,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),
        'formal_files_changed':post['formal_files_changed'],'research_box_empty':post['research_box_empty'],
        'active_receipt_cross_world_tested':False,'full_scene_lifecycle_verified':False,'automatically_released':False}
    target=work/'scene-reload-retakeover-evidence.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(target),'proof':proof},ensure_ascii=False,indent=2))
    return 0 if proof['passed']else 1


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');sys.exit(main())
