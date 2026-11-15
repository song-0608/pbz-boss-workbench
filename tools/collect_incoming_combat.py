"""从关闭会话原始区间重验真实来袭、生命耗尽与自动恢复，保留失败。"""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from control_action_evidence import restoration_result

ROOT = Path(__file__).resolve().parents[1]


def proof(segment):
    begin = re.search(r'INCOMING_COMBAT_BEGIN=health=([\d.-]+)\|sources=2\|seconds=(180|360)', segment)
    health = [(float(a), float(b)) for a, b in re.findall(
        r'OWNED_COMBAT_HEALTH=before=([\d.-]+)\|after=([\d.-]+)', segment)]
    casts = re.findall(r'INCOMING_COMBAT_CAST=([^|\r\n]+)\|skill=skill_07\|number=(\d+)\|active=(\d+)', segment)
    sources = sorted({name for name, _, _ in casts})
    chain = bool(begin and health and float(begin[1]) > 0)
    previous = float(begin[1]) if begin else None
    for before, after in health:
        chain = chain and all(math.isfinite(v) for v in (before, after)) and before == previous and after < before
        previous = after
    depleted = bool(chain and previous <= 0)
    restore = restoration_result(segment, 'auto_exit', 'boss health depleted')
    stop = segment.find('INCOMING_COMBAT_STOP=all_source_abilities_inactive=true')
    exit_at = segment.find('[PBZBossControl] auto_exit success=true state=OFF reason=boss health depleted')
    zero = next((m.start() for m in re.finditer(
        r'OWNED_COMBAT_HEALTH=before=([\d.-]+)\|after=([\d.-]+)', segment) if float(m[2]) <= 0), -1)
    first_cast = segment.find('INCOMING_COMBAT_CAST=')
    first_drop = segment.find('OWNED_COMBAT_HEALTH=')
    source_valid = len(sources) == 2 and all(name.startswith('BP_Monster_AHua_GuiTouDao_C ') for name in sources)
    for source in sources:
        numbers = [int(number) for name, number, _ in casts if name == source]
        source_valid = source_valid and numbers == list(range(1, len(numbers) + 1)) and len(numbers) <= 32
    faults = any(token in segment for token in ('ISSUE_', 'state=FAULTED', 'PBZ_CONTROL_RESTORE:FAILED=',
        'OWNED_DEATH_TRIAL_KILL_REQUESTED=', '[PBZBossControl] exit success=true', 'INCOMING_COMBAT_TIMEOUT='))
    result = {'observed_health_changes': health, 'native_skill_casts': len(casts), 'sources': sources,
        'continuous_health_depletion': depleted, 'source_sequence_verified': source_valid,
        'source_cleanup_before_auto_restore': 0 <= zero < stop < exit_at,
        'native_cast_preceded_damage': bool(begin and begin.start() < first_cast < first_drop),
        'restoration': restore, 'fault_absent': not faults}
    result['passed'] = all((depleted, source_valid, result['source_cleanup_before_auto_restore'],
        result['native_cast_preceded_damage'], restore['passed'], not faults))
    samples = [float(v) for v in re.findall(r'INCOMING_COMBAT_SNAPSHOT=(?:stopped|after_restore)\|player_health=([\d.-]+)', segment)]
    result['post_restore_health_samples'] = samples
    result['post_restore_stability_verified'] = bool(samples and len(set(samples)) == 1
        and 'INCOMING_COMBAT_POST_RESTORE_BEGIN=seconds=60' in segment
        and 'INCOMING_COMBAT_POST_RESTORE_END=true' in segment
        and 'INCOMING_COMBAT_POST_RESTORE_REJECTED=' not in segment)
    return result


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def collect(session):
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    state = read(ROOT / 'runtime' / ('official-validation-' + session) / 'state.json')
    work = Path(state['work'])
    assert state.get('restored') and work.name == session, 'matching closed session required'
    post = read(work / 'postcheck.json')
    assert post['validation_state'] == state['state_file'] and not post['formal_files_changed']
    assert not post['host_config_files_changed'] and post['host_registry_unchanged']
    assert post['research_box_empty'] and post['research_loader_removed']
    action = read(work / 'incoming-combat-actions.json')
    assert action['state_file'] == state['state_file']
    raw = (work / 'UE4SS.log').read_bytes()
    text = raw.decode('utf-8', errors='replace')
    start, end = action['log_offset'], action['log_end']
    assert 0 <= start < end <= len(text), 'original action interval required'
    deployments = [read(p) for p in work.glob('control-lifecycle-deployment-*.json')]
    stamp = re.search(r'\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)', text[start:end])
    assert stamp, 'timestamped original interval required'
    began = datetime.fromisoformat(stamp[1]).replace(tzinfo=datetime.fromisoformat(action['at']).tzinfo)
    deployment = max((d for d in deployments if datetime.fromisoformat(d['at']) <= began), key=lambda d: d['at'])
    assert deployment['incoming_combat_trial'] and deployment['death_trial']
    assert not any(deployment.get(k) for k in ('native_death_trial', 'active_skill_death_trial', 'player_entry'))
    assert {'incoming_combat_trial.lua', 'owned_arena.lua', 'session.lua'} <= deployment['module_source_sha256'].keys()
    result = proof(text[start:end])
    assembly = text[:start].rsplit('PBZ_CONTROL_LIFECYCLE:DEFERRED_ACTOR=', 1)[-1]
    owned_sources = sorted(set(re.findall(r'PBZ_CONTROL_LIFECYCLE:TRAINING_TARGET(?:_[12])?=([^\r\n]+)', assembly)))
    result['exact_owned_sources'] = len(owned_sources) == 2 and result['sources'] == owned_sources
    assert result['native_skill_casts'] == action['native_skill_casts']
    assert result['observed_health_changes'] == [tuple(pair) for pair in action['observed_health_changes']]
    result.update(session=session, log_offset=start, log_end=end, source_log_sha256=hashlib.sha256(raw).hexdigest(),
        deployment_at=deployment['at'], module_source_sha256=deployment['module_source_sha256'],
        manual_exit=action['manual_exit'], complete_mod=False)
    result['passed'] = result['passed'] and result['exact_owned_sources'] and not action['manual_exit']
    target = work / 'incoming-combat-evidence.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(target), 'passed': result['passed']}, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('session')
    raise SystemExit(collect(parser.parse_args().session))
