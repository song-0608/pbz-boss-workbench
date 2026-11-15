"""单次真实F12载图验收：接管、同步恢复、新World自动装配、真实技能和F10。"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import time
import ahua_practice as practice
import research_game_menu as menu
from control_action_evidence import restoration_result


def main():
    owner, state = practice.owned_session()
    assert owner['phase'] == 'armed' and owner.get('scene_transition_trial')
    assert not owner.get('skill_lab') and not owner.get('expanded')
    assert min(state['deadline_unix'], state['control_probe_expires_at']) - time.time() > 240
    path = practice.log_path(state)
    work = Path(state['work'])
    deployment = max(work.glob('control-lifecycle-deployment-*.json'), key=lambda p: p.stat().st_mtime_ns)
    prefix = path.read_text(encoding='utf-8', errors='replace')
    assert prefix[owner['log_offset']:].count('PLAYER_ENTRY_READY=') == 1
    offset = len(prefix)
    row = {'at': datetime.now().astimezone().isoformat(), 'state_file': state['state_file'],
           'deployment_file': deployment.name, 'assembly_log_offset': owner['log_offset'],
           'log_offset': offset, 'passed': False}

    def tail():
        return path.read_text(encoding='utf-8', errors='replace')[offset:]

    def wait(predicate, seconds):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            current = tail()
            assert not any(s in current for s in ('state=FAULTED', 'PBZ_CONTROL_LIFECYCLE:ISSUE_',
                'PBZ_CONTROL_RESTORE:FAILED=', 'PREREQUISITE_NOT_READY=', 'TRANSITION_TRIAL_REJECTED=')), current[-2500:]
            if predicate(current):
                return current
            time.sleep(.2)
        raise RuntimeError('Timed out waiting for current transition stage: ' + tail()[-2500:])

    try:
        menu.click(0, 0, 2560, 1600, 'control_enter')
        wait(lambda t: '[PBZBossControl] enter success=true state=ACTIVE' in t, 8)
        menu.click(0, 0, 2560, 1600, 'control_scene_transition')
        wait(lambda t: 'MAP_TRAVEL_RESTORED_BEFORE_LOAD=true' in t, 20)
        row['preload_restoration'] = restoration_result(tail(), 'auto_exit', 'map travel')
        assert row['preload_restoration']['passed'], 'Preload restoration incomplete'
        wait(lambda t: 'PLAYER_ENTRY_READY=' in t, 140)
        menu.click(0, 0, 2560, 1600, 'control_enter')
        wait(lambda t: t.count('[PBZBossControl] enter success=true state=ACTIVE') == 2, 8)
        menu.click(0, 0, 2560, 1600, 'control_skill')
        wait(lambda t: bool(re.search(r'KEY_SKILL_END=skill_01\|peak=[1-9]\d*\|active=0\|natural=true\|', t)), 50)
        menu.click(0, 0, 2560, 1600, 'control_exit')
        row['postload_restoration'] = restoration_result(wait(lambda t: restoration_result(t, 'exit')['passed'], 8), 'exit')
        row['passed'] = True
    except Exception as error:
        row['error'] = str(error)
    finally:
        current = path.read_text(encoding='utf-8', errors='replace')
        row['log_end'] = len(current)
        row['log_prefix_sha256'] = hashlib.sha256(current.encode('utf-8')).hexdigest()
        row['lines'] = current[offset:].splitlines()
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        target = work / ('active-world-actions-' + stamp + '.json')
        target.write_text(json.dumps(row, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'report': str(target), 'passed': row['passed'], 'error': row.get('error')}, ensure_ascii=False))
    return 0 if row['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
