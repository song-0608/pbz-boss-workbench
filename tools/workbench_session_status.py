"""Read launcher state and serialize UI commands without changing game/session grants."""
from dataclasses import dataclass
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import time


@dataclass(frozen=True)
class SessionView:
    phase: str
    message: str
    allowed: tuple
    bindings: str = ''


def _read(path):
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('State must be a JSON object')
    return value


def _remaining(deadline, now):
    seconds = max(0, int(deadline - now))
    return f'{seconds // 60:02d}:{seconds % 60:02d}'


def _bindings(owner):
    keys = owner.get('actual_controls', {})
    rows = owner.get('actual_bindings', [])
    if not isinstance(keys, dict) or not all(isinstance(keys.get(k), str) for k in ('enter', 'exit', 'cycle_target')):
        return ''
    if not isinstance(rows, list) or any(not isinstance(r, dict) or
            not all(isinstance(r.get(k), str) for k in ('key', 'skill')) for r in rows):
        return ''
    return (f"{keys['enter']} 接管｜{keys['exit']} 恢复主角｜{keys['cycle_target']} 切敌｜"
        f"{keys.get('lock_target', '中键')} 锁敌｜Insert 选角色\n"
        + '；'.join(r['key'] + ' ' + r['skill'] for r in rows))


def _state_path(pointer, runtime, prefix):
    path = Path(pointer['state_file']).resolve()
    if (path.name != 'state.json' or path.parent.parent != runtime or
            not re.fullmatch(prefix + r'-\d{8}-\d{6}', path.parent.name)):
        raise ValueError('Unexpected state path')
    return path


def _cleaned(root, path, state):
    """Only a completed, matching postcheck can retire a foreign session."""
    if state.get('restored') is not True or state.get('remaining_box_pids') != []:
        return False
    report = _read(root / 'evidence/official-validation' /
                   path.parent.name.removeprefix('official-validation-') / 'postcheck.json')
    if Path(report['validation_state']).resolve() != path:
        return False
    restored = datetime.fromisoformat(state['restored_at'])
    checked = datetime.fromisoformat(report['checked_at'])
    if restored.utcoffset() is None or checked.utcoffset() is None or checked < restored:
        return False
    return (all(report.get(key) is True for key in (
        'validation_restored', 'research_box_empty', 'research_loader_removed',
        'all_temporary_network_removed', 'host_registry_unchanged')) and
        all(report.get(key) == [] for key in (
            'remaining_games', 'formal_files_changed', 'host_config_files_changed')))


def _login_view(runtime, now):
    pointer = runtime / 'latest-login-preparation.json'
    if not pointer.exists():
        return None
    state = _read(_state_path(_read(pointer), runtime, 'auth-preparation'))
    if state.get('restored') is True:
        if (state.get('remaining_box_pids') == [] and state.get('formal_files_changed') == []
                and state.get('host_steam_registry_unchanged') is True):
            return None
        raise ValueError('Login cleanup is incomplete')
    deadline = state['deadline_unix']
    if isinstance(deadline, bool) or not isinstance(deadline, (int, float)) or not math.isfinite(deadline):
        raise ValueError('Invalid login deadline')
    if now >= deadline:
        return SessionView('login_cleanup', '登录准备已到时，等待恢复离线规则和清理核对；暂不开始研究会话。', ('status',))
    return SessionView('login_preparation', '独立Steam正在限时准备本人登录，剩余 '
        + _remaining(deadline, now) + '。完成并结束登录准备后，再开始第1步。', ('status',))


def snapshot(root, now=None):
    """Fail closed on partial writes, foreign owners and unresolved cleanup."""
    root = Path(root).resolve(); runtime = root / 'runtime'
    now = time.time() if now is None else now
    pointer = runtime / 'latest-official-validation.json'
    owner_path = runtime / 'ahua-practice.json'
    idle = SessionView('idle', '尚未开始。请先完成第1步准备。', ('prepare', 'status'))
    try:
        login = _login_view(runtime, now)
        if login is not None:
            return login
        if not pointer.exists():
            if owner_path.exists():
                return SessionView('unavailable', '会话指针缺失，请查看状态；暂不开始新会话。', ('status',))
            return idle
        state_path = _state_path(_read(pointer), runtime, 'official-validation')
        state = _read(state_path)
        owner = _read(owner_path) if owner_path.exists() else {}
        matches = bool(owner.get('state_file')) and Path(owner['state_file']).resolve() == state_path
        if not matches:
            if _cleaned(root, state_path, state):
                if owner:
                    old_path = _state_path(owner, runtime, 'official-validation')
                    if not _cleaned(root, old_path, _read(old_path)):
                        return SessionView('foreign', '其他窗口的会话尚未完成清理核对，请回原窗口操作。', ('status',))
                return idle
            return SessionView('foreign', '当前会话属于其他窗口或工具。保留它，请回原窗口操作。', ('status',))
        if state.get('restored') is True:
            if owner.get('postcheck_review_required'):
                return SessionView('postcheck', '研究箱已关闭，正式文件核对尚未完成。请点第4步完成核对。', ('stop', 'status'))
            return idle
        deadline = state['deadline_unix']
        if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
            raise ValueError('Invalid deadline')
        if now >= deadline:
            return SessionView('expired', '本轮总时限已到。请点第4步清理并核对，再开始下一轮。', ('stop', 'status'))
        phase = owner.get('phase')
        if phase == 'preparing':
            return SessionView(phase, '正在准备研究副本，请等待原步骤完成。', ('status',))
        if phase == 'prepared':
            return SessionView(phase, '第1步已完成。确认研究Steam云同步关闭后，点第2步一次。', ('launch', 'stop', 'status'))
        if phase == 'game_launched':
            return SessionView(phase, '游戏已启动。进入保存的场景并站稳后，点第3步一次。', ('arm', 'stop', 'status'))
        if phase == 'armed':
            grant = state.get('control_probe_expires_at')
            if isinstance(grant, bool) or not isinstance(grant, (int, float)):
                return SessionView('unavailable', '装配记录缺少操控时限。请点第4步结束并核对。', ('stop', 'status'))
            until = min(deadline, grant)
            if now >= until:
                return SessionView('control_expired', '本轮操控已到时。请点第4步结束，不重复启动或装配。', ('stop', 'status'))
            keys = owner.get('actual_controls', {})
            enter = keys.get('enter', 'F6') if isinstance(keys, dict) else 'F6'
            return SessionView(phase, f'Boss已启用：回游戏按 {enter} 接管，Insert 选择角色。操控剩余 '
                + _remaining(until, now) + '。无需再点第2、3步。', ('stop', 'status'), _bindings(owner))
        return SessionView('cleanup', '当前阶段需要结束核对。请点第4步，不覆盖或重新装配。', ('stop', 'status'))
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        return SessionView('unavailable', '会话状态正在更新或无法完整读取；已暂停操作，请稍候或查看状态。', ('status',))


class ActionLease:
    """A process-held file lock: a second launcher cannot dispatch a second step."""
    def __init__(self, root):
        self.path = Path(root) / 'runtime/workbench-ui-action.lock'
        self.handle = None

    def acquire(self):
        if self.handle is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open('a+b')
        if self.path.stat().st_size == 0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self.handle = handle
        return True

    def release(self):
        if self.handle is None:
            return
        handle, self.handle = self.handle, None
        try:
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def action_available(root):
    lease = ActionLease(root)
    if not lease.path.exists():
        return True
    try:
        return lease.acquire()
    except OSError:
        return False
    finally:
        lease.release()
