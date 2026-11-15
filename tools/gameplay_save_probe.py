"""用途：为原版离线玩法存档隔离测试建立新备份，并只读比较真实文件变化。"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import official_validation as v


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def session():
    s=json.loads(v.state_path().read_text(encoding='utf-8'))
    if s.get('restored') or time.time()>=s['deadline_unix'] or not s.get('offline_validation') or s.get('network_active'):
        raise RuntimeError('Active strictly offline research lease required')
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    c.isolation.check_policy(dll,allow_offline_validation=True)
    if c.host_steam_pids(dll):raise RuntimeError('Preserve host Steam')
    if s.get('ue4ss_deployed'):raise RuntimeError('Original-game save probe requires no UE4SS deployment')
    v.verify_build()
    now=c.baseline.formal_files();before=s['formal_before']
    if now!=before:raise RuntimeError('Formal files changed; stop experiment')
    return s,dll,now


def prepare():
    s,dll,formal=session();work=Path(s['work']);container=v.c.isolation.get_root(dll)
    if v.c.preflight.games_running():raise RuntimeError('Take consistent snapshot only while PBZ is closed')
    if not s.get('compatibility_probe_passed') or not s.get('local_saved_probe_passed'):
        raise RuntimeError('This lease isolation probes incomplete')
    settings=json.loads((v.ROOT/'evidence/latest-game-settings-isolation.json').read_text(encoding='utf-8'))
    if not settings.get('passed'):raise RuntimeError('Real settings-write isolation not verified')
    if (work/'gameplay-probe-allowed.json').exists():raise RuntimeError('Do not overwrite existing probe baseline')
    if sum(row['bytes'] for row in formal.values())>200*1024*1024:raise RuntimeError('Snapshot scope exceeds budget')
    copied=[]
    for index,(name,info) in enumerate(sorted(formal.items())):
        source=Path(name);target=work/'formal-before-gameplay-backup'/(f'{index:03d}'+source.suffix)
        if digest(source)!=info['sha256']:raise RuntimeError('Formal snapshot race')
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        if digest(target)!=info['sha256'] or digest(source)!=info['sha256']:raise RuntimeError('Snapshot verification failed')
        copied.append({'source':name,'backup':str(target),'sha256':info['sha256']})
    # 用途：仅将本轮正式进度的副本播种到沙盒，不回写正式目录，不复原早晨的旧进度。
    roots=[v.c.baseline.GAME/'ProjectPBZ/Saved',Path(os.environ['LOCALAPPDATA'])/'ProjectPBZ/Saved']
    seeded=[]
    for name,info in sorted(formal.items()):
        source=Path(name)
        if source.suffix.lower()!='.sav' or not any(source.is_relative_to(root) for root in roots):continue
        target=v.c.isolation.virtual_file(container,source)
        if not target.is_relative_to(container) or target==source:raise RuntimeError('Mirror target outside research container')
        if target.exists():
            previous=work/'previous-virtual-saves'/(f'{len(seeded):03d}.sav')
            previous.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,previous)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        if digest(target)!=info['sha256']:raise RuntimeError('Virtual game save seed mismatch')
        seeded.append({'logical_source':name,'physical_target':str(target),'sha256':info['sha256']})
    if not seeded:raise RuntimeError('No known game save to test; do not start new game')
    if v.c.baseline.formal_files()!=formal:raise RuntimeError('Formal files changed during backup')
    report={'at':v.utc8(),'state_file':str(v.state_path()),'formal_backup':copied,'seeded_game_saves':seeded,
        'offline':True,'no_mods':True,'cloud_off_review_required_before_launch':True,
        'scope':'Load current progress COPY, observe actual save write and reload; never modify formal save'}
    v.save(work/'gameplay-probe-allowed.json',report)
    s.update({'save_gameplay_allowed':True,'gameplay_save_probe':True});v.save(v.state_path(),s)
    snapshot('prepared')
    print(json.dumps({'backup_verified_count':len(copied),'game_save_copies_seeded':len(seeded),'formal_files_changed':False}))


def snapshot(label):
    if label not in ('prepared','before-continue','after-load','after-interact','after-return','after-reload','after-exit'):
        raise RuntimeError('Unsupported save-probe phase')
    s,dll,formal=session();work=Path(s['work']);container=v.c.isolation.get_root(dll)
    if not s.get('gameplay_save_probe') or not s.get('save_gameplay_allowed'):raise RuntimeError('No probe gate')
    files={}
    for category,logical in [('game',v.c.baseline.GAME/'ProjectPBZ/Saved'),('local',Path(os.environ['LOCALAPPDATA'])/'ProjectPBZ/Saved')]:
        root=v.c.isolation.virtual_file(container,logical)
        if not root.exists():continue
        for path in root.rglob('*.sav'):
            if path.is_file():files[category+'/'+path.relative_to(root).as_posix()]={'sha256':digest(path),'bytes':path.stat().st_size}
    report={'at':v.utc8(),'phase':label,'virtual_game_save_files':files,'formal_files_changed':False,'formal_file_count':len(formal)}
    prior=work/'gameplay-save-prepared.json'
    if label!='prepared' and prior.exists():
        before=json.loads(prior.read_text(encoding='utf-8'))['virtual_game_save_files']
        report['virtual_sav_changed']=[p for p in sorted(set(before)|set(files)) if before.get(p)!=files.get(p)]
    v.save(work/('gameplay-save-'+label+'.json'),report)
    print(json.dumps({'phase':label,'virtual_save_count':len(files),'changed_save_basenames':[Path(p).name for p in report.get('virtual_sav_changed',[])],'formal_changed_count':0},ensure_ascii=False))
    return report


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if sys.argv[1:]==['--prepare']:prepare()
    elif len(sys.argv)==3 and sys.argv[1]=='--snapshot':snapshot(sys.argv[2])
    else:raise RuntimeError('Use --prepare before game launch, or --snapshot PHASE')
