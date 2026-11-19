"""Read-only native-combo lifecycle audit; never promotes a Boss or release.

Match scheduler, keyed parent instance and allowed child observations inside one
takeover. A historical active observation cannot prove activity at cancellation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, sha, write_json
import boss_native_combo_candidate as candidate
import boss_skill_repeat_audit as repeat
from collect_skill_acceptance import analyze
from mod_installation import unlinked_path

SOURCES = ('tools/boss_native_combo_audit.py', 'tests/test_boss_native_combo_audit.py',
           *repeat.SOURCES)
START = re.compile(r'COMBO_SCHEDULER_BEGIN=([^|\r\n]+)\|brain_tick=true\|outer_ai=false\|ai_tick=false\|limit=25(?=\r?$)', re.M)
OBSERVED = re.compile(r'COMBO_OBSERVED_ACTIVE=([^|\r\n]+)\|active=([1-9]\d*)\|baseline=0(?=\r?$)', re.M)
END = re.compile(r'COMBO_SCHEDULER_END=(natural|cancelled)=true\|all_grants_at_baseline=true\|brain_tick=false(?=\r?$)', re.M)
CANCEL = re.compile(r'COMBO_CANCEL_BEGIN=([^|\r\n]+)\|parent_active=(\d+)\|active_children=(\d+)(?=\r?$)', re.M)


def reviewed_definition(bundle, root=ROOT):
    """Recheck the original frozen graph without substituting later inventory.

    Closing a session adds new historical grants, so rebuilding a current live
    candidate would silently change which graph/bundle a historical audit uses.
    This only authenticates the immutable development graph, never deployment.
    """
    root, bundle = unlinked_path(root), unlinked_path(bundle)
    assert bundle.parent == root / candidate.OUTPUT, 'internal frozen combo bundle required'
    manifest = candidate.read(bundle / 'manifest.json')
    definition = manifest['definition']; identifier = definition['id']
    assert identifier in candidate.REVIEWS
    review = candidate.REVIEWS[identifier]
    key = hashlib.sha256(candidate.canonical(manifest)).hexdigest()[:20]
    assert bundle.name == identifier + '-' + key, 'frozen candidate identity changed'
    assert manifest['schema'] == 1 and manifest['kind'] == 'isolated_native_combo_candidate'
    assert manifest['build'] == candidate.BUILD and manifest['developer_only'] is True
    assert all(manifest[k] is False for k in ('playable','installed','game_started','runtime_acceptance_current'))
    assert manifest['execution_order'] == 'native_engine_only'
    files = manifest['overrides']
    assert set(files) == {'boss_candidate.lua','combo_scheduler.lua','subtree_contracts.lua','owned_arena.lua'}
    assert {p.name for p in bundle.iterdir()} == set(files) | {'manifest.json'}
    assert all(sha(unlinked_path(bundle / name)) == digest for name,digest in files.items()), 'frozen payload changed'
    assert manifest['module_sha256'] == files['boss_candidate.lua']
    graph_path = unlinked_path(root / manifest['dependency_report'])
    assert graph_path.is_relative_to(root / candidate.dependencies.OUTPUT), 'internal dependency report required'
    assert sha(graph_path) == manifest['dependency_report_sha256'] == definition['dependency_report_sha256']
    graph = candidate.read(graph_path)
    rows = [r for r in graph['parents'] if r['id'] == identifier and r['parent_class'] == review['parent']]
    assert len(rows) == 1
    row, = rows
    assert row['declaration_closure_complete'] and not row['issues'] and not row['context_review']
    assert row['subtree_classes'] == [review['parent']] and not row['activation_allowed'] and not row['playable']
    assert definition['class_path'] == review['actor'] and definition['config_path'] == review['config']
    assert definition['parent_class'] == review['parent'] and definition['ability_pool'] == [review['parent']]
    assert definition['contract'] == {'class':review['parent'],'actor':review['actor'],'config':review['config'],
        'trees':{t['path']:t['weight'] for t in row['trees']}, 'leaves':{p:True for p in row['leaf_classes']}}
    assert any(p['actor'] == review['actor'] and p['config'] == review['config'] and p['parent_grant_snapshots']
               for p in row['exact_parent_variants'])
    return definition


def audit_cycle(text, definition, *, mode='natural', repetitions=5):
    assert mode in ('natural', 'cancel')
    contract = definition['contract']; parent = contract['class']; leaves = set(contract['leaves'])
    assert parent == definition['parent_class'] and leaves and parent not in leaves
    short = parent.rsplit('.', 1)[-1]
    base = repeat.audit_cycle(text, 'skill_01', short, repetitions=repetitions)
    recovery = list(repeat.RESTORE.finditer(text))
    boundary = recovery[0].start() if recovery else len(text)
    live = text[:boundary]
    starts = list(START.finditer(live))
    begins = list(repeat.BEGIN.finditer(live))
    rows = []
    for ordinal, start in enumerate(starts):
        stop = starts[ordinal + 1].start() if ordinal + 1 < len(starts) else len(live)
        segment = live[start.start():stop]
        requests = list(repeat.BEGIN.finditer(segment))
        observed = list(OBSERVED.finditer(segment))
        ends = list(END.finditer(segment))
        cancels = list(CANCEL.finditer(segment))
        proof = analyze(segment, 'skill_01')
        classes = [m[1] for m in observed]
        observed_shape = (len(observed) == segment.count('COMBO_OBSERVED_ACTIVE=')
            and len(classes) == len(set(classes)) and set(classes) <= leaves | {parent}
            and all(int(m[2]) <= 255 for m in observed))
        paired = bool(start[1] == 'skill_01' and len(requests) == 1 and requests[0][1] == 'skill_01'
            and proof['activation_instance_verified'] and proof['ability_class_short'] == short
            and len(ends) == 1 and observed_shape and parent in classes and leaves.intersection(classes)
            # The bridge samples the newly active parent synchronously before
            # host.log emits KEY_SKILL_BEGIN; later children arrive on ticks.
            # Both belong to this exact scheduler ticket, never a prior cast.
            and all(start.end()-start.start() <= m.start() < ends[0].start() for m in observed)
            and len(ends) == segment.count('COMBO_SCHEDULER_END='))
        keyed_ends = list(re.finditer(r'KEY_SKILL_END=skill_01\|', segment))
        natural = bool(paired and ends[0][1] == 'natural' and not cancels
            and 'COMBO_CANCEL_BEGIN=' not in segment and len(keyed_ends) == 1
            # Parent sampling can finish before the final child returns to
            # baseline. Require both closures in this same ticket interval.
            and proof['natural_completion'])
        stops = list(re.finditer(r'COMBO_TREE_STOP=running_before=(?:true|false)(?=\r?$)', segment, re.M))
        cancel = bool(paired and ends[0][1] == 'cancelled' and len(cancels) == 1
            and segment.count('COMBO_CANCEL_BEGIN=') == 1 and cancels[0][1] == 'skill_01'
            and 0 <= int(cancels[0][2]) <= 255 and 0 <= int(cancels[0][3]) <= len(leaves)
            and int(cancels[0][2]) + int(cancels[0][3]) > 0 and len(stops) == segment.count('COMBO_TREE_STOP=') == 1
            and all(m.end() <= cancels[0].start() for m in observed)
            and cancels[0].end() <= stops[0].start() < ends[0].start()
            and not proof['natural_completion'])
        rows.append(dict(ordinal=ordinal + 1, interval_sha256=hashlib.sha256(segment.encode()).hexdigest(),
            parent_and_allowed_child_observed=paired, observed_classes=classes,
            natural_scheduler_and_parent_end_observed=natural,
            active_cancellation_and_all_grants_baseline_observed=cancel,
            cancellation_snapshot=dict(parent_active=int(cancels[0][2]), active_children=int(cancels[0][3]))
                if len(cancels) == 1 else None))
    shape = bool(len(starts) == len(begins) == len(rows) > 0
        and len(starts) == live.count('COMBO_SCHEDULER_BEGIN=')
        and len(rows) == live.count('COMBO_SCHEDULER_END=')
        and sum(len(OBSERVED.findall(live[s.start():starts[i+1].start() if i+1 < len(starts) else len(live)]))
                for i,s in enumerate(starts)) == live.count('COMBO_OBSERVED_ACTIVE=')
        and len(CANCEL.findall(live)) == live.count('COMBO_CANCEL_BEGIN=')
        and (not starts or not any(token in live[:starts[0].start()] for token in ('COMBO_',)))
        and 'PBZ_COMBO_CANCEL:FAILED=' not in text
        and not any(token in text[boundary:] for token in ('COMBO_SCHEDULER_', 'COMBO_OBSERVED_ACTIVE=', 'COMBO_CANCEL_BEGIN=')))
    restored = base['explicit_player_exit_verified']
    natural = bool(mode == 'natural' and shape and base['consecutive_natural_uses_verified'] and restored
        and all(r['natural_scheduler_and_parent_end_observed'] for r in rows))
    cancelled = bool(mode == 'cancel' and shape and base['same_control_verified'] and restored and len(rows) == 1
        and rows[0]['active_cancellation_and_all_grants_baseline_observed'])
    return dict(schema=1, kind='native_combo_lifecycle_observation', mode=mode,
        parent_class=parent, allowed_leaf_classes=sorted(leaves), attempts=rows,
        skill_repeat_observation=base, scheduler_events_paired=shape,
        repeated_native_lifecycle_and_player_recovery_observed=natural,
        active_native_cancellation_and_player_recovery_observed=cancelled,
        every_use_health_decrease_observed=bool(natural and base['every_use_health_decrease_observed']),
        lifecycle_observation_passed=natural or cancelled, native_execution_order_inferred=False,
        runtime_bundle_identity_verified=False, exact_live_grants_verified=False,
        runtime_acceptance_current=False, playable=False, release_accepted=False,
        scope='Captured lifecycle only; deployment identity, exact live grants, input gates and gameplay acceptance remain separate.')


def closed_audit(session, cycle, bundle, *, mode='natural', repetitions=5, root=ROOT):
    root = unlinked_path(root)
    bundle = unlinked_path(bundle)
    definition = reviewed_definition(bundle, root=root)
    baseline = repeat.closed_audit(session, cycle, 'skill_01', definition['parent_class'].rsplit('.', 1)[-1],
                                   repetitions=repetitions, root=root)
    log = unlinked_path(root / 'evidence/official-validation' / session / 'UE4SS.log')
    raw = log.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == baseline['sources'][log.relative_to(root).as_posix()], 'log changed during audit'
    _, _, segment = repeat.cycle_interval(raw.decode('utf-8', errors='strict'), cycle)
    result = audit_cycle(segment, definition, mode=mode, repetitions=repetitions)
    result.update(session=session, cycle=cycle, sources=baseline['sources'],
        log_character_start=baseline['log_character_start'], log_character_end=baseline['log_character_end'],
        reviewed_graph_candidate_manifest_sha256=sha(bundle / 'manifest.json'),
        audit_source_sha256={p:sha(ROOT / p) for p in SOURCES}, historical_observation_only=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session'); parser.add_argument('cycle', type=int); parser.add_argument('candidate', type=Path)
    parser.add_argument('--mode', choices=('natural', 'cancel'), default='natural')
    parser.add_argument('--repetitions', choices=(3,4,5), type=int, default=5)
    args = parser.parse_args()
    result = closed_audit(args.session, args.cycle, args.candidate, mode=args.mode, repetitions=args.repetitions)
    key = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    path = ROOT / 'evidence/adaptation' / ('boss-native-combo-observation-' + key + '.json')
    if path.exists(): assert candidate.read(path) == result
    else: write_json(path, result)
    print(json.dumps(dict(report=str(path), lifecycle_observation_passed=result['lifecycle_observation_passed'],
        runtime_acceptance_current=False, playable=False), ensure_ascii=False))
