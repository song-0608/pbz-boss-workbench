"""创建可安装的固定源码候选；离线检查通过后才能构建，不标记为完整发布。"""
from datetime import datetime
import json
from pathlib import Path
import shutil
from mod_installation import ROOT,MANIFEST,digest,validate_package


def build():
    checks=ROOT/'evidence/adaptation/ahua-delivery-local-checks.json'
    local=json.loads(checks.read_text(encoding='utf-8'))
    if not local.get('passed'):raise RuntimeError('Local milestone checks must pass before building a candidate')
    for name,expected in local['source_sha256'].items():
        if digest(ROOT/name)!=expected:raise RuntimeError('Source changed after local checks: '+name)
    source=ROOT/'mod/PBZBossControl'
    paths=sorted([*source.rglob('*.lua'),source/'README.md'])
    files={'PBZBossControl/'+path.relative_to(source).as_posix():digest(path)for path in paths}
    import hashlib
    fingerprint=hashlib.sha256(json.dumps(files,sort_keys=True).encode('utf-8')).hexdigest()
    release_id='ahua-28-m2-'+fingerprint[:16]
    target=ROOT/'runtime/release-candidates'/release_id
    if target.exists():
        current=validate_package(target)
        if current['files']!=files:raise RuntimeError('Existing candidate content differs; preserve it')
        print(json.dumps({'candidate':str(target),'release_id':release_id,'existing_verified':True},ensure_ascii=False))
        return target
    target.mkdir(parents=True)
    for path in paths:
        destination=target/'PBZBossControl'/path.relative_to(source)
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,destination)
    manifest={'schema':1,'release_id':release_id,'at':datetime.now().astimezone().isoformat(),
        'scope':'local-protected-offline-launcher','status':'acceptance-candidate','complete_mod':False,
        'ability_count':28,'skill_binding_count':29,
        'exe_sha256':'4415933ce33476f14c837abb61a1b60af8b78cd81783896501913a7aac69e423',
        'local_checks_sha256':digest(checks),'source_fingerprint':fingerprint,'files':files,
        'runtime_acceptance_current':False,
        'prerequisites':'本机现有隔离启动器、Sandboxie研究环境、验证过的自编译加载器及Python；不是任意电脑便携包',
        'excluded':'游戏资源、存档、账号资料、令牌、活动会话凭据和机器专属配置不包含在Mod包中'}
    (target/MANIFEST).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    validate_package(target)
    print(json.dumps({'candidate':str(target),'release_id':release_id,'files':len(files),'complete_mod':False},ensure_ascii=False))
    return target


if __name__=='__main__':build()
