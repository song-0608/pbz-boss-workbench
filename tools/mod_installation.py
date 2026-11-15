"""本机研究启动器的可核验Mod安装管理；不写游戏目录、存档或个人键位。"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
MANIFEST='pbz-release.json'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    pending=path.with_name(path.name+'.'+uuid.uuid4().hex+'.pending')
    pending.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    pending.replace(path)


def unlinked_path(path):
    """拒绝链接、junction或解析后逃离本地包目录的条目。"""
    path=Path(path)
    for item in (path,*path.parents):
        if item.is_symlink()or(getattr(item,'is_junction',lambda:False)()):
            raise RuntimeError('Linked package paths are not supported: '+str(item))
    return path.resolve()


def validate_package(directory):
    directory=unlinked_path(directory)
    manifest_path=directory/MANIFEST
    unlinked_path(manifest_path)
    data=read(manifest_path)
    if data.get('schema')!=1 or not re.fullmatch(r'ahua-[a-z0-9][a-z0-9-]{0,80}',str(data.get('release_id',''))):
        raise RuntimeError('Invalid release manifest or release id')
    if data.get('scope')!='local-protected-offline-launcher':
        raise RuntimeError('Package does not target the local protected launcher')
    files=data.get('files')
    if not isinstance(files,dict)or not files or len(files)>256:
        raise RuntimeError('Bounded explicit package file manifest required')
    folded=set()
    for name,expected in files.items():
        relative=PurePosixPath(name)
        allowed=(relative.parts[:1]==('PBZBossControl',)and len(relative.parts)>=2
            and(name=='PBZBossControl/README.md'or
                (relative.parts[1]in('Scripts','Experiments')and relative.suffix=='.lua')))
        if (not allowed or relative.is_absolute()or any(p in('', '.', '..')or ':'in p for p in relative.parts)
            or '\\'in name or str(relative)!=name or name.casefold()in folded
            or not isinstance(expected,str)or not re.fullmatch('[0-9a-f]{64}',expected)):
            raise RuntimeError('Invalid or duplicate payload path: '+str(name))
        folded.add(name.casefold())
        path=unlinked_path(directory.joinpath(*relative.parts))
        if not path.is_relative_to(directory)or not path.is_file()or digest(path)!=expected:
            raise RuntimeError('Package file differs from manifest: '+name)
    required={'PBZBossControl/Scripts/main.lua','PBZBossControl/Scripts/player_entry.lua',
              'PBZBossControl/Scripts/profiles/ahua.lua','PBZBossControl/Experiments/spawn_lifecycle.lua'}
    if not required<=set(files):
        raise RuntimeError('Complete player entry and assembly are required')
    actual=set()
    for path in directory.rglob('*'):
        unlinked_path(path)
        if path.is_file():actual.add(path.relative_to(directory).as_posix())
    if actual!=set(files)|{MANIFEST}:
        raise RuntimeError('Undeclared or missing package files')
    return data


def assert_closed(root=ROOT):
    """安装状态修改仅在本机研究会话已经完整收尾后进行。"""
    root=Path(root).resolve()
    pointer=root/'runtime/latest-official-validation.json'
    if not pointer.exists():return
    path=Path(read(pointer)['state_file']).resolve()
    if not path.is_relative_to(root/'runtime'):
        raise RuntimeError('Unexpected research session pointer')
    state=read(path)
    if not state.get('restored')or state.get('remaining_box_pids')or state.get('ue4ss_deployed')and not state.get('research_loader_removed'):
        raise RuntimeError('End the current research session and remove its loader before managing the Mod')


def receipt_path(root):
    return Path(root)/'runtime/mod-installation.json'


def installed_package(root=ROOT):
    root=Path(root).resolve();receipt=read(receipt_path(root))
    if receipt.get('schema')!=1 or not receipt.get('installed'):
        raise RuntimeError('Mod is not installed; use the installation manager')
    directory=unlinked_path(Path(receipt['directory']))
    managed=unlinked_path(root/'runtime/managed-mod')
    if directory.parent!=managed:
        raise RuntimeError('Installation receipt points outside the managed Mod directory')
    data=validate_package(directory)
    if receipt.get('release_id')!=data['release_id']or receipt.get('manifest_sha256')!=digest(directory/MANIFEST):
        raise RuntimeError('Installation receipt and package do not match')
    return receipt,data,directory


def active_mod_root(root=ROOT):
    root=Path(root).resolve()
    if not receipt_path(root).exists():return root/'mod/PBZBossControl'
    receipt,_,directory=installed_package(root)
    if not receipt.get('enabled'):
        raise RuntimeError('Mod is disabled; enable it in the installation manager before assembly')
    return directory/'PBZBossControl'


def record(root,action,data):
    now=datetime.now().astimezone().isoformat()
    receipt=dict(data,at=now)
    save(receipt_path(root),receipt)
    audit=Path(root)/'evidence/installation'/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-'+action+'.json')
    save(audit,dict(receipt,action=action,formal_install_modified=False,personal_settings_modified=False))
    return receipt


def install(package,root=ROOT):
    root=Path(root).resolve();assert_closed(root)
    package=unlinked_path(package);data=validate_package(package)
    managed=unlinked_path(root/'runtime/managed-mod');managed.mkdir(parents=True,exist_ok=True)
    destination=managed/data['release_id']
    if destination.exists():
        validate_package(destination)
        if digest(destination/MANIFEST)!=digest(package/MANIFEST):
            raise RuntimeError('Existing release id has different content; preserve it')
    else:
        pending=managed/('.install-'+uuid.uuid4().hex);pending.mkdir()
        # 只复制已经列明的Mod载荷；不会复制游戏、存档、令牌或临时会话。
        for name in [*data['files'],MANIFEST]:
            target=pending/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(package/name,target)
        validate_package(pending)
        pending.rename(destination)
    return record(root,'install',{'schema':1,'installed':True,'enabled':True,
        'release_id':data['release_id'],'directory':str(destination),'manifest_sha256':digest(destination/MANIFEST),
        'release_status':data.get('status','unknown')})


def set_enabled(enabled,root=ROOT):
    assert_closed(root);receipt,_,_=installed_package(root)
    receipt['enabled']=bool(enabled)
    return record(root,'enable'if enabled else'disable',receipt)


def uninstall(root=ROOT):
    assert_closed(root);receipt,data,directory=installed_package(root)
    # 验证全部文件后才开始删除。任何未声明/修改文件都先保留，不做递归删除。
    files=[directory/name for name in [*data['files'],MANIFEST]]
    parents={parent for path in files for parent in path.parents if parent.is_relative_to(directory)}
    receipt['enabled']=False
    record(root,'disable-before-uninstall',receipt)
    for path in files:path.unlink()
    for parent in sorted(parents,key=lambda p:len(p.parts),reverse=True):
        if parent.exists()and not any(parent.iterdir()):parent.rmdir()
    return record(root,'uninstall',{'schema':1,'installed':False,'enabled':False,
        'release_id':receipt['release_id'],'removed_directory':str(directory)})


def status(root=ROOT):
    if not receipt_path(root).exists():
        return {'installed':False,'development_source_active':True,'source':str(Path(root)/'mod/PBZBossControl')}
    receipt=read(receipt_path(root))
    if receipt.get('installed'):installed_package(root)
    return receipt


def main():
    parser=argparse.ArgumentParser(description='仅管理本机研究启动器的Mod文件；不写正式游戏和存档')
    parser.add_argument('action',choices=('status','verify','install','enable','disable','uninstall'))
    parser.add_argument('package',nargs='?');args=parser.parse_args()
    if args.action=='install':
        if not args.package:parser.error('install requires a package directory')
        result=install(args.package)
    elif args.action=='verify':
        result=validate_package(Path(args.package))if args.package else installed_package()[0]
    elif args.action=='enable':result=set_enabled(True)
    elif args.action=='disable':result=set_enabled(False)
    elif args.action=='uninstall':result=uninstall()
    else:result=status()
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
