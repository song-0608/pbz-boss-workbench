"""Archive verified v1 gameplay payload plus the local launcher performance fix."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
from mod_installation import ROOT,MANIFEST,active_mod_root,assert_closed,digest,read,validate_package


def package():
    assert_closed()
    acceptance_path=ROOT/'evidence/adaptation/ahua-performance-hotfix-acceptance.json'
    acceptance=read(acceptance_path);assert acceptance['passed']
    for name,sha in acceptance['launcher_source_sha256'].items():assert digest(ROOT/name)==sha
    checks_path=ROOT/'evidence/adaptation/ahua-delivery-local-checks.json';checks=read(checks_path)
    assert checks['passed']and all(digest(ROOT/name)==sha for name,sha in checks['source_sha256'].items())
    source=active_mod_root();original=source.parent;manifest=validate_package(original)
    assert manifest['release_id']==acceptance['gameplay_release']and manifest['complete_mod']
    modules={p.relative_to(source/'Scripts').as_posix():digest(p)for p in(source/'Scripts').rglob('*.lua')if p.name!='main.lua'}
    assert modules==acceptance['module_source_sha256']
    paths=['tools/pbz_ue4ss_baseline.py','tools/ahua_practice.py','tools/run_control_lifecycle_probe.py',
           'tools/performance_probe.lua','tools/collect_performance_comparison.py','tools/collect_performance_hotfix.py',
           'tools/package_performance_hotfix.py','tests/test_performance_comparison.py','tools/check_ahua_delivery.py']
    paths.append('tools/probe_cache_after_world.py')
    fingerprint=hashlib.sha256(json.dumps({n:digest(ROOT/n)for n in paths},sort_keys=True).encode()).hexdigest()
    release_id='ahua-v1.0.1-performance-'+fingerprint[:12]
    target=ROOT/'releases'/release_id
    if target.exists():raise RuntimeError('Preserve existing immutable hotfix package')
    target.mkdir(parents=True)
    for name in [*manifest['files'],MANIFEST]:
        destination=target/'Mod'/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(original/name,destination)
    for name in paths:
        destination=target/'Launcher'/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,destination)
    evidence=[acceptance_path,ROOT/'evidence/adaptation/ahua-performance-comparison.json',checks_path,
              ROOT/manifest['acceptance_report'],ROOT/'evidence/official-validation'/acceptance['reload_session']/'cache-world-probe.json']
    for path in evidence:
        destination=target/'Evidence'/path.name;destination.parent.mkdir(exist_ok=True);shutil.copy2(path,destination)
    shutil.copy2(ROOT/'docs/archive/60-接管卡顿修复与验收.md',target/'使用说明.md')
    (target/'README.md').write_text('''# 阿花 v1.0.1 性能修复完整交付

当前 D:\\mod文档 中的启动器已应用修复，直接双击“开始阿花训练.cmd”即可。

本包包含完整28能力/29绑定v1 Mod（Mod目录）、启动器性能修复与验收工具（Launcher目录）、验收报告（Evidence目录）。当前本机受保护离线环境和已验证自编译加载器仍是前提，包内不包含游戏资源、存档、账号或活动会话凭据。

重新安装Mod时，在现有管理窗口选择本包的Mod目录。仅安装Mod不会更新启动器；已有同版本项目副本需在所有研究会话结束后，将Launcher目录内的tools、tests复制到项目根目录。现有工作目录已完成此更新。

本次修复启动器的对象查询缓存配置，游戏Lua及已验证DLL未改动。全部文件哈希见hotfix-manifest.json；具体指标与使用方法见使用说明.md。
''',encoding='utf-8')
    files={p.relative_to(target).as_posix():digest(p)for p in sorted(target.rglob('*'))if p.is_file()}
    metadata={'release_id':release_id,'at':datetime.now().astimezone().isoformat(),'complete_mod':True,
              'gameplay_release':manifest['release_id'],'performance_fix_verified':True,'files':files}
    (target/'hotfix-manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    archive=target.parent/(target.name+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED)as output:
        for path in sorted(target.rglob('*')):
            if path.is_file():output.write(path,path.relative_to(target).as_posix())
    with zipfile.ZipFile(archive)as output:
        expected={**files,'hotfix-manifest.json':digest(target/'hotfix-manifest.json')}
        assert set(output.namelist())==set(expected)and output.testzip()is None
        assert all(hashlib.sha256(output.read(name)).hexdigest()==sha for name,sha in expected.items())
    archive.with_suffix('.zip.sha256').write_text(digest(archive)+'  '+archive.name+'\n',encoding='utf-8')
    result={'release_id':release_id,'directory':str(target),'archive':str(archive),'archive_sha256':digest(archive),
            'verified_payload_files':len(files)+1,'complete_mod':True,'performance_fix_verified':True,
            'formal_install_modified':False,'acceptance_sha256':digest(acceptance_path)}
    (ROOT/'evidence/releases'/f'{release_id}-delivery.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':package()
