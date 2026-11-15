"""用途：封存普攻拆解与技能08的真实成功、失败证据；不提升默认键位、不启动游戏。"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    owner = read(ROOT / 'runtime/ahua-practice.json')
    state = read(Path(owner['state_file']))
    work = Path(state['work'])
    post = read(ROOT / 'evidence/latest-native-diagnostic-postcheck.json')
    checks = read(ROOT / 'evidence/adaptation/ahua-delivery-local-checks.json')
    if (owner['phase'] != 'closed' or not state.get('restored')
            or post['validation_state'] != owner['state_file'] or post['formal_files_changed']
            or post['host_config_files_changed'] or not post['host_registry_unchanged']
            or not post['research_box_empty'] or not post['research_loader_removed'] or not checks['passed']):
        raise RuntimeError('Clean matching closed offline session and passing local checks required')
    for name, expected in checks['source_sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Source changed after checks: ' + name)
    graph = read(work / 'ahua-combo-tree-contract.json')
    lifecycle = read(work / 'ahua-attack-lifecycle-contract.json')
    attack = next(o for o in lifecycle['objects'] if 'GA_AHua_Attack_01.' in o['class'])
    parents = [o['path'] for o in attack['inheritance']]
    if '/Script/SGameAI.RunSubtreeAbility' not in parents or len(graph['leaf_abilities']) != 6:
        raise RuntimeError('Expected exact reflected wrapper and six leaf references')
    text = (work / 'UE4SS.log').read_text(encoding='utf-8', errors='replace')
    actions = read(work / 'skill-lab-actions.json')
    natural = re.findall(r'KEY_SKILL_END=skill_08\|peak=(\d+)\|active=(\d+)\|natural=(true|false)\|health_before=([\d.]+)\|health_after=([\d.]+)', text)
    successful = [dict(peak=int(p), active_after=int(a), natural_finish=n == 'true',
                       health_before=float(b), health_after=float(e)) for p, a, n, b, e in natural
                  if int(p) > 0 and int(a) == 0 and n == 'true' and float(b) > float(e)]
    interrupted = [r for r in actions if r.get('candidate_before_input') == 'skill_08'
                   and r.get('action') == 'interrupt' and r.get('active_candidate_cancelled')]
    if not successful or not interrupted:
        raise RuntimeError('Real damage, natural finish and active cancellation required')
    deployments = [read(p) for p in sorted(work.glob('control-lifecycle-deployment-*.json'))]
    report = {'at': datetime.now().astimezone().isoformat(), 'session': str(work),
        'prior_failed_session': str(ROOT / 'evidence/official-validation/20261113-150139'),
        'attack_wrapper_inheritance': parents, 'combo_graph': 'ahua-combo-tree-contract.json',
        'node_count': len(graph['nodes']), 'leaf_abilities': graph['leaf_abilities'],
        'static_relationship_only': True, 'exact_stuck_cause_proven': False,
        'skill08_samples': successful, 'skill08_active_cancellation_verified': True,
        'default_f8_verified': False, 'default_f8_released': False,
        'default_rearm_failed_before_takeover': 'PREREQUISITE_NOT_READY=temporary boss initialization did not become ready in three cleaned attempts' in text,
        'initialization_stability_fixed': False, 'game_restart_for_each_skill': False,
        'unsafe_attack01_disabled': True, 'default_player_skill_keys': 5,
        'original_player_restoration_verified': all(token in '\n'.join(interrupted[-1]['lines']) for token in (
            'ORIGINAL_PLAYER_POSITION_DELTA=0.0', 'ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0')),
        'deployment_history': deployments, 'local_check_count': len(checks['checks']),
        'formal_file_count': post['formal_file_count'], 'formal_file_change_count': 0,
        'research_box_empty': True, 'research_loader_removed': True,
        'complete_all_boss_mod': False}
    save(work / 'postcheck.json', post)
    target = ROOT / 'evidence/adaptation/ahua-attack-research-milestone.json'
    save(target, report)
    note = '''# 阿花普攻入口拆解与技能08实测（开发记录）

本轮结果不是完整Boss Mod，也不是已经验收的六键玩家版。默认玩家入口仍为五键v0.3；F8尚未发布，左键普攻仍未绑定。

## 这次实际弄清了什么

1. 实机反射确认：Attack_01 → GA_AutoComboGroup → RunSubtreeAbility → GameplayAbility。它是连招子树调度入口，不是可直接视作一刀普攻的独立攻击。
2. 同一游戏线程只读遍历Attack_01类默认对象的ComboTreeWithWeight，确认唯一映射：BT_AHua_TeleportAttack_01，权重100。提取16个节点、6个AbilityToActivate能力引用：Skill_03、Skill_08、Skill_05_Hard、CA_01_GEx_Teleport_RedEye、Teleport_Left、Teleport_Right。
3. 以上是静态声明与引用关系，不证明具体分支执行顺序。暂停Brain与子树入口不结束的精确因果尚未证实；Attack_01仍隔离禁用，不强写活动计数、不绕过取消限制。
4. 本轮活体唯一授予列表中，新候选只有Skill_08可装配；没有授予的候选自动拒绝，未擅自授予技能。

## 真实出招结果

- 开发试验台F9选中Skill_08，F8独立施放：ActiveCount峰值1、自然归零；独立采样目标9000→8900，另一训练目标9000→9000。不保证任意距离命中，也不将它命名为普通左键连段。
- 同一阿花再次施放后按F10：实际活动计数1→0，取消日志记录invoking_cancel与activity_cleared；原主角位置变化0、新活动能力0，退出恢复成功。
- 默认F8的装配代码已经编写，但player_key_verified=false。后续同进程重新装配时，临时角色HasAuthority=false、无Controller/授予技能，有限等待与三次清理重试未恢复就绪；因此没有进行默认F8按键实测，不发布六键版。
- 初始化现在允许等待真实权限就绪，永久false时仍拒绝进入控制；这只是门槛改进，不是初始化故障已经修复。

## 初学者只读这几处

1. tools/load_ahua_lifecycle_classes.py：看“加载类→读取默认对象映射→遍历节点”及中文用途注释，不调用ChooseTree、不运行行为树。
2. tools/inspect_ahua_attack_lifecycle.py：比较继承链、函数声明与调用引用候选；候选不等于完整反编译。
3. mod/PBZBossControl/Scripts/skill_lab.lua：精确资产路径与本次唯一授予名单交叉匹配，再加入开发试放列表。
4. mod/PBZBossControl/Scripts/ue_calls.lua：取消只作用于真实活动、可取消的实例，必须实际读到活动计数归零。
5. mod/PBZBossControl/Scripts/profiles/ahua.lua：Skill_08已有伤害/结束/取消证据，但默认玩家键位验收为false；两个结论不能混用。

## 本轮收尾与下一处根因

研究游戏已结束。核对56个正式文件，本轮变化0；研究箱为空、研究加载器已撤除。没有回写研究存档，没有用历史备份覆盖正式进度。旧基线与用户之后正常游戏的差异不属于本轮修改。

下一处必须解决的是临时Boss的初始化/回收机制，使成功生成不依赖偶然时序；之后再验默认F8、拆分真正普攻连段。保留v0.3稳定归档，不用开发快照冒充稳定版。

证据：evidence/adaptation/ahua-attack-research-milestone.json；原始日志与成功/失败装配记录均在evidence/official-validation/20261113-151020。首次初始化失败另存20261113-150139。
'''
    (ROOT / '44-普攻入口拆解与技能08实测-开发中.md').write_text(note, encoding='utf-8')
    status = read(ROOT / '项目状态.json')
    status.update(updated_at=report['at'], latest_attack_research_evidence=str(target),
        latest_result_note=str(ROOT / '44-普攻入口拆解与技能08实测-开发中.md'),
        next_action='修复临时Boss初始化与回收；再验默认F8，继续拆分普攻连段',
        skill08_developer_gameplay_verified=True, skill08_default_key_verified=False,
        default_player_skill_keys=5, default_damage_skill_keys=4,
        unsafe_attack01_disabled=True, research_loader_currently_deployed=False,
        no_remaining_pbz_processes_verified=True, research_loader_removed=True,
        latest_formal_file_check_at=post['checked_at'], latest_formal_file_check_changed_count=0)
    save(ROOT / '项目状态.json', status)
    included = set()
    for folder, suffixes in [('mod', {'.lua'}), ('tools', {'.py'}), ('tests', {'.lua', '.py'})]:
        included.update(p for p in (ROOT / folder).rglob('*') if p.is_file() and p.suffix in suffixes and '__pycache__' not in p.parts)
    included.update(ROOT.glob('*.md')); included.update(ROOT.glob('*.csv'))
    included.add(ROOT / '项目状态.json'); included.add(target)
    included.add(ROOT / 'evidence/adaptation/ahua-delivery-local-checks.json')
    for name in ('ahua-combo-tree-contract.json', 'ahua-attack-lifecycle-contract.json', 'attack-readonly-probe.lua',
                 'attack-readonly-evidence.log', 'skill-lab-actions.json', 'expanded-actions.json', 'UE4SS.log',
                 'postcheck.json', 'before-same-process-retirement.lua', 'same-process-retirement.json'):
        included.add(work / name)
    included.update(work.glob('control-lifecycle-deployment*.json'))
    included.update(p for p in (work / 'module-history').rglob('*.lua'))
    archive = ROOT / '归档包' / ('阿花普攻拆解与技能08-开发快照-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=5) as package:
        for path in sorted(included):
            package.write(path, 'PBZ-Boss操控研究/' + path.relative_to(ROOT).as_posix())
        package.writestr('开发快照说明.txt', '默认玩家入口仍为五键v0.3。此包用于学习与继续开发，不是六键稳定发布版；不含原始存档、Steam账号缓存或游戏资源。正式游戏目录禁止部署。\n')
    with zipfile.ZipFile(archive) as package:
        if package.testzip() is not None:
            raise RuntimeError('Archive CRC failed')
        count = len(package.namelist())
    save(ROOT / '归档包/latest-development-package.json', {'at': report['at'], 'archive': str(archive),
        'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'files': count, 'crc_verified': True,
        'stable_package_pointer_changed': False, 'raw_saves_included': False, 'default_f8_released': False})
    print(json.dumps({'report': str(target), 'archive': str(archive), 'files': count, 'formal_changes': 0,
                      'skill08_developer_verified': True, 'default_f8_released': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
