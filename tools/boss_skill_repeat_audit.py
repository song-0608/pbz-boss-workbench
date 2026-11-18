"""Audit consecutive skill uses inside one control receipt; no game or UI calls.

Class names in SKILL_INSTANCE are short runtime names, not full native grant
paths. This audit never promotes a character or replaces grant/cancel gates.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, sha, write_json
from control_action_evidence import control_identity, restoration_result
from collect_skill_acceptance import analyze
from candidate_effect_scope import local_effect
from mod_installation import unlinked_path

ENTER = re.compile(r'\[PBZBossControl\] enter success=true state=ACTIVE[^\r\n]*')
RESTORE = re.compile(r'\[PBZBossControl\] (exit|menu_exit|auto_exit) success=true state=OFF[^\r\n]*')
BEGIN = re.compile(r'KEY_SKILL_BEGIN=([^|\r\n]+)\|target=([^|\r\n]+)\|health=([^|\r\n]+)\|active=(\d+)')
SOURCES = ('tools/boss_skill_repeat_audit.py', 'tests/test_boss_skill_repeat_audit.py',
           'tools/control_action_evidence.py', 'tools/collect_skill_acceptance.py',
           'tools/candidate_effect_scope.py')


def cycle_interval(text, index):
    assert type(index) is int and index >= 0
    entries = list(ENTER.finditer(text))
    assert index < len(entries), 'control cycle does not exist'
    # Keep its final recovery readbacks, but stop before the next takeover.
    start = entries[index].start()
    end = entries[index + 1].start() if index + 1 < len(entries) else len(text)
    return start, end, text[start:end]


def audit_cycle(text, skill, class_short, *, repetitions=5, action_kind='attack'):
    assert type(repetitions) is int and 3 <= repetitions <= 5, 'three to five consecutive uses required'
    assert action_kind in ('attack', 'dodge')
    assert re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', skill)
    assert re.fullmatch(r'GA_[A-Za-z0-9_]+_C', class_short)
    entries = list(ENTER.finditer(text))
    assert len(entries) == 1, 'never join separate takeovers'
    assert not text[:entries[0].start()].strip(), 'cycle must start with its control entry'
    identity = control_identity(text)
    recovery = list(RESTORE.finditer(text))
    # Ending through stop/lease cleanup is recorded as incomplete recovery;
    # it cannot become a successful player F10 action.
    boundary = recovery[0].start() if recovery else len(text)
    live = text[:boundary]
    post_recovery_skill_events = bool(re.search(r'KEY_SKILL_(?:BEGIN|END)=', text[boundary:]))
    assert not any(t in live for t in ('SPAWN_ATTEMPT=', 'PLAYER_ENTRY_READY=',
                                     'WORKBENCH_BOSS_SELECTED=', 'CONTROL_WORLD:OLD_OBJECTS_DISPOSED=')), \
        'assembly or world changed inside control cycle'
    begins = list(BEGIN.finditer(live))
    all_requests = re.findall(r'KEY_SKILL_BEGIN=([^|\r\n]+)\|', live)
    assert len(all_requests) == len(begins), 'malformed skill request must not disappear from audit'
    foreign = sorted(set(all_requests) - {skill})
    rows = []
    last_end = -1
    all_end_count = len(re.findall(r'KEY_SKILL_END=[^|\r\n]+\|', live))
    for index, begin in enumerate(begins):
        end = begins[index + 1].start() if index + 1 < len(begins) else len(live)
        interval = live[begin.start():end]
        proof = local_effect(analyze(interval, skill), interval)
        ends = list(re.finditer(r'KEY_SKILL_END=' + re.escape(skill) + r'\|', interval))
        instances = re.findall(r'SKILL_INSTANCE=' + re.escape(skill) + r'\|', interval)
        health = float(begin[3])
        natural = proof['natural_completion']
        consistent_health = bool(natural and math.isfinite(health) and health >= 0
                                 and health == natural['health_before'])
        lifecycle = bool(begin[1] == skill and int(begin[4]) > 0 and len(ends) == 1
            and len(instances) == 1 and proof['activation_instance_verified']
            and proof['ability_class_short'] == class_short and natural and consistent_health
            and begin.start() > last_end and not proof['foreign_keyed_activations'])
        if ends: last_end = begin.start() + ends[-1].end()
        damage = natural['health_before'] - natural['health_after'] if natural else None
        rows.append(dict(ordinal=index + 1, skill=begin[1], target=begin[2],
            log_start=begin.start(), log_end=end, interval_sha256=hashlib.sha256(interval.encode()).hexdigest(),
            lifecycle_verified=lifecycle, short_class_matches=proof['ability_class_short'] == class_short,
            natural=natural, observed_health_decrease=damage,
            local_displacement_verified=proof['local_displacement_verified'],
            attack_health_decrease_observed=bool(lifecycle and damage is not None and damage > 0),
            dodge_displacement_observed=bool(lifecycle and natural['movement_observed'])))
    rejected = any(token in live for token in ('success=false', 'SKILL_NATIVE_REJECTED=',
        'state=FAULTED', 'PBZ_CONTROL_RESTORE:FAILED=', 'PBZ_CONTROL_LIFECYCLE:ISSUE_'))
    same_control = bool(identity and not foreign and not rejected and not post_recovery_skill_events)
    repeated = bool(same_control and len(rows) >= repetitions and all_end_count == len(rows)
                    and all(row['lifecycle_verified'] for row in rows))
    health_decrease = bool(repeated and all(row['attack_health_decrease_observed'] for row in rows))
    dodge_motion = bool(repeated and all(row['dodge_displacement_observed'] for row in rows))
    # Require exactly the recovery closing this cycle. Later events cannot
    # complete missing camera/player readbacks from the first recovery.
    restored = restoration_result(text) if len(recovery) == 1 else {'passed': False, 'reason': 'one recovery required'}
    return dict(schema=1, skill=skill, expected_class_short=class_short, action_kind=action_kind,
        requested_repetitions=repetitions, observed_attempts=len(rows), attempts=rows,
        identity=identity, foreign_keyed_activations=foreign, native_rejection_or_failure_seen=rejected,
        post_recovery_skill_events=post_recovery_skill_events,
        same_control_verified=same_control, consecutive_natural_uses_verified=repeated,
        every_use_health_decrease_observed=health_decrease, every_use_dodge_displacement_observed=dodge_motion,
        restoration=restored, explicit_player_exit_verified=bool(restored.get('passed') and restored.get('label') == 'exit'),
        repeated_effect_and_recovery_observed=bool(repeated and restored['passed']
            and (health_decrease if action_kind == 'attack' else dodge_motion)),
        exact_native_grant_path_verified=False, cancellation_verified=False,
        playable=False, release_accepted=False,
        scope='One captured control cycle and runtime short class only; observed health change is not source-attributed damage.')


def closed_audit(session, cycle, skill, class_short, *, repetitions=5, action_kind='attack', root=ROOT):
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    root = unlinked_path(root)
    state_path = unlinked_path(root / 'runtime' / ('official-validation-' + session) / 'state.json')
    state = json.loads(state_path.read_bytes())
    work = unlinked_path(root / 'evidence/official-validation' / session)
    assert unlinked_path(Path(state['work'])) == work and state.get('restored') is True
    assert state['state_file'] == str(state_path)
    post_path = unlinked_path(work / 'postcheck.json'); post = json.loads(post_path.read_bytes())
    assert post['validation_state'] == str(state_path)
    assert all(post[k] is True for k in ('research_box_empty', 'research_loader_removed', 'host_registry_unchanged'))
    assert not post['formal_files_changed'] and not post['host_config_files_changed']
    log_path = unlinked_path(work / 'UE4SS.log')
    text = log_path.read_bytes().decode('utf-8', errors='strict')
    start, end, segment = cycle_interval(text, cycle)
    result = audit_cycle(segment, skill, class_short, repetitions=repetitions, action_kind=action_kind)
    if result['identity']:
        assert result['identity']['world_id'].split('|', 1)[0] == 'official-validation-' + session
    result.update(session=session, cycle=cycle, log_character_start=start, log_character_end=end,
                  historical_observation_only=True, runtime_acceptance_current=False,
                  sources={p.relative_to(root).as_posix(): sha(p) for p in (state_path, post_path, log_path)},
                  audit_source_sha256={p: sha(ROOT / p) for p in SOURCES})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session'); parser.add_argument('cycle', type=int)
    parser.add_argument('skill'); parser.add_argument('class_short')
    parser.add_argument('--repetitions', type=int, choices=(3, 4, 5), default=5)
    parser.add_argument('--action-kind', choices=('attack', 'dodge'), default='attack')
    args = parser.parse_args()
    report = closed_audit(args.session, args.cycle, args.skill, args.class_short,
                          repetitions=args.repetitions, action_kind=args.action_kind)
    key = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()[:16]
    target = ROOT / 'evidence/adaptation' / ('boss-skill-repeat-' + key + '.json')
    if target.exists(): assert json.loads(target.read_bytes()) == report
    else: write_json(target, report)
    print(json.dumps(dict(report=str(target), natural=report['consecutive_natural_uses_verified'],
        health_decrease=report['every_use_health_decrease_observed'], restored=report['restoration']['passed'],
        playable=False, runtime_acceptance_current=False), ensure_ascii=False))
