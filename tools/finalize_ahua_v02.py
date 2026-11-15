"""用途：按真实证据整理F7双目标训练版；不把候选出招、掉血、完整Boss成品混写。"""
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


def skill_rows(text):
    pattern = (r'KEY_SKILL_END=(\w+)\|peak=(\d+)\|active=(\d+)\|natural=(true|false)'
               r'\|health_before=([\d.-]+)\|health_after=([\d.-]+)\|distance=([\d.eE+-]+)')
    return [{'id': a, 'peak': int(b), 'active_after': int(c), 'natural_finish': d == 'true',
             'health_before': float(e), 'health_after': float(f), 'position_delta': float(g),
             'damage_observed_in_window': float(e) > float(f)}
            for a, b, c, d, e, f, g in re.findall(pattern, text)]


def main():
    owner = read(ROOT / 'runtime/ahua-practice.json')
    state = read(Path(owner['state_file']))
    post = read(ROOT / 'evidence/latest-native-diagnostic-postcheck.json')
    local = read(ROOT / 'evidence/adaptation/ahua-delivery-local-checks.json')
    if (not state.get('restored') or post['validation_state'] != state['state_file']
            or post['formal_files_changed'] or post['host_config_files_changed']
            or not post['host_registry_unchanged'] or not post['research_box_empty']
            or not post['research_loader_removed'] or not local['passed']):
        raise RuntimeError('Finished matching session, unchanged formal files and passed local checks required')
    for name, expected in local['source_sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Source changed after checks: ' + name)
    work = Path(state['work'])
    text = (work / 'UE4SS.log').read_text(encoding='utf-8', errors='replace')
    current = text[text.rfind('PBZ_CONTROL_LIFECYCLE:DEFERRED_ACTOR='):]
    selected = re.findall(r'\[PBZBossControl\] target verified: ([^\r\n]+)', current)
    initial_match = re.search(r'INTERACTIVE_TARGET=([^\r\n]+)', current)
    initial = initial_match.group(1) if initial_match else None
    skills = skill_rows(current)
    scheduled = int(re.search(r'INTERACTIVE_READY=.*cleanup in (\d+) seconds', current).group(1))
    checks = {
        'default_ready_with_f7': 'F7 target' in current and 'INTERACTIVE_READY=' in current,
        'unverified_skill_keys_disabled': 'F5/F8 experimental skills' not in current and not owner.get('expanded'),
        'entered_control': 'enter success=true state=ACTIVE' in current,
        'two_different_target_queries_observed': initial is not None and any(name != initial for name in selected),
        'target_cycle_returned_to_initial': len(selected) >= 2 and selected[-1] == initial,
        'skill01_natural_finish_and_damage': any(r['id'] == 'skill_01' and r['natural_finish'] and r['damage_observed_in_window'] for r in skills),
        'exit_restoration': 'exit success=true state=OFF' in current,
        'original_player_position_unchanged': 'ORIGINAL_PLAYER_POSITION_DELTA=0.0' in current,
        'original_player_no_new_active_ability': 'ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0' in current,
        'input_barrier': 'INPUT_BARRIER_CONSTRUCTED=true' in current,
    }
    if not all(checks.values()):
        raise RuntimeError('Current release runtime checks incomplete: ' + str(checks))
    # 用途：此前同进程失败保留在报告中，绝不只抽最后一段成功伪称首次成功。
    prior_work = ROOT / 'evidence/official-validation/20261113-131356'
    prior = (prior_work / 'UE4SS.log').read_text(encoding='utf-8', errors='replace')
    prior_post = read(prior_work / 'postcheck.json')
    if prior_post['formal_files_changed'] or not prior_post['research_box_empty']:
        raise RuntimeError('Prior development session postcheck required')
    failed_work = ROOT / 'evidence/official-validation/20261113-133045'
    failed_text = (failed_work / 'UE4SS.log').read_text(encoding='utf-8', errors='replace')
    failed_post = read(failed_work / 'postcheck.json')
    if failed_post['formal_files_changed'] or not failed_post['research_box_empty']:
        raise RuntimeError('Failed release session postcheck required')
    now = datetime.now().astimezone().isoformat()
    live_modules = {}
    cosmetic_changes = []
    marker = '/Mods/PBZObserveAI/Scripts/'
    for row in state['ue4ss_loader_manifest']:
        physical = row['physical_path'].replace('\\', '/')
        if marker not in physical:
            continue
        relative = physical.split(marker, 1)[1]
        source = ROOT / 'mod/PBZBossControl/Scripts' / relative
        if relative == 'main.lua' or not source.exists():
            continue
        live_modules[relative] = row['sha256']
        if hashlib.sha256(source.read_bytes()).hexdigest() != row['sha256']:
            if relative not in ('profiles/ahua.lua', 'config.lua'):
                raise RuntimeError('Runtime module changed after acceptance: ' + relative)
            cosmetic_changes.append(relative)
    report = {'at': now, 'passed': True, 'version': 'v0.2', 'session': owner['state_file'],
              'checks': checks, 'initial_target': initial, 'verified_target_queries': selected,
              'live_module_sha256': live_modules,
              'post_runtime_cosmetic_label_comment_changes': cosmetic_changes,
              'current_skill_samples': skills, 'formal_file_count': post['formal_file_count'],
              'scheduled_practice_seconds': scheduled,
              'formal_files_changed': post['formal_files_changed'], 'research_box_empty': post['research_box_empty'],
              'research_loader_removed': post['research_loader_removed'], 'full_ten_minutes_tested': False,
              'game_sessions_this_iteration': 3,
              'failed_release_session': {'work': str(failed_work), 'formal_files_changed': failed_post['formal_files_changed'],
                  'initialization_errors': [line for line in failed_text.splitlines() if any(token in line for token in ('INITIALIZATION_ATTEMPT_REJECTED=', 'ISSUE_START='))],
                  'result': 'initialization timeout; isolated process closed; no control entered'},
              'current_initialization_errors': [line for line in text.splitlines() if 'INITIALIZATION_ATTEMPT_REJECTED=' in line],
              'development_session': {'work': str(prior_work), 'game_process_restarted_during_hot_reloads': False,
                  'spawns': prior.count('PBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT='),
                  'same_process_retirements': prior.count('PBZ_REARM_RETIRE:PASS='),
                  'initialization_errors': [line for line in prior.splitlines() if any(token in line for token in ('INITIALIZATION_ATTEMPT_REJECTED=', 'ISSUE_START='))],
                  'skill_samples': skill_rows(prior), 'formal_files_changed': prior_post['formal_files_changed']},
              'unverified_candidates': ['heavy_02', 'special_03'],
              'candidate_conclusion': 'activation and natural finish observed; no damage seen during sampled windows; disabled by default',
              'remaining': ['target HUD and line-of-sight filtering', 'more skills and phase dependencies',
                            'death/map transition restoration', 'camera component unregistration and long-term stability', 'additional bosses'],
              'complete_all_boss_mod': False,
              'log_sha256': hashlib.sha256((work / 'UE4SS.log').read_bytes()).hexdigest()}
    evidence = ROOT / 'evidence/adaptation/ahua-target-v02-milestone.json'
    write(evidence, json.dumps(report, ensure_ascii=False, indent=2))
    write(work / 'postcheck.json', json.dumps(post, ensure_ascii=False, indent=2))
    history = ROOT / 'evidence/status-history' / datetime.now().strftime('%Y%m%d-%H%M%S-v02')
    history.mkdir(parents=True)
    for name in ('00-项目目标与现状.md', '04-当前结果与下一关.md', '34-简历与面试素材-开发中.md', '项目状态.json'):
        (history / name).write_bytes((ROOT / name).read_bytes())
    count = post['formal_file_count']
    write(ROOT / '40-双目标更新与实测.md', f'''# 阿花双目标离线训练 v0.2

整理时间：{now}。这是四技能训练版的目标切换更新，不是全Boss成品。

## 现在怎样用

仍双击 `D:\\mod文档\\开始阿花训练.cmd`，按照中文窗口1到4步操作。F6接管、WASD移动、鼠标转镜头、F1至F4出招，新增F7循环选择30米内的存活敌人，F10回主角。按键表见第39号。

默认创建两个临时敌人。出招中不能切目标；切换先请求，后续游戏帧读到真实技能目标一致后才开放出招。当前目标信息写入本轮UE4SS.log，还没有额外目标HUD。距离与障碍物仍会导致打空。

## 本轮真实结果

- 默认入口通过F6、F7切到不同对象再切回、F1自然结束与目标掉血、F10恢复。原主角位置变化0、新活动能力0。
- 本轮实际启动3次研究游戏会话。第一会话内使用热重载集中排错，2次恢复后清理；没有为每一招重开游戏。
- 第一会话第三次装配暴露临时目标被回收，重试又跳过静止等待；第二会话初始化超时，未进入操控。第三会话前三次装配仍在第二目标处失败，清理后保留了同一游戏进程。
- 后续恢复了实测过的第二目标位置，增加局部布局候选和生成后本地权限校验，再在同一游戏完成默认入口验收。另将StopAI延后至能力列表稳定、重试重新等待静止并加入初始化限时与夹具。具体游戏层回收原因尚未完全证实，不能把一次通过说成所有位置都稳定。
- 修正生成角色固定世界零度的问题，并在出招前用已核对接口朝向目标；只改临时Boss旋转，不传送原主角或更改进度。
- Heavy_02和Special_03有激活、活动计数归零记录，但样本窗口未观察到伤害，因此F5/F8不进入默认玩家键位，更多能力仍在研究。
- 三次研究会话分别收尾；每次核对的{count}个正式文件零变化，研究箱为空，研究加载器撤除。没有回写研究存档或自动回档。
- 本地{local['python_syntax_files']}份Python、{local['lua_syntax_files']}份Lua语法，以及目标筛选/异步切换/输入/保护等夹具通过。最终装配受总会话剩余时间限制为{scheduled}秒上限，本次只做短时验收，未跑满10分钟稳定性。

## 下一步与边界

优先研究更多技能的生效条件、目标HUD及视线过滤；之后处理死亡/切图、相机组件注销回收与其他Boss。目标选择成功不能直接等同于攻击命中，销毁请求不能直接等同于GC完成。

证据：`evidence/adaptation/ahua-target-v02-milestone.json`。第38号保留v0.1历史；当前说明以本文件、第37号和项目状态.json为准。
''')
    for name in ('00-项目目标与现状.md', '04-当前结果与下一关.md'):
        contents = (ROOT / name).read_text(encoding='utf-8')
        if not contents.startswith('> 当前更新：阿花双目标离线训练v0.2'):
            contents = '> 当前更新：阿花双目标离线训练v0.2，新增F7目标切换；本轮实测与失败修复见第40号。\n\n' + contents
        contents = contents.replace('当前支持：临时阿花、训练敌人、第三人称镜头、移动、四个技能键、F10退出恢复。',
                                    '当前支持：临时阿花、两个临时训练敌人、第三人称镜头、移动、四个技能键、F7目标切换、F10退出恢复。')
        contents = contents.replace('新的中文入口已经单轮实机启用并完成恢复和收尾，未重复旧功能的全部测试。',
                                    'v0.2默认入口已实测接管、F1掉血、F7往返与F10恢复；F2至F4复用此前四键证据。')
        contents = contents.replace('当前以第37、38号与项目状态.json为准。',
                                    '当前以第37、40号与项目状态.json为准；第38号保留v0.1历史。')
        contents = contents.replace('自由目标切换、死亡切图', '目标HUD和视线筛选、死亡切图')
        contents = contents.replace('自由选择目标、其他Boss', '目标HUD和视线筛选、其他Boss')
        write(ROOT / name, contents)
    resume = ROOT / '34-简历与面试素材-开发中.md'
    contents = resume.read_text(encoding='utf-8')
    contents = contents.replace('定位为个人离线研究项目、四键训练原型。', '定位为个人离线研究项目、四技能与目标切换训练原型。')
    if '新增有界敌人筛选与异步目标切换' not in contents:
        contents = contents.replace('## 面试口述', '- 新增有界敌人筛选与异步目标切换：排除原主角、自身、跨World、已死亡和销毁中的对象，等待真实技能查询回读后再开放出招；F7双目标循环已实机核对。\n\n## 面试口述')
    write(resume, contents)
    status = read(ROOT / '项目状态.json')
    status.update(updated_at=now, status='ahua-target-offline-practice-v0.2',
        status_summary='阿花四技能与F7双目标训练默认入口已实机验收，完整Boss体系仍在开发',
        target_cycle_runtime_verified=True, target_cycle_scope='same-world living hostile actors within 3000 Unreal units; no target HUD or LOS filtering',
        latest_result_note=str(ROOT / '40-双目标更新与实测.md'), latest_target_evidence=str(evidence),
        latest_formal_file_check_at=post['checked_at'], latest_formal_file_check_changed_count=0,
        no_remaining_pbz_processes_verified=True, research_loader_currently_deployed=False,
        research_loader_removed=True, formal_loader_deployed=False,
        blocked_reason='更多技能/阶段、目标HUD和视线过滤、死亡切图与组件回收尚待完成',
        not_done=['更多阿花技能和阶段条件', '目标HUD和视线过滤', '死亡切图恢复', '相机组件回收和长期稳定性', '其他Boss'],
        next_action='研究更多真实Boss技能的生效条件；不把候选动画作为可玩伤害能力')
    write(ROOT / '项目状态.json', json.dumps(status, ensure_ascii=False, indent=2))
    for name in ('00-从这里开始.md', 'README.md'):
        path = ROOT.parent / name
        contents = path.read_text(encoding='utf-8-sig').replace('阿花四键离线训练', '阿花四技能与F7目标训练v0.2')
        write(path, contents)
    # 用途：白名单归档源码与摘要证据，排除沙盒、账号缓存、原始存档和游戏资产。
    included = set()
    for directory, pattern in [('mod', '*'), ('tools', '*.py'), ('tests', '*'), ('adaptation/pbz-26367565', '*')]:
        included.update(p for p in (ROOT / directory).rglob(pattern) if p.is_file() and '__pycache__' not in p.parts
                        and p.suffix.lower() in ('.lua', '.py', '.cpp', '.ini', '.txt', '.cmd'))
    included.update(ROOT.glob('*.md')); included.update(ROOT.glob('*.csv'))
    included.update([ROOT / '开始阿花训练.cmd', ROOT / '打开研究工作台.cmd', ROOT / '项目状态.json', evidence])
    included.update(ROOT / 'evidence/adaptation' / name for name in ('ahua-protected-interactive-milestone.json',
                    'ahua-remote-control-milestone.json', 'ahua-delivery-local-checks.json'))
    archive = ROOT / '归档包' / ('阿花双目标离线训练-v0.2-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=5) as package:
        for path in sorted(included):
            package.write(path, 'PBZ-Boss操控研究/' + path.relative_to(ROOT).as_posix())
        binary = ROOT.parent / 'build/ue4ss-ascii/Game__Shipping__Win64/bin'
        for name in ('UE4SS.dll', 'dwmapi.dll'):
            package.write(binary / name, '自编译UE4SS/' + name)
        package.writestr('本机恢复说明.txt', '这是本机源码与工具归档，不是独立安装器。使用 D:\\mod文档\\开始阿花训练.cmd。依赖当前Python、Sandboxie、Steam和合法PBZ。禁止将研究存档写回正式存档。\n')
    with zipfile.ZipFile(archive) as package:
        if package.testzip() is not None:
            raise RuntimeError('Archive CRC failed')
        files = len(package.namelist())
    write(ROOT / '归档包/latest-package.json', json.dumps({'created_at': now, 'archive': str(archive),
        'bytes': archive.stat().st_size, 'files': files, 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'crc_verified': True, 'edition': 'Ahua four-skill and target-cycle bounded offline practice v0.2',
        'complete_all_boss_mod': False, 'raw_save_backup_included': False, 'steam_account_cache_included': False,
        'standalone_installer': False, 'runtime_acceptance_report': str(evidence)}, ensure_ascii=False, indent=2))
    print(json.dumps({'passed': True, 'checks': checks, 'archive': str(archive), 'files': files}, ensure_ascii=False))


if __name__ == '__main__':
    main()
