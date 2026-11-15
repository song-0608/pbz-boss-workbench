"""用普通已注册技能耗尽本轮训练目标，再核对残留锁定清理；不写血量。"""
import json
from pathlib import Path
import re
import time

import ahua_practice as practice
import research_game_menu as menu
from collect_workbench_recovery import proof as recovery_proof
from control_action_evidence import restoration_result
from player_target_readiness import ensure_visible_target, latest_target_status
from test_player_skill_batch import action_proof, resolve_binding, wait_for


def main():
    owner, state = practice.owned_session()
    assert owner['phase'] == 'armed' and owner.get('player_entry')
    work = Path(state['work'])
    path = practice.log_path(state)
    target = work / 'dead-target-recovery-actions.json'
    assert not target.exists(), 'Preserve the existing recovery attempt'
    binding = resolve_binding(owner['actual_bindings'], 'skill_07')
    session = 'official-validation-' + work.name
    start = len(path.read_text(encoding='utf-8', errors='replace'))
    report = {'state_file': state['state_file'], 'log_offset': start,
              'binding': binding, 'casts': [], 'passed': False}

    def raw():
        return path.read_text(encoding='utf-8', errors='replace')

    def healthy(text):
        assert not any(k in text for k in ('state=FAULTED', 'PBZ_CONTROL_LIFECYCLE:ISSUE_',
            'PBZ_CONTROL_RESTORE:FAILED=', 'HUD_UNAVAILABLE=')), 'Runtime failure'

    def status(text):
        return latest_target_status(text, session, time.time(), allow_unavailable=True)

    def health(row):
        match = re.search(r'^目标：.+ \| 生命 (-?\d+(?:\.\d+)?)$', row['hud']['text'], re.M)
        assert match, 'Exact current target health required'
        return float(match[1])

    try:
        assert min(state['deadline_unix'], state['control_probe_expires_at'] - 20) - time.time() > 230
        menu.click(0, 0, 2560, 1600, 'control_enter')
        entered = wait_for(path, start, lambda t: 'enter success=true state=ACTIVE' in t, 8, True)
        assert 'enter success=true state=ACTIVE' in entered
        ensure_visible_target(path, start, session, wait_for, menu.click, time.time)
        initial = status(raw()[start:])
        assert initial and initial['visibility'] == 'visible'
        original_target = initial['target']
        previous_health = health(initial)
        assert previous_health > 0
        deadline = min(time.monotonic() + 215,
                       time.monotonic() + state['deadline_unix'] - time.time() - 40)
        for number in range(1, 41):
            assert time.monotonic() < deadline, 'Bounded ordinary attack budget exhausted'
            current = raw()[start:]
            healthy(current)
            before = status(current)
            assert before and before['target'] == original_target and before['visibility'] == 'visible'
            assert health(before) == previous_health and previous_health > 0
            cast_offset = len(raw())
            menu.click(0, 0, 2560, 1600, 'control_registered_skill_' + binding['slot'])
            tail = wait_for(path, cast_offset,
                lambda t: bool(action_proof(t, 'skill_07')['natural_completion']), 12, True)
            healthy(tail)
            natural = action_proof(tail, 'skill_07')['natural_completion']
            assert natural and natural['damage_observed'], 'Actual ordinary skill damage required'
            assert natural['health_before'] == previous_health
            after_health = natural['health_after']
            assert 0 <= after_health < previous_health
            report['casts'].append({'number': number, 'log_offset': cast_offset,
                'log_end': len(raw()), 'natural_completion': natural})
            print('训练目标普通技能伤害：' + str(previous_health) + ' → ' + str(after_health), flush=True)
            previous_health = after_health
            if after_health == 0:
                dead = wait_for(path, start,
                    lambda t: bool(status(t) and status(t)['target'] is not None
                        and health(status(t)) == 0), 5)
                assert status(dead) and health(status(dead)) == 0, 'Fresh actual dead-target HUD required'
                break
            wait_for(path, cast_offset, lambda t: bool(status(t) and health(status(t)) == after_health), 4)
            time.sleep(.35)
        assert previous_health == 0, 'Target survived bounded ordinary inputs'
        menu.click(0, 0, 2560, 1600, 'control_exit')
        tail = wait_for(path, start, lambda t: restoration_result(t, 'exit')['passed'], 10)
        report['proof'] = recovery_proof(tail)
        assert report['proof']['passed'], 'Dead-target fallback and full restoration not verified'
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
    finally:
        current = raw()[start:]
        if 'enter success=true state=ACTIVE' in current and not restoration_result(current, 'exit')['passed']:
            try:
                menu.click(0, 0, 2560, 1600, 'control_exit')
                report['failure_restoration'] = restoration_result(wait_for(path, start,
                    lambda t: restoration_result(t, 'exit')['passed'], 10), 'exit')
            except Exception as error:
                report['cleanup_error'] = str(error)
        report['log_end'] = len(raw())
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
