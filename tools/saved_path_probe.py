"""用途：原版关闭时，在研究箱中读写当前实际 .sav 文件的副本，证明同名文件没有回写主机。"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import uuid
import official_validation as v


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def worker(spec_path,output):
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    if os.getpid() not in c.baseline.box_pids(dll):raise RuntimeError('Worker must be in research box')
    spec=json.loads(Path(spec_path).read_text(encoding='utf-8'));rows=[]
    for item in spec['files']:
        path=Path(item['logical_path']);original=path.read_bytes()
        if not original or hashlib.sha256(original).hexdigest()!=item['sha256']:
            raise RuntimeError('Existing research save differs from declared source; stop before writes')
        altered=bytes([original[0]^1])+original[1:]
        try:
            path.write_bytes(altered)
            write_verified=path.read_bytes()==altered
        finally:
            path.write_bytes(original)
        # 用途：写入、还原同名实际存档副本；通过独立标记确认容器路径，游戏全程关闭。
        marker=path.parent/('PBZLab_path_probe_'+uuid.uuid4().hex+'.tmp')
        token=uuid.uuid4().hex.encode('ascii');marker.write_bytes(token)
        rows.append({'logical_path':str(path),'write_read_verified':write_verified,
            'restored_sha256':digest(path),'marker_path':str(marker),'marker_sha256':hashlib.sha256(token).hexdigest()})
    v.save(Path(output),{'inside_research_box':True,'rows':rows})


def main():
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    state=json.loads(v.state_path().read_text(encoding='utf-8'));work=Path(state['work'])
    c.isolation.check_policy(dll,allow_offline_validation=True)
    if c.preflight.games_running():raise RuntimeError('Game must be closed for save path probe')
    container=c.isolation.get_root(dll);baseline=c.baseline.formal_files()
    root=c.baseline.GAME/'ProjectPBZ/Saved'
    source=[p for p in root.rglob('*.sav') if p.is_file() and not p.is_symlink()]
    if not source or sum(p.stat().st_size for p in source)>200*1024*1024:
        raise RuntimeError('Actual save set missing or outside expected size')
    spec={'files':[]}
    for p in source:
        target=c.isolation.virtual_file(container,p)
        # 用途：保留已经存在的研究进度/设置，按当前副本哈希测试再原样还原；绝不覆盖为正式档。
        current=target if target.is_file() else p
        spec['files'].append({'logical_path':str(p),'sha256':digest(current)})
    specification=work/'save-path-probe-spec.json';output=work/'save-path-probe-worker.json'
    v.save(specification,spec)
    result=subprocess.run([str(c.isolation.SBIE/'Start.exe'),'/box:PBZSteamLab','/silent','/hide_window','/wait',
        sys.executable,__file__,'--worker',str(specification),str(output)],capture_output=True,timeout=40)
    physical=c.isolation.virtual_file(container,output)
    if result.returncode or not physical.is_file():raise RuntimeError('Save path probe failed')
    rows=json.loads(physical.read_text(encoding='utf-8'))['rows'];checks=[]
    for row in rows:
        logical=Path(row['logical_path']);virtual=c.isolation.virtual_file(container,logical)
        marker=Path(row['marker_path']);virtual_marker=c.isolation.virtual_file(container,marker)
        item={'file_basename':logical.name,'host_unchanged':digest(logical)==baseline[str(logical)]['sha256'],
            'virtual_copy_restored':virtual.is_file() and digest(virtual)==row['restored_sha256']==next(x['sha256'] for x in spec['files'] if x['logical_path']==str(logical)),
            'boxed_write_read_verified':row['write_read_verified'],'host_marker_absent':not marker.exists(),
            'virtual_marker_valid':virtual_marker.is_file() and digest(virtual_marker)==row['marker_sha256']}
        checks.append(item)
        if item['virtual_marker_valid']:virtual_marker.unlink()
    after=c.baseline.formal_files()
    changed=[name for name in set(baseline)|set(after) if baseline.get(name)!=after.get(name)]
    proof={'at':v.utc8(),'game_running_during_probe':False,'actual_save_file_count':len(checks),
        'same_filename_copy_write_restore_verified':all(all(val for key,val in row.items() if key!='file_basename') for row in checks),
        'formal_files_changed_count':len(changed),'files':checks,
        'scope':'Actual current .sav filenames tested via sandbox worker while PBZ closed; game-authored save operation not yet exercised',
        'game_authored_save_write_verified':False}
    proof['passed']=proof['same_filename_copy_write_restore_verified'] and not changed
    v.save(work/'actual-save-path-proof.json',proof)
    if not proof['passed']:raise RuntimeError('Save path isolation proof failed')
    print(json.dumps({k:val for k,val in proof.items() if k!='files'},ensure_ascii=False))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv)==4 and sys.argv[1]=='--worker':worker(sys.argv[2],sys.argv[3])
    else:main()
