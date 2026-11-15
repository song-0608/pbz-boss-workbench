"""仅用本次动作的实时HUD决定是否需要F7；引擎仍独立核对真正出招条件。"""
import json
import re


def deployed_boss_name(owner, deployment, text, registered):
    """只使用本轮已完成装配的角色，不读取玩家为下一轮保存的设置。"""
    if not owner.get('player_entry') or not deployment.get('player_entry'):
        raise RuntimeError('Ordinary player deployment required')
    selected=deployment.get('boss_id')
    for event,identifier in re.findall(
            r'PBZ_CONTROL_LIFECYCLE:(PLAYER_ENTRY_READY|WORKBENCH_BOSS_SELECTED)=([^\r\n|]+)', text):
        if identifier not in registered:
            raise RuntimeError('Unknown Boss in current deployment')
        if event=='WORKBENCH_BOSS_SELECTED':
            selected=None
        else:
            selected=identifier
    if selected not in registered:
        raise RuntimeError('Boss switching has not completed')
    return registered[selected]


def latest_target_status(text, session, now, boss_name='新娘阿花', allow_unavailable=False):
    records = [line.split('PBZ_PLAYER_UI:STATUS=', 1)[1]
               for line in text.splitlines() if 'PBZ_PLAYER_UI:STATUS=' in line]
    if not records:
        return None
    try:
        row = json.loads(records[-1])
        if (row['session'] != session or type(row['at']) is not int
                or not now - 3 <= row['at'] <= now + 1
                or type(row['expires_at']) is not int or row['expires_at'] <= now
                or not isinstance(row['player'], str) or not row['player']
                or not isinstance(row['text'], str)):
            return None
        lines = row['text'].splitlines()
        if (not isinstance(boss_name, str) or not boss_name or '\n' in boss_name
                or not lines or lines[0] != boss_name + ' | ACTIVE'):
            return None
        targets = [line for line in lines if line.startswith('目标：')]
        if len(targets) != 1:
            return None
        if targets[0]=='目标：无有效锁定' and allow_unavailable:
            return {'visibility':'unavailable','target':None,'hud':row}
        target = re.fullmatch(r'目标：(.+) \| 生命 (-?\d+(?:\.\d+)?)', targets[0])
        if not target:
            return None
        name = target[1]
        if '（视线待核对）' in name:
            return None
        if float(target[2]) <= 0:
            return {'visibility':'unavailable','target':name,'hud':row} if allow_unavailable else None
        if '（已死亡）' in name:
            return None
        return {'visibility': 'blocked' if '（视线遮挡）' in name else 'visible',
                'target': name, 'hud': row}
    except (ValueError, KeyError, TypeError, IndexError):
        return None


def target_cycle_verified(text):
    if '[PBZBossControl] target verified:'in text:return True
    # Runtime 去重相同目标的提示文本，但原生精确目标查询仍单独记录。
    requests=list(re.finditer(r'\[PBZBossControl\] target_request success=true state=ACTIVE reason=requested; awaiting readback: ([^\r\n]+)',text))
    if not requests:return False
    requested=requests[-1][1]
    return re.search(r'PBZ_COMBAT_TARGET:QUERY='+re.escape(requested)+r'\|ignore_soft='+re.escape(requested)+r'(?:\r?\n|$)',
                     text[requests[-1].end():])is not None


def ensure_visible_target(path, offset, session, wait_for, click, now, force_cycle=False,
                          boss_name='新娘阿花'):
    """最多一次真实切换；必须在该输入之后重新取得当前会话可见目标回读。"""
    def status(text):
        return latest_target_status(text, session, now(), boss_name, allow_unavailable=True)

    tail = wait_for(path, offset, lambda text: status(text) is not None, 5, True)
    before = status(tail)
    if before is None:
        raise RuntimeError('Fresh ACTIVE target status not verified')
    cycle = force_cycle or before['visibility'] in ('blocked','unavailable')
    if not cycle:
        return {'cycle_sent': False, 'before': before, 'after': before}
    cycle_offset = len(path.read_text(encoding='utf-8', errors='replace'))
    click(0, 0, 2560, 1600, 'control_target')
    tail = wait_for(path, cycle_offset,
                    lambda text: target_cycle_verified(text)
                    and status(text) is not None and status(text)['visibility'] == 'visible', 6, True)
    after = status(tail)
    if (not target_cycle_verified(tail)
            or after is None or after['visibility'] != 'visible'):
        raise RuntimeError('Target cycle and fresh visible target not verified')
    return {'cycle_sent': True, 'before': before, 'after': after, 'cycle_log_offset': cycle_offset}
