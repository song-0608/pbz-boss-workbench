"""只编排同一固定源码尚缺的证据；不会启动游戏或改变战斗前置条件。"""

# 固定分组避免A完成后重算剩余列表，导致B遗漏；长连招和明确位移动作靠后。
# 顺序只减少测试干扰，不保证后续目标可见，也不允许跳过引擎的视线检查。
ORDER = (
    'skill_01', 'skill_02', 'skill_04', 'skill_06', 'skill_06_hard',
    'skill_07', 'skill_07_hard', 'skill_08', 'skill_09', 'special_02_new',
    'special_03', 'special_03_flower', 'special_03_flower_cd', 'special_07',
    'heavy_01', 'heavy_02', 'dash', 'teleport_left', 'teleport_right',
    'homing_flower', 'homing_flower_hard', 'attack_01',
    'special_05_a', 'special_11', 'special_move_01', 'special_move_back',
    'special_move_left', 'special_move_right',
)


def make_plan(readiness, batch):
    if batch not in ('a', 'b'):
        raise RuntimeError('A fixed catalog batch a or b is required')
    bindings = readiness['expected_bindings']
    expected = {r['skill'] for r in bindings}
    slots = {r['slot']: r for r in bindings}
    if len(bindings) != 29 or len(slots) != 29 or expected != set(ORDER):
        raise RuntimeError('Exact 28-ability / 29-binding catalog required')
    missing_natural = set(readiness['missing_natural'])
    missing_cancel = set(readiness['missing_cancel'])
    missing_bindings = readiness['missing_bindings']
    if not (missing_natural | missing_cancel) <= expected or any(
            r != slots.get(r['slot']) for r in missing_bindings):
        raise RuntimeError('Missing evidence must name exact current registered bindings')
    selected = set(ORDER[0 if batch == 'a' else 1::2])
    natural, cancel = [], []

    def request(row):
        return row['slot'] if row['slot'] == 'primary_attack' else row['skill']

    def action(row, reason):
        return {'request': request(row), 'binding': dict(row), 'reason': reason}

    for skill in ORDER:
        if skill not in selected:
            continue
        rows = [r for r in bindings if r['skill'] == skill]
        canonical = next(r for r in rows if r['slot'] != 'primary_attack')
        planned = set()
        if skill in missing_natural:
            natural.append(action(canonical, 'missing_natural'))
            planned.add(canonical['slot'])
        if skill in missing_cancel:
            # 技能01取消顺带核对尚未验证的左键，F1自然结束仍单独保留。
            alternatives = [r for r in rows if r in missing_bindings and r['slot'] not in planned]
            chosen = alternatives[0] if alternatives else canonical
            cancel.append(action(chosen, 'missing_cancel'))
            planned.add(chosen['slot'])
        for row in rows:
            if row in missing_bindings and row['slot'] not in planned:
                natural.append(action(row, 'missing_binding'))
                planned.add(row['slot'])

    return {
        'batch': batch, 'release_id': readiness['release_id'],
        'module_source_sha256': readiness['module_source_sha256'],
        'candidate_manifest_sha256': readiness['candidate_manifest_sha256'],
        'expected_bindings': bindings,
        'closed_evidence_sessions': readiness['exact_source_closed_sessions'],
        'phases': [
            {'name': 'ordinary_cancel', 'interrupt': True, 'actions': cancel},
            {'name': 'ordinary_natural', 'interrupt': False, 'actions': natural},
        ],
        'action_count': len(cancel) + len(natural),
        'game_launch_requested': False, 'game_restart_requested': False,
        'target_gate_unchanged': True, 'complete_mod': False,
    }
