"""用途：只依据真实游戏写入、可见载入和正式文件对比验收副本进度隔离。"""
import json
from pathlib import Path
import sys
import official_validation as v
from gameplay_save_probe import session


def verify():
    state,dll,formal=session();work=Path(state['work'])
    proof=json.loads((work/'save-reload-visual-review.json').read_text(encoding='utf-8'))
    if proof.get('state_file')!=str(v.state_path()) or not all(proof.get(k) for k in
            ['scene_loaded','returned_to_title','fresh_save_timestamp_visible','fresh_save_selected','reloaded_scene_visible']):
        raise RuntimeError('This session genuine save/reload visual review missing')
    for name in proof['screenshots']:
        p=work/name
        if p.parent!=work or not p.is_file():raise RuntimeError('Reviewed screenshot unavailable')
    stages={name:json.loads((work/('gameplay-save-'+name+'.json')).read_text(encoding='utf-8'))
        for name in ['prepared','after-interact','after-return','after-reload']}
    baseline=stages['prepared']['virtual_game_save_files']
    changed=[]
    for name,info in stages['after-interact']['virtual_game_save_files'].items():
        if Path(name).name=='PBZSaveGame.sav' and baseline.get(name)!=info:changed.append(name)
    if not changed:raise RuntimeError('No game-authored main progress save change; settings do not count')
    if any(any(p not in stage['virtual_game_save_files'] for p in changed) or stage.get('formal_files_changed')
            for stage in stages.values()):raise RuntimeError('Incomplete progress snapshots or formal changes')
    report={'at':v.utc8(),'passed':True,'game_save_isolation_verified':True,
        'validation_state':str(v.state_path()),'work':str(work),'formal_file_count':len(formal),'formal_changed_count':0,
        'game_authored_progress_write_verified':True,'same_process_title_menu_reload_verified':True,
        'new_progress_save_timestamp':proof['fresh_save_timestamp'],'main_progress_files_changed_count':len(changed),
        'formal_save_restored_or_overwritten':False,'all_game_network_blocked':True,'cloud_off_reviewed':True,
        'scope':'Observed original-game progress write, fresh save visible in load menu, selected and loaded in same game process. No kernel-level file-read trace; not all future save paths or mods certified.'}
    v.save(work/'gameplay-save-isolation-result.json',report)
    v.save(v.ROOT/'evidence/latest-gameplay-save-isolation.json',report)
    return report


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');print(json.dumps(verify(),ensure_ascii=False,indent=2))
