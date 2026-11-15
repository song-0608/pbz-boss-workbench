"""用途：在训练入口收尾后统一整理当前说明、证据、简历和本机归档；不触碰正式存档。"""
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, text):
    path.write_text(text.rstrip() + '\n', encoding='utf-8')


def main():
    owner = read(ROOT / 'runtime/ahua-practice.json')
    state = read(Path(owner['state_file']))
    post = read(ROOT / 'evidence/latest-native-diagnostic-postcheck.json')
    local = read(ROOT / 'evidence/adaptation/ahua-delivery-local-checks.json')
    historical = read(ROOT / 'evidence/adaptation/ahua-protected-interactive-milestone.json')
    if (not state['restored'] or post['validation_state'] != owner['state_file']
            or post['formal_files_changed'] or not post['research_box_empty']
            or not post['research_loader_removed'] or not local['passed'] or not historical['passed']):
        raise RuntimeError('Delivery requires matching finished practice and successful checks')
    work = Path(state['work'])
    log = (work / 'UE4SS.log').read_text(encoding='utf-8', errors='replace')
    segment = log[log.rfind('PBZ_CONTROL_LIFECYCLE:DEFERRED_ACTOR='):]
    ready = re.search(r'INTERACTIVE_READY=.*cleanup in (\d+) seconds', segment)
    checks = {'practice_ready': ready is not None,
              'practice_enter': 'enter success=true state=ACTIVE' in segment,
              'practice_exit': 'exit success=true state=OFF' in segment,
              'input_barrier': 'INPUT_BARRIER_CONSTRUCTED=true' in segment,
              'original_player_position_unchanged': 'ORIGINAL_PLAYER_POSITION_DELTA=0.0' in segment,
              'original_player_no_new_active_ability': 'ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0' in segment,
              'formal_files_unchanged': not post['formal_files_changed'],
              'research_box_empty': post['research_box_empty'],
              'research_loader_removed': post['research_loader_removed']}
    if not all(checks.values()):
        raise RuntimeError('Practice entrance checks incomplete: ' + str(checks))
    now = datetime.now().astimezone().isoformat()
    # 用途：把本版入口的失败启动也计入记录，不能只保留通过的一轮声称一次就成功。
    attempts = []
    for path in sorted((ROOT / 'runtime').glob('official-validation-*/state.json')):
        prior = read(path)
        if prior.get('test_purpose') == 'User-operated protected Ahua four-key offline practice; no map exploration':
            prior_log = Path(prior['work']) / 'UE4SS.log'
            prior_text = prior_log.read_text(encoding='utf-8', errors='replace') if prior_log.exists() else ''
            attempts.append({'session': str(path), 'launch_requested': bool(prior.get('launch_requested_at')),
                             'restored': prior.get('restored', False),
                             'formal_files_changed_count': len(prior.get('formal_files_changed', [])),
                             'stopped_before_spawn_for_player_velocity': 'ISSUE_START=' in prior_text and 'stop moving before entering boss control' in prior_text,
                             'temporary_actor_initialization_expired': 'temporary actor expired during initialization' in prior_text})
    launches = sum(attempt['launch_requested'] for attempt in attempts)
    evidence = {'at': now, 'session': owner['state_file'], 'checks': checks, 'passed': True,
                'scheduled_practice_seconds': int(ready.group(1)),
                'full_ten_minute_stability_tested': False,
                'game_launches_for_this_delivery': launches, 'attempts': attempts,
                'four_skill_key_evidence': str(ROOT / 'evidence/adaptation/ahua-protected-interactive-milestone.json'),
                'source_check_report': str(ROOT / 'evidence/adaptation/ahua-delivery-local-checks.json'),
                'log_sha256': hashlib.sha256((work / 'UE4SS.log').read_bytes()).hexdigest(),
                'formal_file_count': post['formal_file_count'], 'complete_all_boss_mod': False}
    write(ROOT / 'evidence/adaptation/ahua-practice-entry-milestone.json', json.dumps(evidence, ensure_ascii=False, indent=2))

    # 用途：留存旧说明后更新当前入口；旧编号实测报告不改写历史结论。
    history = ROOT / 'evidence/status-history' / datetime.now().strftime('%Y%m%d-%H%M%S-delivery')
    history.mkdir(parents=True)
    for name in ('00-项目目标与现状.md', '04-当前结果与下一关.md', '34-简历与面试素材-开发中.md', '项目状态.json'):
        source = ROOT / name
        (history / name).write_bytes(source.read_bytes())

    write(ROOT / '00-项目目标与现状.md', r'''# 影之刃零：Boss离线操控与AI研究

更新：2026-11-13。主线是玩家操控Boss和使用其真实技能，先支持新娘阿花。

## 从哪里开始

双击本目录或 `D:\mod文档` 的 **开始阿花训练.cmd**。详细步骤看 **37-阿花训练版操作卡.md**，实际交付检查与限制看 **38-阿花训练版交付记录.md**。

当前支持：临时阿花、训练敌人、第三人称镜头、移动、四个技能键、F10退出恢复。四键已有保护后的真实按键记录；三项攻击另有逐招配对掉血证据。新的中文入口已经单轮实机启用并完成恢复和收尾，未重复旧功能的全部测试。

这是有时间上限的离线训练版，不等于所有Boss、阿花全部技能、任意地图均可玩。

## 技术基础

- 通用UE4SS源码已自主编译；标准练习使用本机实际UE5.8.1，不冒充完成UE5.7靶场。
- 固定PBZ构建已有自写GUObjectArray AOB及反射布局；不推断更新后兼容，也不把“魔改UE5.7.4”当作已经完整核定的版本结论。
- 从真实授予能力、原生AI焦点与技能目标查询接入阿花技能。只设置锁定组件曾不足以让Boss技能找到敌人。
- 当前使用遥控：原PlayerController仍拥有主角，Boss保留原AIController作为技能目标桥；停止其自主决策，转发玩家的移动与出招意图。

## 存档保护

正式安装：`E:\SteamLibrary\steamapps\common\PBZ`。加载器只放研究箱的物理镜像，结束撤除。每轮取新的正式文件基线，只复制到研究副本；不回写、不自动回档。旧备份与当前文件不同可能来自正常游玩，不会因此覆盖你的新进度。

各轮核验范围见第38号和对应证据，不能把一次无变化推广为未来任何操作都绝对安全。所有新增资料在 `D:\mod文档`，不放桌面。

## 尚待完成

阿花更多招式与阶段、自由目标切换、死亡切图完整恢复、相机组件彻底注销回收、长时间稳定性和其他Boss。正式通用 `Scripts/main.lua` 保持默认禁用；只有完成外部隔离核对的限时训练入口会装配四项能力。

旧编号报告保留当时结论。当前以第37、38号与项目状态.json为准。
''')
    write(ROOT / '04-当前结果与下一关.md', '''# 当前结果与下一关

双击 **开始阿花训练.cmd**，按中文窗口顺序准备研究副本、启动隔离游戏、启用阿花。零基础操作看第37号；本次交付和实机验收看第38号。

已通过：阿花遥控、第三人称镜头、W移动、鼠标转向、四个技能键、F10恢复、三项攻击逐招掉血观测。原主角保护后的位置变化0，新激活能力0。

后续工作：更多阿花招式和阶段、自由选择目标、其他Boss、死亡切图完整恢复、相机组件回收。不再继续无目的探图；未完成的部分不会标成已完成。

源码在 mod/PBZBossControl/Scripts，简历材料在第34号。主入口的默认禁用和限时训练入口是不同入口，请勿手动把全部verified改为true。
''')
    count = post['formal_file_count']
    write(ROOT / '38-阿花训练版交付记录.md', f'''# 阿花离线训练版 v0.1：交付记录

整理时间：{now}

## 本次已交付

- `开始阿花训练.cmd` 与中文按钮窗口；准备隔离副本、启动研究游戏、启用阿花、结束训练四步集中管理。
- 中文操作卡（第37号）、实际按键CSV、带用途注释的Lua源码、自编译UE4SS和自写签名/布局的追溯路径。
- 更新后的项目状态、工作台P/H入口、简历与面试素材。

## 验证结果

- 复用上一轮保护后四键整体验收：F6、W、鼠标、F1至F4、F10通过；原主角位置变化0、新激活能力0。
- 本版入口测试实际启动 **{launches}个研究游戏会话**。前两轮分别暴露主角静止前置条件与临时角色初始化回收问题，均正常收尾。随后加入静止等待、顺序初始化及清理后的同进程有限重试，再检查装配、F6进入、F10恢复、输入屏障与正式文件保护，不重复所有旧功能。
- 训练时长装配为 **{evidence['scheduled_practice_seconds']}秒上限**；本次是短时入口验收，未声称跑满10分钟稳定性。
- 收尾：本轮记录的 **{count}个正式文件零变化**，研究箱为空，加载器撤除；没有将训练副本或旧备份回写正式目录。
- 本地Python语法、{local['lua_syntax_files']}份Lua语法、中文窗口创建和输入/保护/调度夹具通过；本地测试与游戏内测试分别记录。

## 证据入口

- `evidence/adaptation/ahua-protected-interactive-milestone.json`：上一轮四键与恢复。
- `evidence/adaptation/ahua-remote-control-milestone.json`：逐招激活、自然结束与配对掉血；不把失败招式的后续掉血算成功。
- `evidence/adaptation/ahua-practice-entry-milestone.json`：本轮新入口。
- `evidence/adaptation/ahua-delivery-local-checks.json`：本地语法和夹具。
- `evidence/latest-native-diagnostic-postcheck.json`：本轮收尾。

## 没有交付成什么

它仍不是全Boss完整Mod。尚不支持自由选敌、所有招式和阶段、任意关卡长期游玩及死亡切图完整恢复。相机Actor/相机臂在销毁请求后仍可能可查询，彻底注销与GC没有验收；训练结束会关闭研究进程。本版没有左键Boss普攻，也没有解锁Boss或推进正式剧情。

## 本机归档

`归档包` 内的新ZIP保存本项目源码、工具、操作卡、有限证据和自编译加载器，不包含正式/研究存档、Steam账号缓存、游戏资产或上游完整私有依赖源码。

这是本机恢复归档，依赖当前已安装的Python、Sandboxie、Steam和合法PBZ；不是给其他电脑直接运行的通用安装包。正常启动继续使用总目录的cmd，不需要先解压ZIP。
''')
    write(ROOT / '34-简历与面试素材-开发中.md', '''# 简历与面试素材：UE4SS适配与阿花操控训练

只写有源码和实机证据的成果；定位为个人离线研究项目、四键训练原型。

## 简历可用文案

**UE运行时适配与Boss操控原型｜个人项目**

- 从通用UE4SS源码自主构建，在自制UE5.8.1靶场验证加载；针对固定PBZ构建分析GUObjectArray AOB和反射成员布局，打通Lua运行时访问。
- 拆分输入、角色会话、AI暂停、阵营目标与镜头模块，实现新娘阿花遥控、第三人称镜头及四个真实能力键；三项攻击在临时训练敌人上观察到配对掉血，保留原有冷却和状态限制。
- 定位“锁定组件成功但技能目标为空”的接口差异，通过原AIController焦点接入技能查询；保留Boss控制器并停止其自主决策，避免简单Possess破坏技能依赖。
- 用事务式状态快照保存并恢复主角、输入和镜头；加入原主角隐藏、碰撞/移动与受伤标志保护，实机批次确认位置不变、未出现新的主角活动能力和F10恢复。
- 将实验封装为独立离线训练入口，按轮复制进度与核对正式文件，采用同进程批量排错，避免逐问题重启。

## 面试口述

“我研究的是Boss自主AI如何切换为玩家驱动。先从通用UE4SS构建和标准UE靶场入手，再为目标构建自己推导签名和反射布局。最开始直接接管并不够：镜头、输入和Boss技能的目标查询都依赖原游戏体系。尤其是锁定组件有值不代表技能能读到敌人，所以后来采用遥控，保留Boss的AIController，停止自主决策，再转发玩家输入，并设置真实AI焦点。技能从已授予列表匹配真实类，读取活动计数判断结束。当前实现了阿花四键训练，其中三项攻击有配对掉血观测；F10能恢复主角。死亡切图、更多招式和多人系统没有完成，我会明确区分设计方案与实测能力。”

## 你需要自己能解释

1. AOB通配符、唯一命中和RIP相对地址为何都必须核对。
2. 反射布局/函数参数变化如何使通用调用失效；例如此构建生成函数的Scale参数。
3. 停止Brain与外层AI组件、保留Controller和目标焦点分别解决什么问题。
4. 为何37项授予能力不能叫37个可玩技能；为何掉血要与成功激活的具体招式配对。
5. F10恢复、异常状态和研究箱结束分别负责哪些清理；销毁请求不等于立即GC。

多人AI仅作为后续自有UE项目方案：服务器持有仇恨与目标决策权，客户端提交意图并表现。没有实现的同步、全Boss和跨版本自动适配不要写入已完成项。
''')
    with (ROOT / '39-玩家实际按键表.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['按键', '功能', '范围与证据'])
        writer.writerows([['F6', '开始遥控新娘阿花', '研究副本临时角色，实机通过'],
                          ['W/A/S/D', '镜头相对移动', 'W实机通过，四向逻辑夹具通过'],
                          ['鼠标移动', '第三人称镜头', '实机通过'],
                          ['F1', '技能01', '键盘激活、自然结束、配对掉血观测'],
                          ['F2', '重击01', '同上'], ['F3', '技能02', '同上'],
                          ['F4', '冲刺', '键盘激活与自然结束，不作为伤害招式'],
                          ['F10', '回主角', '实机恢复通过'], ['鼠标左键', '没有绑定Boss普攻', '原主角输入由屏障阻断']])
    status = read(ROOT / '项目状态.json')
    status.update(updated_at=now, status='ahua-four-key-offline-practice-v0.1',
        status_summary='阿花四键离线训练入口已单轮实机启用并恢复；完整Boss系统仍在开发。',
        protected_interactive_controls_verified=True, practice_entry_runtime_verified=True,
        real_bridge_available=True, boss_control_verified=True,
        boss_control_verification_scope='Owned temporary Ahua, four-key bounded offline practice only; not all bosses/full game',
        runtime_launch_allowed=True, runtime_launch_scope='ahua_practice.py owned offline isolated lease only',
        latest_result_note=str(ROOT / '38-阿花训练版交付记录.md'),
        latest_practice_evidence=str(ROOT / 'evidence/adaptation/ahua-practice-entry-milestone.json'),
        latest_formal_file_check_at=post['checked_at'], latest_formal_file_check_changed_count=0,
        latest_camera_screenshot=str(ROOT / 'evidence/official-validation/20261113-121801/ahua-input-barrier-preview.png'),
        blocked_reason='四键训练版可用；完整技能、目标切换、死亡切图和组件回收仍待验收',
        not_done=['阿花更多招式与阶段条件', '自由目标切换与其他Boss', '死亡切图完整恢复', '相机组件注销回收与长期稳定性'],
        blocking_items=['全Boss完整Mod尚未完成', '不应把短时训练用于正式存档或剧情通关'],
        next_action='围绕Boss更多真实技能和可玩性继续开发，不继续无目的地图探索',
        no_remaining_pbz_processes_verified=True, research_loader_currently_deployed=False,
        research_loader_removed=True, formal_loader_deployed=False,
        note='本机四键离线训练版；正式通用主入口仍默认禁用，不是全Boss成品')
    write(ROOT / '项目状态.json', json.dumps(status, ensure_ascii=False, indent=2))
    top = ROOT.parent / '00-从这里开始.md'
    text = top.read_text(encoding='utf-8-sig')
    marker = '**当前主线入口（2026-11-13）：**'
    if marker not in text:
        text = text.replace('以后只打开这个文件夹：**D:\\mod文档**。',
            '以后只打开这个文件夹：**D:\\mod文档**。\n\n' + marker + ' 双击 `开始阿花训练.cmd`。按中文窗口操作，详细说明在 `PBZ-Boss操控研究/37-阿花训练版操作卡.md`，交付验证在第38号。')
    text = text.replace('前置审计、存档备份、技能与按键草案；尚无可玩Mod', '阿花四键离线训练、UE4SS自适配源码、按键卡和证据；完整Boss体系继续开发')
    write(top, text)
    top_readme = ROOT.parent / 'README.md'
    text = top_readme.read_text(encoding='utf-8-sig')
    intro = '''> 当前状态（2026-11-13）：资料已统一到 D:\\mod文档。双击 **开始阿花训练.cmd**，使用阿花四键离线训练窗口；操作卡看第37号，交付证据与限制看第38号。以下涉及H盘、桌面、源码权限或尚未编译的表述是早期历史记录；当前以PBZ项目状态为准。

'''
    if not text.startswith('> 当前状态（2026-11-13）'):
        write(top_readme, intro + text)
    entrance = ROOT.parent / '00-使用入口/先读我.txt'
    text = entrance.read_text(encoding='utf-8-sig')
    if '4 阿花离线训练' not in text:
        write(entrance, '当前主线：双击“4 阿花离线训练”。操作卡在 PBZ-Boss操控研究/37-阿花训练版操作卡.md。\n\n' + text)

    # 用途：只归档已列出的项目文件，不递归加入沙盒、存档、账号缓存或大体积上游依赖。
    included = set()
    for directory, pattern in [('mod', '*'), ('tools', '*.py'), ('tests', '*'), ('adaptation/pbz-26367565', '*')]:
        for source in (ROOT / directory).rglob(pattern):
            if source.is_file() and '__pycache__' not in source.parts and source.suffix.lower() in ('.lua', '.py', '.cpp', '.ini', '.txt', '.cmd'):
                included.add(source)
    included.update(ROOT.glob('*.md'))
    included.update(ROOT.glob('*.csv'))
    included.update([ROOT / '开始阿花训练.cmd', ROOT / '打开研究工作台.cmd', ROOT / '项目状态.json'])
    for name in ('ahua-protected-interactive-milestone.json', 'ahua-practice-entry-milestone.json', 'ahua-remote-control-milestone.json', 'ahua-delivery-local-checks.json'):
        included.add(ROOT / 'evidence/adaptation' / name)
    archive = ROOT / '归档包' / ('阿花四键离线训练-v0.1-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=5) as package:
        for source in sorted(included):
            package.write(source, 'PBZ-Boss操控研究/' + source.relative_to(ROOT).as_posix())
        binary = ROOT.parent / 'build/ue4ss-ascii/Game__Shipping__Win64/bin'
        for name in ('UE4SS.dll', 'dwmapi.dll'):
            package.write(binary / name, '自编译UE4SS/' + name)
        package.writestr('本机恢复说明.txt', '本包为源码与本机恢复归档，非独立安装器。正常使用 D:\\mod文档\\开始阿花训练.cmd。需要当前Python、Sandboxie、Steam和合法PBZ。禁止将研究存档写回正式存档。\n')
    with zipfile.ZipFile(archive) as package:
        if package.testzip() is not None:
            raise RuntimeError('Archive CRC failed')
        files = len(package.namelist())
    package_info = {'created_at': now, 'archive': str(archive), 'bytes': archive.stat().st_size, 'files': files,
                    'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'crc_verified': True,
                    'edition': 'Ahua four-key bounded offline practice v0.1', 'complete_all_boss_mod': False,
                    'raw_save_backup_included': False, 'steam_account_cache_included': False,
                    'standalone_installer': False, 'runtime_acceptance_report': str(ROOT / 'evidence/adaptation/ahua-practice-entry-milestone.json')}
    write(ROOT / '归档包/latest-package.json', json.dumps(package_info, ensure_ascii=False, indent=2))
    print(json.dumps({'finished': True, 'files_in_archive': files, 'archive': str(archive), 'checks': checks}, ensure_ascii=False))


if __name__ == '__main__':
    main()
