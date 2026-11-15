"""用途：测试研究箱对PBZ本地配置的虚拟读写，不启动游戏，不写真实存档。"""
from pathlib import Path
import hashlib,json,os,sys,uuid,subprocess,shutil
import test_offline_client as c
from prepare_manual_login import save


def verify_virtualized_read_write(state_path):
    """用途：移除逻辑拒绝后，先离线验证副本写入；验收成功前不给游戏联网。"""
    c.isolation.select_box('PBZSteamLab');dll=c.isolation.api();container=c.isolation.get_root(dll)
    path=Path(state_path);s=json.loads(path.read_text(encoding='utf-8'));work=Path(s['work'])
    source=Path(os.environ['LOCALAPPDATA'])/'ProjectPBZ/Saved/Config'
    if not (source/'Windows/GameUserSettings.ini').is_file():raise RuntimeError('Existing local config missing')
    for f in source.rglob('*.ini'):
        target=c.isolation.virtual_file(container,f);target.parent.mkdir(parents=True,exist_ok=True)
        # 用途：本轮使用原件的已知配置作对照；仅覆盖研究箱中的配置副本。
        shutil.copy2(f,target)
    output=work/'local-saved-probe-boxed.json'
    r=subprocess.run([str(c.isolation.SBIE/'Start.exe'),'/box:PBZSteamLab','/silent','/hide_window','/wait',
        sys.executable,__file__,'--worker',str(output)],capture_output=True,timeout=20)
    physical=c.isolation.virtual_file(container,output)
    if r.returncode or not physical.is_file():raise RuntimeError('Boxed local config probe did not complete')
    report=json.loads(physical.read_text(encoding='utf-8'));config=Path(report['config_path']);marker=Path(report['marker_path'])
    config_hash=hashlib.sha256(config.read_bytes()).hexdigest()
    marker_copy=c.isolation.virtual_file(container,marker)
    report['host_marker_absent']=not marker.exists()
    report['virtual_marker_present']=marker_copy.is_file() and hashlib.sha256(marker_copy.read_bytes()).hexdigest()==report['marker_sha256']
    report['host_config_unchanged']=config_hash==report['config_sha256_before']==report['config_restored_sha256']
    now=c.baseline.formal_files()
    report['formal_files_changed']=[p for p in set(now)|set(s['formal_before']) if now.get(p)!=s['formal_before'].get(p)]
    report['passed']=all(report[k] for k in ['inside_research_box','config_read_write_verified','marker_read_verified',
           'host_marker_absent','virtual_marker_present','host_config_unchanged']) and not report['formal_files_changed']
    save(work/'local-saved-virtualization-proof.json',report)
    if marker_copy.exists():marker_copy.unlink() # 用途：仅清理本轮创建的箱内标记。
    if not report['passed']:raise RuntimeError('Local configuration virtualization proof failed; stop')
    s['local_saved_probe_passed']=True;save(path,s)
    if c.cleanup(dll):raise RuntimeError('Probe helper cleanup incomplete')
    return report


def worker(output):
    c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    if os.getpid() not in c.baseline.box_pids(dll):raise RuntimeError('Worker must run inside research box')
    saved=Path(os.environ['LOCALAPPDATA'])/'ProjectPBZ/Saved'
    config=saved/'Config/Windows/GameUserSettings.ini'
    original=config.read_bytes();before=hashlib.sha256(original).hexdigest()
    marker=saved/('PBZLab_virtualization_probe_'+uuid.uuid4().hex+'.tmp')
    token=uuid.uuid4().hex.encode('ascii')
    try:
        # 用途：仅在虚拟副本追加注释并立即恢复，证明配置路径可读写；不改变任何游戏设置值。
        config.write_bytes(original+b'\r\n; PBZLab virtual-only probe\r\n')
        config_write_read=config.read_bytes().endswith(b'; PBZLab virtual-only probe\r\n')
        config.write_bytes(original)
        marker.write_bytes(token)
        marker_read=marker.read_bytes()==token
        save(Path(output),{'inside_research_box':True,'config_path':str(config),'config_sha256_before':before,
             'config_read_write_verified':config_write_read,'config_restored_sha256':hashlib.sha256(config.read_bytes()).hexdigest(),
             'marker_path':str(marker),'marker_sha256':hashlib.sha256(token).hexdigest(),'marker_read_verified':marker_read})
    finally:
        if config.read_bytes()!=original:config.write_bytes(original)
        # 用途：标记保留到主机核对箱内映射，后续仅删除本轮创建的标记。


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--worker':worker(sys.argv[2])
    else:raise RuntimeError('Use only as a boxed worker in a controlled experiment')
