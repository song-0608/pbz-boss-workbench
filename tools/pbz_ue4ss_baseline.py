"""用途：仅向研究箱镜像部署自编译通用UE4SS，采集无玩法Mod的初始化日志。"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import time
import official_validation as v


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def verified_build_record():
    setup=v.ROOT.parent/'evidence/setup'
    pointer=setup/'selfbuilt-ue4ss-current.json'
    path=setup/'selfbuilt-ue4ss-verification.json'
    if pointer.is_file():
        current=json.loads(pointer.read_text(encoding='utf-8'))
        path=Path(current['verification_file'])
        if not path.resolve().is_relative_to(setup.resolve()) or digest(path)!=current['sha256']:
            raise RuntimeError('Current loader verification record is not intact')
    built=json.loads(path.read_text(encoding='utf-8'))
    if not built.get('compiled_from_source') or not built['practice_test']['passed']:
        raise RuntimeError('No verified self-built practice baseline')
    if 'input_regression'in built and not built['input_regression'].get('passed'):
        raise RuntimeError('Loader input regression did not pass')
    for row in built['artifacts']:
        if Path(row['path']).name in ('UE4SS.dll','dwmapi.dll') and digest(Path(row['path']))!=row['sha256']:
            raise RuntimeError('Self-built loader differs from verified build record')
    for name,key in (('UE4SS.dll','dll_sha256'),('dwmapi.dll','proxy_sha256')):
        rows=[r for r in built['artifacts']if Path(r['path']).name==name]
        if len(rows)!=1 or rows[0]['sha256']!=built['practice_test'].get(key):
            raise RuntimeError('Loader build and practice smoke evidence do not match')
    for relative,expected in built.get('input_regression',{}).get('source_sha256',{}).items():
        if digest(v.ROOT.parent/relative)!=expected:
            raise RuntimeError('Input source differs from current loader verification')
    return built,path


def remove_declared_loader(state,dll):
    """用途：进程结束后只撤除声明过且哈希一致的研究副本文件；不触碰正式安装。"""
    c=v.c;container=c.isolation.get_root(dll);work=Path(state['work'])
    target=c.isolation.virtual_file(container,c.baseline.GAME/'platform/steam')
    log=target/'ue4ss/UE4SS.log'
    if log.is_file():shutil.copy2(log,work/'UE4SS.log')
    for row in state.get('ue4ss_loader_manifest',[]):
        p=Path(row['physical_path'])
        if not p.is_relative_to(target):raise RuntimeError('Declared loader is outside virtual research target')
        if p.is_file():
            if digest(p)!=row['sha256']:raise RuntimeError('Changed research deployment file preserved for review')
            p.unlink()
    if any(Path(row['physical_path']).exists() for row in state.get('ue4ss_loader_manifest',[])):
        raise RuntimeError('Research loader removal incomplete')


def deploy_and_launch(with_signature=False, readonly_smoke=False, readonly_ai=False, readonly_hot_reload=False, load_map_hook_trial=False):
    state=json.loads(v.state_path().read_text(encoding='utf-8'));work=Path(state['work'])
    if state.get('restored') or time.time()>=state['deadline_unix'] or not state.get('offline_validation'):
        raise RuntimeError('Active offline preparation required')
    # 用途：正式文件有变化则先停止；检查发生在任何研究镜像部署写入之前。
    if v.c.baseline.formal_files()!=state['formal_before']:
        raise RuntimeError('Formal files changed; no research deployment allowed')
    proof=json.loads((v.ROOT/'evidence/latest-game-settings-isolation.json').read_text(encoding='utf-8'))
    if not proof.get('passed') or not proof.get('game_settings_write_isolation_verified'):
        raise RuntimeError('Actual game settings write isolation has not passed')
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    c.isolation.check_policy(dll,allow_offline_validation=True)
    if c.host_steam_pids(dll) or c.preflight.games_running():raise RuntimeError('Preserve existing session')
    v.verify_build()
    if not (work/'cloud-gate.json').is_file():raise RuntimeError('Current cloud screenshot review gate required')
    built,build_record=verified_build_record()
    container=c.isolation.get_root(dll)
    target=c.isolation.virtual_file(container,c.baseline.GAME/'platform/steam')
    core=target/'ue4ss';core.mkdir(parents=True,exist_ok=True)
    binary=v.ROOT.parent/'build/ue4ss-ascii/Game__Shipping__Win64/bin'
    settings=(v.ROOT.parent/'upstream/RE-UE4SS/assets/UE4SS-settings.ini').read_text(encoding='utf-8-sig')
    # 用途：首先诊断对象/名称/签名初始化；不开启玩法Mod及可选运行时Hook，不猜布局。
    for key in re.findall(r'(?m)^(Hook\w+)\s*=',settings):
        settings=re.sub(r'(?m)^'+key+r'\s*=.*$',key+' = 0',settings)
    for key,value in {'ConsoleEnabled':'0','GuiConsoleEnabled':'0','GuiConsoleVisible':'0',
            'UseCache':'0','DoEarlyScan':'0','SecondsToScanBeforeGivingUp':'40',
            # 已通过初始化的交互入口使用加载器原生对象缓存；删除监听器负责失效。
            # 保留GUObjectArray查找与全部Lua身份/引擎有效性检查。初次诊断仍关闭缓存。
            'bUseUObjectArrayCache':'true' if readonly_ai else 'false',
            'bForceGUObjectArrayForIteration':'true'}.items():
        settings=re.sub(r'(?m)^'+key+r'\s*=.*$',key+' = '+value,settings)
    if readonly_hot_reload:
        if not readonly_ai:raise RuntimeError('Hot reload is only for declared read-only AI experiment')
        settings=re.sub(r'(?m)^EnableHotReloadSystem\s*=.*$','EnableHotReloadSystem = 1',settings)
    if readonly_smoke or readonly_ai:
        # 用途：仅在无Mod初始化和菜单均已实测后，开启游戏线程读取所需的唯一可选Hook。
        if not with_signature:raise RuntimeError('PBZ smoke requires own verified profile')
        initialized=json.loads((v.ROOT/'evidence/adaptation/latest-initialization.json').read_text(encoding='utf-8'))
        if not initialized.get('ue4ss_event_loop_started') or not initialized.get('menu_verified'):
            raise RuntimeError('No verified PBZ initialization and menu baseline')
        settings=re.sub(r'(?m)^HookEngineTick\s*=.*$','HookEngineTick = 1',settings)
        settings=re.sub(r'(?m)^EngineTickResolveMethod\s*=.*$','EngineTickResolveMethod = Scan',settings)
    if readonly_ai:
        # 用途：真实进度副本隔离和场景引用先通过，才允许这一批只读查询脚本进入地图。
        if readonly_smoke:raise RuntimeError('Choose one research Lua batch')
        isolation=json.loads((v.ROOT/'evidence/latest-gameplay-save-isolation.json').read_text(encoding='utf-8'))
        metadata=json.loads((v.ROOT/'evidence/adaptation/latest-batch-character-metadata.json').read_text(encoding='utf-8'))
        if not isolation.get('passed') or not metadata.get('player_controller_pawn_verified'):
            raise RuntimeError('Game-authored save/reload isolation and reciprocal scene references required')
    if load_map_hook_trial:
        if not (with_signature and readonly_ai and readonly_hot_reload):
            raise RuntimeError('LoadMap hook requires the declared protected offline player research stack')
        # 受保护玩家入口也必须开启；注册Lua回调不会自动启用引擎detour。
        settings=re.sub(r'(?m)^HookLoadMap\s*=.*$','HookLoadMap = 1',settings)
    contents={'dwmapi.dll':(binary/'dwmapi.dll').read_bytes(),
              'ue4ss/UE4SS.dll':(binary/'UE4SS.dll').read_bytes(),
              'ue4ss/UE4SS-settings.ini':settings.encode('utf-8'),
              'ue4ss/Mods/mods.txt':b'; No gameplay mods in this read-only initialization experiment.\n'}
    if readonly_smoke:
        contents['ue4ss/Mods/mods.txt']=b'PBZReadOnlySmoke : 1\n'
        contents['ue4ss/Mods/PBZReadOnlySmoke/Scripts/main.lua']=(v.ROOT/'adaptation/pbz-26367565/Mods/PBZReadOnlySmoke/Scripts/main.lua').read_bytes()
    if readonly_ai:
        contents['ue4ss/Mods/mods.txt']=b'PBZObserveAI : 1\n'
        contents['ue4ss/Mods/PBZObserveAI/Scripts/main.lua']=(v.ROOT/'adaptation/pbz-26367565/Mods/PBZObserveAI/Scripts/main.lua').read_bytes()
    if with_signature:
        # 用途：只接受本项目亲自推导且完成静态唯一性/原版运行只读验证的固定配置。
        profile=v.ROOT/'adaptation/pbz-26367565'
        checked=json.loads((v.ROOT/'evidence/adaptation/profile-verification.json').read_text(encoding='utf-8'))
        probe=json.loads((v.ROOT/'evidence/adaptation/latest-object-array-probe.json').read_text(encoding='utf-8'))
        if not checked.get('passed') or not probe.get('passed'):
            raise RuntimeError('Own signature has not passed static and original-runtime structural checks')
        for relative in ('UE4SS_Signatures/GUObjectArray.lua','MemberVariableLayout.ini'):
            source=profile/relative
            if digest(source)!=checked['files'][relative]:raise RuntimeError('Adaptation file changed after verification')
            contents['ue4ss/'+relative]=source.read_bytes()
    if digest(binary/'UE4SS.dll')!=next(row['sha256'] for row in built['artifacts'] if Path(row['path']).name=='UE4SS.dll'):
        raise RuntimeError('Self-built DLL differs from verified build record')
    for relative in contents:
        if (target/relative).exists():raise RuntimeError('Existing research artifact must be reviewed before deployment')
    manifest=[{'physical_path':str(target/name),'sha256':hashlib.sha256(data).hexdigest()} for name,data in contents.items()]
    # 用途：先记录所有拟部署文件，再写入，确保独立看门狗能在异常或超时后收尾。
    state.update({'ue4ss_deployed':True,'readonly_ue4ss_experiment':True,'readonly_ai_experiment':readonly_ai,'readonly_hot_reload_enabled':readonly_hot_reload,'ue4ss_loader_manifest':manifest})
    v.save(v.state_path(),state)
    for name,data in contents.items():
        p=target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    v.verify_build(manifest)
    # 保存本轮实际设置，供性能对比和缓存销毁验收核对；不含账号/存档。
    (work/'loader-settings.ini').write_text(settings,encoding='utf-8')
    v.save(work/'selfbuilt-baseline-deployment.json',{'at':v.utc8(),'compiled_from_source':True,
        'object_lookup_cache_enabled':bool(readonly_ai),
        'loader_settings_sha256':digest(work/'loader-settings.ini'),
        'build_verification_file':str(build_record),'build_verification_sha256':digest(build_record),
        'source_revision':built['main_revision'],'dll_sha256':digest(binary/'UE4SS.dll'),
        'physical_target':str(target),'formal_install_modified':False,'lua_mods_enabled':readonly_smoke or readonly_ai,
        'readonly_smoke_enabled':readonly_smoke,'readonly_ai_enabled':readonly_ai,'engine_tick_hook_enabled':readonly_smoke or readonly_ai,
        'custom_aob_used':with_signature,'custom_offsets_used':with_signature,'all_pbz_network_blocked':True})
    v.launch(offline=True,readonly_ue4ss=True)
    print(json.dumps({'research_loader_deployed':True,'formal_install_modified':False,'source_built':True}))


if __name__=='__main__':
    if sys.argv[1:]==['--deploy-and-launch']:deploy_and_launch()
    elif sys.argv[1:]==['--deploy-own-signature-and-launch']:deploy_and_launch(with_signature=True)
    elif sys.argv[1:]==['--deploy-readonly-smoke-and-launch']:deploy_and_launch(with_signature=True,readonly_smoke=True)
    elif sys.argv[1:]==['--deploy-readonly-ai-and-launch']:deploy_and_launch(with_signature=True,readonly_ai=True)
    elif sys.argv[1:]==['--deploy-readonly-ai-hot-reload-and-launch']:deploy_and_launch(with_signature=True,readonly_ai=True,readonly_hot_reload=True)
    else:raise RuntimeError('Use --deploy-and-launch or --deploy-own-signature-and-launch after cloud-OFF review')
