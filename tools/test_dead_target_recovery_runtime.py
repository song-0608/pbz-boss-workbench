"""用普通已注册技能耗尽本轮训练目标，再核对残留锁定清理；不写血量。"""
import argparse
import json
import math
from pathlib import Path
import re
import time

import ahua_practice as practice
import research_game_menu as menu
from collect_workbench_recovery import proof as recovery_proof
from control_action_evidence import restoration_result
from player_target_readiness import ensure_visible_target, latest_target_status
from test_player_skill_batch import action_proof, resolve_binding, wait_for


ATTACK_SEQUENCE = ('skill_06', 'skill_09') * 4
ATTACK_SECONDS = 215


def target_health(row, expected_name=None):
    if not row or row.get('target') is None:
        raise RuntimeError('Exact current target health required')
    match = re.search(r'^目标：(.+) \| 生命 (-?\d+(?:\.\d+)?)$', row['hud']['text'], re.M)
    if not match or match[1] != row['target']:
        raise RuntimeError('Exact current target health required')
    name = match[1].removesuffix('（已死亡）')
    if expected_name is not None and name != expected_name:
        raise RuntimeError('Training target display identity changed')
    value = float(match[2])
    if not math.isfinite(value) or value < 0:
        raise RuntimeError('Finite nonnegative target health required')
    return name, value


def validate_cast(text, skill, previous_health, expected_actor=None):
    begins = re.findall(r'KEY_SKILL_BEGIN=' + re.escape(skill)
        + r'\|target=([^|\r\n]+)\|health=([^|\r\n]+)\|active=([1-9]\d*)', text)
    if len(begins) != 1 or begins[0][0] == 'None':
        raise RuntimeError('One exact active skill and target instance required')
    actor = begins[0][0]
    if expected_actor is not None and actor != expected_actor:
        raise RuntimeError('Training target instance changed')
    natural = action_proof(text, skill)['natural_completion']
    if not natural or not natural['damage_observed']:
        raise RuntimeError('Actual ordinary skill damage required')
    before, after = natural['health_before'], natural['health_after']
    values = (previous_health, float(begins[0][1]), before, after)
    if not all(math.isfinite(v) for v in values) or not (
            previous_health == float(begins[0][1]) == before and 0 <= after < before):
        raise RuntimeError('Unbroken actual target health chain required')
    return actor, natural


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-only', action='store_true', help='仅显示有界普通按键计划，不读取会话或操作游戏')
    args = parser.parse_args()
    if args.plan_only:
        print(json.dumps({'skills': ATTACK_SEQUENCE, 'maximum_casts': len(ATTACK_SEQUENCE),
            'attack_seconds': ATTACK_SECONDS, 'stop_on_miss': True,
            'exact_target_instance_required': True, 'game_started': False,
            'game_input_sent': False}, ensure_ascii=False))
        return 0
    owner, state = practice.owned_session()
    assert owner['phase'] == 'armed' and owner.get('player_entry')
    assert not any(owner.get(k) for k in ('skill_lab', 'expanded', 'death_trial', 'boss_candidate'))
    work = Path(state['work'])
    path = practice.log_path(state)
    target = work / 'dead-target-recovery-actions.json'
    assert not target.exists(), 'Preserve the existing recovery attempt'
    from player_settings import BOSSES
    from player_target_readiness import deployed_boss_name
    deployment = practice.read(work / 'control-lifecycle-deployment.json')
    boss_name = deployed_boss_name(owner, deployment,
        path.read_text(encoding='utf-8', errors='replace')[owner['log_offset']:], BOSSES)
    assert boss_name == BOSSES['ahua_guitoudao'], 'Current ordinary Ahua entry required'
    bindings = {skill: resolve_binding(owner['actual_bindings'], skill) for skill in dict.fromkeys(ATTACK_SEQUENCE)}
    session = 'official-validation-' + work.name
    start = len(path.read_text(encoding='utf-8', errors='replace'))
    report = {'state_file': state['state_file'], 'log_offset': start,
              'bindings': bindings, 'attack_sequence': ATTACK_SEQUENCE,
              'attack_seconds': ATTACK_SECONDS, 'casts': [], 'passed': False}

    def save():
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def raw():
        return path.read_text(encoding='utf-8', errors='replace')

    def healthy(text):
        assert not any(k in text for k in ('state=FAULTED', 'PBZ_CONTROL_LIFECYCLE:ISSUE_',
            'PBZ_CONTROL_RESTORE:FAILED=', 'HUD_UNAVAILABLE=')), 'Runtime failure'

    def status(text):
        return latest_target_status(text, session, time.time(), allow_unavailable=True)

    try:
        assert min(state['deadline_unix'], state['control_probe_expires_at'] - 20) - time.time() > 230
        menu.click(0, 0, 2560, 1600, 'control_enter')
        entered = wait_for(path, start, lambda t: 'enter success=true state=ACTIVE' in t, 8, True)
        assert 'enter success=true state=ACTIVE' in entered
        ensure_visible_target(path, start, session, wait_for, menu.click, time.time)
        initial = status(raw()[start:])
        assert initial and initial['visibility'] == 'visible'
        original_target, previous_health = target_health(initial)
        original_actor = None
        assert previous_health > 0
        deadline = min(time.monotonic() + ATTACK_SECONDS, time.monotonic()
            + min(state['deadline_unix'], state['control_probe_expires_at'] - 20) - time.time() - 40)
        for number, skill in enumerate(ATTACK_SEQUENCE, 1):
            assert time.monotonic() < deadline, 'Bounded ordinary attack budget exhausted'
            current = raw()[start:]
            healthy(current)
            before = status(current)
            assert before and before['visibility'] == 'visible'
            assert target_health(before, original_target)[1] == previous_health and previous_health > 0
            cast_offset = len(raw())
            cast = {'number': number, 'skill': skill, 'binding': bindings[skill],
                    'log_offset': cast_offset, 'passed': False, 'cast_dispatched': False}
            report['casts'].append(cast)
            save()
            menu.click(0, 0, 2560, 1600, 'control_registered_skill_' + bindings[skill]['slot'])
            cast['cast_dispatched'] = True
            tail = wait_for(path, cast_offset,
                lambda t: bool(action_proof(t, skill)['natural_completion']),
                min(40, max(0, deadline - time.monotonic())), True)
            cast.update(log_end=len(raw()), natural_completion=action_proof(tail, skill)['natural_completion'])
            save()
            healthy(tail)
            original_actor, natural = validate_cast(tail, skill, previous_health, original_actor)
            after_health = natural['health_after']
            cast.update(passed=True, target_actor=original_actor)
            save()
            print('训练目标普通技能伤害：' + str(previous_health) + ' → ' + str(after_health), flush=True)
            previous_health = after_health
            if after_health == 0:
                dead = wait_for(path, start,
                    lambda t: bool(status(t) and status(t)['target'] is not None
                        and target_health(status(t), original_target)[1] == 0), 5)
                assert status(dead) and target_health(status(dead), original_target)[1] == 0, 'Fresh actual dead-target HUD required'
                break
            refreshed = wait_for(path, cast_offset, lambda t: bool(status(t)
                and target_health(status(t), original_target)[1] == after_health), 4)
            assert status(refreshed) and target_health(status(refreshed), original_target)[1] == after_health
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
        save()
        print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
