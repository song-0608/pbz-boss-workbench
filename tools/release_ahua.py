"""全部验收门槛通过后，从不可变候选创建本机离线发布包；不启动游戏。"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil

from collect_release_readiness import collect
from mod_installation import ROOT, MANIFEST, assert_closed, digest, validate_package


def release(candidate):
    assert_closed()
    candidate=Path(candidate).resolve()
    manifest=validate_package(candidate)
    report=collect(candidate)
    if not report['ready_for_release']:
        missing=[key for key,value in report['gates'].items() if not value]
        raise RuntimeError('Incomplete acceptance; no release created: '+', '.join(missing))
    if digest(candidate/MANIFEST)!=report['candidate_manifest_sha256']:
        raise RuntimeError('Candidate changed during acceptance review')
    code_fingerprint=hashlib.sha256(json.dumps(report['module_source_sha256'],sort_keys=True).encode('utf-8')).hexdigest()
    release_id='ahua-28-v1-'+code_fingerprint[:16]
    target=ROOT/'releases'/release_id
    if target.exists():
        existing=validate_package(target)
        unchanged=all(existing['files'].get(name)==sha for name,sha in manifest['files'].items()
                      if name!='PBZBossControl/README.md')
        if existing.get('complete_mod') is not True or not unchanged or existing.get('accepted_candidate')!=manifest['release_id']:
            raise RuntimeError('Existing release differs; preserve it')
        witness=ROOT/existing['acceptance_report']
        if digest(witness)!=existing['acceptance_report_sha256']:
            raise RuntimeError('Immutable release acceptance record changed')
        return target
    target.mkdir(parents=True)
    for name in manifest['files']:
        destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(candidate/name,destination)
    readme=target/'PBZBossControl/README.md'
    content=readme.read_text(encoding='utf-8')
    table_start=content.index('| 默认键 |')
    table_end=content.index('\n\n',table_start)
    key_table=content[table_start:table_end]
    content='''# 新娘阿花离线操控 Mod v1

本版提供28项独立能力、29个技能绑定。普通按键的自然结束、活动取消与完整恢复、全部绑定、满600秒稳定性及正常加载闭环均通过同一源码实机验收。

## 开始使用

在现有项目根目录双击“开始阿花训练.cmd”，按窗口步骤准备隔离副本、核对研究Steam云同步关闭、启动研究游戏、进入场景并启用。请保留本项目现有Sandboxie环境、自编译加载器和Python运行时；此包供当前本机启动器安装使用。

如需重新安装，双击“管理阿花Mod.cmd”，选择本发布目录安装并启用。安装管理会逐文件校验；停用或卸载前须先结束研究会话。安装及卸载均保留个人键位和设置。

## 操作

F6接管、WASD移动、鼠标转向、F7切换可见敌对目标、F10恢复主角。Esc先恢复主角，再按一次打开原菜单。正常重载请在恢复后选择“系统→退出游戏→返回至开始界面”，再“继续游戏”；新场景就绪后自动装配，仍需F6主动接管。

'''+key_table+'''

“技能与按键设置”可改键，下次装配生效。状态层显示本次实际绑定、生命和目标。出招仍受视线、距离、目标存活及冷却限制；激活不保证命中。

## 结束与支持范围

F10仅退出操控；结束整轮请点击启动器“结束本轮训练并核对正式存档”。每轮最多20分钟，每次装配最多10分钟；到时自动收尾。正式游戏和存档不安装加载器，研究进度不回写，也不自动回档。

仅支持当前核定PBZ构建和本机隔离启动器，不是任意电脑可用的便携包。程序SHA-256为`4415933ce33476f14c837abb61a1b60af8b78cd81783896501913a7aac69e423`，不匹配会拒绝装配。已验证溪谷局部地形；无合适同层落点或视线时拒绝生成，需由玩家移动至开阔地面站稳后再启用。

三项配对抓取能力保持隔离，六项被动/工具保留原生授予。支持上述恢复后原菜单重载路径；直接OpenLevel诊断不作为玩法加载方式。跨版本、其他Boss和所有关卡不在本版支持范围内。

本包不含游戏资源、存档、账号或临时会话凭据。版本、每个文件的SHA-256及不可变验收报告见上级目录`pbz-release.json`。
'''
    readme.write_text(content,encoding='utf-8')
    manifest['files']['PBZBossControl/README.md']=digest(readme)
    manifest['source_fingerprint']=hashlib.sha256(json.dumps(manifest['files'],sort_keys=True).encode('utf-8')).hexdigest()
    acceptance=ROOT/'evidence/releases'/(release_id+'-acceptance.json')
    acceptance.parent.mkdir(parents=True,exist_ok=True)
    if acceptance.exists():raise RuntimeError('Preserve existing immutable release acceptance record')
    shutil.copy2(ROOT/'evidence/adaptation/ahua-release-readiness.json',acceptance)
    manifest.update(release_id=release_id,at=datetime.now().astimezone().isoformat(),status='release',
                    complete_mod=True,runtime_acceptance_current=True,
                    accepted_candidate=report['release_id'],
                    acceptance_report=acceptance.relative_to(ROOT).as_posix(),
                    acceptance_report_sha256=digest(acceptance),
                    local_checks_sha256=digest(ROOT/'evidence/adaptation/ahua-delivery-local-checks.json'),
                    supported_travel='原菜单加载前完整恢复主角，旧World退役后自动装配；不使用直接OpenLevel诊断作为加载方式')
    (target/MANIFEST).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    validate_package(target)
    print(json.dumps({'release':str(target),'release_id':release_id,'complete_mod':True},ensure_ascii=False))
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('candidate');args=parser.parse_args()
    release(args.candidate)
