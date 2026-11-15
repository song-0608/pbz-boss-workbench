"""用途：纯文本解析V2/V3观察证据；可离线复现，不连接游戏或修改存档。"""
import re

MARKER = re.compile(r'^START_V(2|3)$')
OWNER = re.compile(r'^(PLAYER|NPC_\d+)(?:_|$)')


def parse_observation(lines):
    payloads = [line.split('PBZ_AI_OBSERVE:', 1)[1].strip()
                for line in lines if 'PBZ_AI_OBSERVE:' in line]
    starts = [index for index, line in enumerate(payloads) if MARKER.fullmatch(line)]
    if not starts:
        raise ValueError('No supported observer marker; no runtime pass inferred')
    current = payloads[starts[-1]:]
    actors, rows, issues, counts, instances = {}, [], [], {}, {}
    for value in current:
        key, _, val = value.partition('=')
        if key == 'PLAYER' or re.fullmatch(r'NPC_\d+', key):
            actors[key] = val
            instances.setdefault(val, {'last_counts': {}, 'queries': {}, 'issues': [], 'stages': {}})
        owner_key = key.removeprefix('ISSUE_')
        match = OWNER.match(owner_key)
        label = match[1] if match else None
        instance = instances.get(actors.get(label))
        suffix = owner_key[len(label) + 1:] if label else ''
        if key.startswith('ISSUE_'):
            issues.append(value)
            if instance is not None: instance['issues'].append(value)
        if key.endswith('_ABILITY_COLLECTED'):
            counts[key] = int(val)
            if instance is not None: instance['last_counts']['abilities'] = int(val)
        if instance is not None and suffix in ('BRAIN_RUNNING', 'TREE', 'CONFIG_NAME', 'CONFIG_NAME_KEY', 'LOCALIZATION_PENDING'):
            instance['queries'][suffix] = val
        if instance is not None:
            for prefix, status in (('READY_', 'ready'), ('PENDING_', 'pending'), ('RETRY_EXHAUSTED_', 'unresolved')):
                if suffix.startswith(prefix): instance['stages'][suffix[len(prefix):]] = status
            if suffix == 'OBSERVED': instance['observation_recorded'] = True
        skill = re.fullmatch(r'(PLAYER|NPC_\d+)_ABILITY_(\d+)', key)
        if skill:
            rows.append({'观察对象': skill[1], '实例': actors.get(skill[1], ''), '采集序号': int(skill[2]),
                         '授予技能对象': val, '已激活实测': False, '玩家按键': '未分配'})
    return {'version': int(MARKER.fullmatch(current[0])[1]), 'starts': len(starts),
            'current': current, 'rows': rows, 'issues': issues, 'counts': counts, 'per_instance': instances}
