"""用途：只读核对研究箱游戏设置文件变化和正式文件哈希，不恢复或写入游戏文件。"""
import hashlib
import json
from pathlib import Path
import sys
import time
import official_validation as v


def capture(label, previous=None):
    if label not in ('before-audio', 'after-audio', 'restored-audio', 'after-exit'):
        raise RuntimeError('Unknown settings observation phase')
    state=json.loads(v.state_path().read_text(encoding='utf-8'))
    if state.get('restored') or time.time()>=state['deadline_unix']:
        raise RuntimeError('Offline research lease ended')
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    c.isolation.check_policy(dll,allow_offline_validation=True)
    if c.host_steam_pids(dll):raise RuntimeError('Preserve host Steam')
    container=c.isolation.get_root(dll);work=Path(state['work']);files={}
    import os
    roots=[c.baseline.GAME/'ProjectPBZ/Saved',Path(os.environ['LOCALAPPDATA'])/'ProjectPBZ/Saved']
    for index,logical in enumerate(roots):
        physical=c.isolation.virtual_file(container,logical)
        if not physical.exists():continue
        for p in physical.rglob('*'):
            if p.is_file() and p.suffix.lower() in ('.sav','.ini'):
                with p.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
                files[str(index)+'/'+p.relative_to(physical).as_posix()]={'sha256':digest,'bytes':p.stat().st_size}
    now=c.baseline.formal_files();before=state['formal_before']
    changed=[p for p in set(now)|set(before) if now.get(p)!=before.get(p)]
    report={'at':v.utc8(),'label':label,'files':files,'formal_file_count':len(now),
            'formal_changed_count':len(changed),'settings_write_verified':False}
    if previous:
        prior=json.loads((work/('settings-'+previous+'.json')).read_text(encoding='utf-8'))
        differences=[p for p in set(files)|set(prior['files']) if files.get(p)!=prior['files'].get(p)]
        report.update({'previous':previous,'virtual_changed_files':differences})
    v.save(work/('settings-'+label+'.json'),report)
    print(json.dumps({'label':label,'formal_changed_count':len(changed),'virtual_file_count':len(files),
        'virtual_changed_basenames':[Path(p).name for p in report.get('virtual_changed_files',[])]},ensure_ascii=False))
    if changed:raise RuntimeError('Formal file change detected; stop research test')
    return report


if __name__=='__main__':capture(*sys.argv[1:])
