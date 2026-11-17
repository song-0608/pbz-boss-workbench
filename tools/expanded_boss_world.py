"""Native-menu World proof for one exact expansion profile, including movement-only actions."""
import argparse
import importlib
import json
from pathlib import Path
import re
import sys
import time

from boss_adaptation_workflow import ROOT, sha, write_json
from collect_auto_world_reassembly import proof as lifecycle_proof
from collect_skill_acceptance import analyze
from control_action_evidence import restoration_result
import expanded_boss_integration_workflow as workflow
import build_expanded_boss_candidate as candidate


def proof(text, identifier, class_path, ability_path):
    ready = list(re.finditer(r'PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=([^\r\n]+)', text))
    result = lifecycle_proof(text)
    if len(ready) != 2:
        return dict(result, passed=False)
    first = text[ready[0].start():ready[1].start()]
    second = text[ready[1].start():]
    natural = analyze(second, 'skill_01')
    completion = natural['natural_completion']
    result['profile_preserved'] = all(row[1] == identifier for row in ready)
    before, after = result.get('before_identity'), result.get('after_identity')
    result['exact_native_class'] = bool(before and after and all(
        row['participants']['boss']['class'].split(' ', 1)[-1] == class_path for row in (before, after)))
    result['native_primary_effect'] = bool(completion and
        natural['ability_class_short'] == ability_path.rsplit('.', 1)[-1] and
        (completion['damage_observed'] or completion['movement_observed']) and
        completion['distance'] <= 3000 and natural['restoration']['passed'])
    result['no_selection_inside_cycle'] = 'WORKBENCH_BOSS_SELECTED=' not in first + second
    required = ('old_world_and_owned_retired', 'title_wait_resumed', 'manual_rearm_absent',
                'fault_absent', 'new_identity', 'profile_preserved', 'exact_native_class',
                'native_primary_effect', 'no_selection_inside_cycle')
    # The common damage-specific field remains truthful. Movement-only native actions
    # require observed local displacement rather than being relabelled as attacks.
    result['passed'] = bool(result.get('before_restoration', {}).get('passed') and
        result.get('after_restoration', {}).get('passed') and all(result.get(k) for k in required))
    return result


def definition(manifest, identifier):
    rows = [r for r in manifest['expansion_profiles'] if r['id'] == identifier]
    assert len(rows) == 1
    report = json.loads((ROOT / rows[0]['evidence']).read_bytes())
    return report['metadata_identity']['class_path'], report['accepted_skills']['skill_01']['class_path']


def run(flow, identifier, finish=False):
    frozen = workflow.verify(flow); package = Path(frozen['candidate']); manifest = candidate.verify(package)
    class_path, ability_path = definition(manifest, identifier)
    sys.path.insert(0, str(flow))
    practice = importlib.import_module('ahua_practice')
    dispatch = importlib.import_module('test_player_experience_inputs').main
    wait_for = importlib.import_module('test_player_skill_batch').wait_for
    owner, state = practice.owned_session(); path = practice.log_path(state); work = Path(state['work'])
    assert owner['phase'] == 'armed' and owner.get('player_entry') and owner.get('workbench')
    target = work / ('expanded-world-' + identifier + '.json')
    def raw(): return path.read_text(encoding='utf-8', errors='replace')
    text = raw()
    assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)', text)[-1] == identifier
    if finish:
        report = practice.read(target)
        assert report['pre_world_passed'] and not report['passed'] and not report.get('error')
        assert report['lines'] == text[report['log_offset']:report['log_end']].splitlines()
        assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)', text[report['world_scope_offset']:]) == [identifier] * 2
    else:
        assert not target.exists() and min(state['deadline_unix'], state['control_probe_expires_at']) - time.time() > 300
        ready = list(re.finditer(r'PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=' + re.escape(identifier), text))
        assert ready
        report = dict(schema=1, state_file=state['state_file'], workflow=str(flow),
            candidate_manifest_sha256=sha(package / 'pbz-release.json'), id=identifier,
            class_path=class_path, ability_path=ability_path, log_offset=len(text),
            world_scope_offset=ready[-1].start(), pre_world_passed=False, passed=False)
    def send(action):
        start = len(raw()); dispatch(flow, action); return start
    try:
        start = send('enter')
        tail = wait_for(path, start, lambda t: 'TARGET_CAMERA_LOCK=true|initial' in t, 12, True)
        assert 'enter success=true state=ACTIVE' in tail and 'TARGET_CAMERA_LOCK=true|initial' in tail
        start = send('shift_cast')
        tail = wait_for(path, start, lambda t: bool(analyze(t, 'skill_01')['natural_completion']), 45, True)
        natural = analyze(tail, 'skill_01')
        assert natural['ability_class_short'] == ability_path.rsplit('.', 1)[-1] and natural['natural_completion']
        start = send('exit')
        tail = wait_for(path, start, lambda t: restoration_result(t, 'exit')['passed'], 12)
        assert restoration_result(tail, 'exit')['passed']
        if finish:
            result = proof(raw()[report['world_scope_offset']:], identifier, class_path, ability_path)
            assert result['passed'], result
            report.update(world_cycle=result, passed=True)
        else: report['pre_world_passed'] = True
        return 0
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        text = raw(); last = text.rfind('[PBZBossControl] enter success=true state=ACTIVE')
        if last >= report['log_offset'] and not restoration_result(text[last:])['passed']:
            try: send('exit')
            except Exception as cleanup: report['cleanup_error'] = str(cleanup)
        return 1
    finally:
        text = raw(); report.update(log_end=len(text), lines=text[report['log_offset']:].splitlines())
        write_json(target, report)
        print(json.dumps({k:v for k,v in report.items() if k not in ('lines', 'world_cycle')}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('begin', 'finish')); parser.add_argument('workflow', type=Path)
    parser.add_argument('identifier', choices=candidate.profiles.NAMES)
    args = parser.parse_args(); raise SystemExit(run(args.workflow.resolve(), args.identifier, args.action == 'finish'))
