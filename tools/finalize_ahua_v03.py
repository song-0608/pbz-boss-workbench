"""用途：仅在默认F5实机与正式文件收尾通过后，整理五键训练版和无存档归档。"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(value.rstrip() + '\n', encoding='utf-8')


def main():
    evidence = ROOT / 'evidence/adaptation/ahua-skill-lab-milestone.json'
    report = read(evidence)
    latest = report['sessions'][-1]
    work = Path(latest['directory'])
    owner = read(ROOT / 'runtime/ahua-practice.json')
    local = read(ROOT / 'evidence/adaptation/ahua-delivery-local-checks.json')
    if owner['phase'] != 'closed' or owner.get('skill_lab') or owner.get('expanded'):
        raise RuntimeError('Finished default player session required')
    state = read(Path(owner['state_file']))
    if Path(state['work']) != work or not state.get('restored') or not local['passed']:
        raise RuntimeError('Matching current finished session and local checks required')
    text = (work / 'UE4SS.log').read_text(encoding='utf-8', errors='replace')
    checks = {'five_key_default_ready': 'INTERACTIVE_READY=F6 enter, WASD move, F1-F5 skills, F7 target, F10 restore;' in text,
              'skill06_natural_finish': any(r['id'] == 'skill_06' and r['peak'] > 0 and r['natural_finish'] for r in latest['samples']),
              'skill06_default_damage': any(r['id'] == 'skill_06' and r['damage_observed_in_window'] for r in latest['samples']),
              'skill06_active_cancel_verified': latest['skill06_active_cancel_verified'],
              'entered': latest['entered'], 'exited': latest['exited'], 'no_runtime_fault': not latest['issues'],
              'player_stationary': latest['original_player_stationary_at_exit'],
              'player_no_new_ability': latest['original_player_no_new_active_at_exit'],
              'damage_evidence': report['candidates']['skill_06']['damage_observed_in_window']}
    if not all(checks.values()):
        raise RuntimeError('Default v0.3 acceptance incomplete: ' + str(checks))
    for name, expected in local['source_sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Source changed after local checks: ' + name)
    deployment = report['current_assembly_deployment']
    for name, expected in deployment['module_source_sha256'].items():
        path = ROOT / 'mod/PBZBossControl/Scripts' / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Runtime module changed after acceptance: ' + name)
    if hashlib.sha256((ROOT / 'mod/PBZBossControl/Experiments/spawn_lifecycle.lua').read_bytes()).hexdigest() != deployment['assembly_source_sha256']:
        raise RuntimeError('Runtime assembly changed after acceptance')
    now = datetime.now().astimezone().isoformat()
    history = ROOT / 'evidence/status-history' / datetime.now().strftime('%Y%m%d-%H%M%S-v03')
    history.mkdir(parents=True)
    for name in ('00-项目目标与现状.md', '04-当前结果与下一关.md', '34-简历与面试素材-开发中.md',
                 '37-阿花训练版操作卡.md', '39-玩家实际按键表.csv', '项目状态.json'):
        (history / name).write_bytes((ROOT / name).read_bytes())
    report.update(version='v0.3', default_player_checks=checks, default_skill06_key='F5',
                  skill06_released_to_bounded_player_practice=True, unsafe_attack01_quarantined=True,
                  full_ten_minutes_tested=False)
    write(evidence, json.dumps(report, ensure_ascii=False, indent=2))
    card = ROOT / '37-阿花训练版操作卡.md'
    value = card.read_text(encoding='utf-8').replace('训练 v0.1', '训练 v0.3').replace('阿花四个技能键', '阿花五个技能键')
    value = value.replace('| F7 |', '| F5 | 阿花技能06（Skill_06） | 开发批次自然结束且9000→8350；默认F5另有实机记录 |\n| F7 |', 1)
    value = value.replace('阿花出招使用F1至F4', '阿花出招使用F1至F5')
    value = value.replace('F5、F8候选技能仅在开发参数`--expanded`下存在，尚未确认伤害，不属于玩家可用招式。',
                          'F8、F9候选技能仅在开发模式中存在，不属于默认玩家键位。普攻Attack_01因活动计数未归零且取消失败，已禁用；不要自行解除。')
    value += '\n## v0.3补充\n\n新增F5技能06。当前共五个技能键，其中F4是冲刺；不是五个伤害技能。技能试验台和本批失败原因见第42号，默认版验收见第43号。第38、40号是历史版本记录。\n'
    write(card, value)
    keys = ROOT / '39-玩家实际按键表.csv'
    value = keys.read_text(encoding='utf-8').replace('F7,切换当前敌人', 'F5,技能06,自然结束与配对掉血；默认F5独立验收\nF7,切换当前敌人', 1)
    write(keys, value)
    for name in ('00-项目目标与现状.md', '04-当前结果与下一关.md'):
        path = ROOT / name
        value = path.read_text(encoding='utf-8')
        value = re.sub(r'^> 当前更新：[^\n]+', '> 当前更新：阿花五键离线训练v0.3，新增F5技能06；本批实测见第42、43号。', value)
        value = value.replace('四个技能键', '五个技能键').replace('装配四项能力', '装配五项能力')
        value += '\n本批新增：F5技能06，已观测9000→8350并完成默认键位验收。另做三项候选研究；普攻01未结束且取消失败，已隔离禁用。完整Boss体系仍在开发。\n'
        write(path, value)
    resume = ROOT / '34-简历与面试素材-开发中.md'
    value = resume.read_text(encoding='utf-8').replace('四技能与目标切换训练原型', '五键与目标切换训练原型')
    value = value.replace('四个真实能力键', '五个真实能力键（含冲刺）').replace('三项攻击在临时训练敌人上观察到配对掉血', '四项攻击在各自采样批次的临时训练敌人上观察到配对掉血')
    value += '\n## 新增面试案例：能力并不等于独立招式\n\n新增精确白名单技能试验台，逐招记录真实活动计数、目标血量和位移。技能06在单独采样窗口观察到650点掉血，纳入F5。Attack_01虽然能激活，却会重开Brain调度，后续没有自然结束且取消失败；保留失败日志并隔离禁用。只修正调度冲突不能证明整招可玩，不能靠把verified改成true解决。\n'
    write(resume, value)
    status = read(ROOT / '项目状态.json')
    status.update(updated_at=now, status='ahua-five-key-offline-practice-v0.3',
                  status_summary='阿花F1至F5五键与F7目标训练；新增技能06，完整Boss体系仍在开发',
                  latest_result_note=str(ROOT / '43-五键训练版交付记录.md'), latest_skill_evidence=str(evidence),
                  default_player_skill_keys=5, default_damage_skill_keys=4, unsafe_attack01_disabled=True,
                  latest_formal_file_check_changed_count=0, latest_formal_file_check_at=read(work / 'postcheck.json')['checked_at'],
                  no_remaining_pbz_processes_verified=True, research_loader_currently_deployed=False,
                  research_loader_removed=True, next_action='研究普攻01的原始任务/事件结束依赖；保持禁用，不绕过取消限制')
    write(ROOT / '项目状态.json', json.dumps(status, ensure_ascii=False, indent=2))
    count = latest['formal_file_count']
    write(ROOT / '43-五键训练版交付记录.md', f'''# 阿花五键离线训练 v0.3

整理时间：{now}。入口仍为 D:\\mod文档\\开始阿花训练.cmd。

新增 **F5：阿花技能06**。F1技能01、F2重击01、F3技能02、F4冲刺、F7切目标、F10恢复。鼠标左键仍未绑定Boss普攻。

## 真实结果

- 开发同一会话集中试放Skill_04、Skill_06、Special_05_A和Attack_01。Skill_06目标9000→8350，两名临时敌人的采样都观察到掉血；不能据此保证任意距离命中。
- Skill_04和Special_05_A激活并自然结束，有位移，但采样未观察到掉血，仍仅开发可用。
- Attack_01第一次触发Brain tick冲突；有限重申暂停后第二次没有即时失控，但仍未自然结束且取消失败。两轮都由研究监督器收尾，不能写成普攻完成修复；该候选已禁用。
- 默认五键版另用一轮完成F5自然结束且9000→8350；再次出招时按F10，真实活动计数1→0，取消与恢复通过。原主角位置变化0、新活动能力0。
- 本批共{len(report['sessions'])}个研究游戏会话；没有为每招重开游戏。旧功能复用已有证据，只做与新技能直接相关的检查。
- 本批各轮正式文件均无变化；最新轮核对{count}个正式文件。研究箱已关闭、加载器撤除，不回写、不回档。

## 当前边界

这是五键短时训练版，含四项攻击和一项冲刺。普攻连段、阶段切换、目标HUD/视线过滤、死亡切图恢复、长期相机回收、其他Boss尚未完成。没有实测满10分钟。

本批源码、失败和通过证据：evidence/adaptation/ahua-skill-lab-milestone.json。每次装配另存源码哈希，避免用新源码冒充旧批次实测。
''')
    included = set()
    for directory, pattern in [('mod', '*'), ('tools', '*.py'), ('tests', '*'), ('adaptation/pbz-26367565', '*')]:
        included.update(p for p in (ROOT / directory).rglob(pattern) if p.is_file() and '__pycache__' not in p.parts
                        and p.suffix.lower() in ('.lua', '.py', '.cpp', '.ini', '.txt', '.cmd'))
    included.update(ROOT.glob('*.md')); included.update(ROOT.glob('*.csv'))
    included.update((ROOT / name for name in ('开始阿花训练.cmd', '打开研究工作台.cmd', '项目状态.json')))
    included.add(evidence)
    included.update(ROOT / 'evidence/adaptation' / name for name in (
        'ahua-target-v02-milestone.json', 'ahua-protected-interactive-milestone.json', 'ahua-delivery-local-checks.json'))
    archive = ROOT / '归档包' / ('阿花五键离线训练-v0.3-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=5) as package:
        for path in sorted(included):
            package.write(path, 'PBZ-Boss操控研究/' + path.relative_to(ROOT).as_posix())
        binary = ROOT.parent / 'build/ue4ss-ascii/Game__Shipping__Win64/bin'
        for name in ('UE4SS.dll', 'dwmapi.dll'):
            package.write(binary / name, '自编译UE4SS/' + name)
        package.writestr('本机恢复说明.txt', '本机源码与工具归档，不是独立安装器。入口 D:\\mod文档\\开始阿花训练.cmd。依赖本机Python、Sandboxie、Steam和合法PBZ。禁止回写研究存档。\n')
    with zipfile.ZipFile(archive) as package:
        if package.testzip() is not None:
            raise RuntimeError('Archive CRC failed')
        files = len(package.namelist())
    write(ROOT / '归档包/latest-package.json', json.dumps({'created_at': now, 'archive': str(archive),
        'bytes': archive.stat().st_size, 'files': files, 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'crc_verified': True, 'edition': 'Ahua five-key bounded offline practice v0.3',
        'complete_all_boss_mod': False, 'raw_save_backup_included': False, 'steam_account_cache_included': False,
        'standalone_installer': False, 'runtime_acceptance_report': str(evidence)}, ensure_ascii=False, indent=2))
    print(json.dumps({'passed': True, 'checks': checks, 'archive': str(archive), 'files': files}, ensure_ascii=False))


if __name__ == '__main__':
    main()
