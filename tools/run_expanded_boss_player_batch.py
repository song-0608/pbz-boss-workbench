"""One ordinary workbench batch for exact independently accepted expansion profiles."""
import argparse
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from boss_adaptation_workflow import ROOT, sha, write_json
import expanded_boss_integration_workflow as workflow
import build_expanded_boss_candidate as candidate


def main(flow):
    frozen = workflow.verify(flow)
    package = Path(frozen['candidate']); manifest = candidate.verify(package)
    sys.path.insert(0, str(flow))
    practice = importlib.import_module('ahua_practice')
    dispatch = importlib.import_module('test_player_experience_inputs').main
    wait_for = importlib.import_module('test_player_skill_batch').wait_for
    from control_action_evidence import restoration_result
    from collect_skill_acceptance import analyze
    from player_target_readiness import target_cycle_verified
    owner, state = practice.owned_session()
    assert owner['phase'] == 'armed' and owner.get('player_entry') and owner.get('workbench')
    assert min(state['deadline_unix'], state['control_probe_expires_at']) - time.time() > 600
    path = practice.log_path(state); work = Path(state['work'])
    target = work / 'expanded-boss-player-batch.json'
    assert not target.exists(), 'Preserve each native acceptance attempt'
    order = [row['id'] for row in manifest['bosses']]
    additions = manifest['expansion_profiles']
    report = dict(schema=1, state_file=state['state_file'], workflow=str(flow),
        candidate=str(package), candidate_manifest_sha256=sha(package / 'pbz-release.json'),
        log_offset=len(path.read_text(encoding='utf-8', errors='replace')), roles=[], passed=False)
    def raw(): return path.read_text(encoding='utf-8', errors='replace')
    def save():
        text = raw(); report.update(log_end=len(text), lines=text[report['log_offset']:].splitlines())
        write_json(target, report)
    def send(action):
        start = len(raw()); dispatch(flow, action); return start
    def wait(start, predicate, seconds=12):
        tail = wait_for(path, start, predicate, seconds, True)
        assert predicate(tail), 'Native result missing after real input'
        return tail
    def select(identifier):
        current = re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)', raw())[-1]
        assert current in order and identifier in order
        if current == identifier: return
        start = send('workbench'); wait(start, lambda t: 'WORKBENCH_INPUT_LOCKED=' in t)
        delta = order.index(identifier) - order.index(current)
        action = 'down' if delta > 0 else 'up'
        for _ in range(abs(delta)):
            start = send(action); wait(start, lambda t: 'workbench_' + action + ' success=true' in t)
        start = send('confirm')
        wait(start, lambda t: ('WORKBENCH_BOSS_SELECTED=' + identifier) in t
             and ('PLAYER_ENTRY_READY=' + identifier) in t and 'WORKBENCH_INPUT_RESTORED=true' in t, 70)
    try:
        save()
        for addition in additions:
            identifier = addition['id']; select(identifier)
            role = dict(id=identifier, log_offset=len(raw()), passed=False)
            report['roles'].append(role); save()
            start = send('enter')
            wait(start, lambda t: 'enter success=true state=ACTIVE' in t and 'TARGET_CAMERA_LOCK=true|initial' in t)
            start = send('shift_cast')
            natural = wait(start, lambda t: bool(analyze(t, 'skill_01')['natural_completion']), 45)
            assert '[PBZBossControl] slot1 success=true state=ACTIVE' in natural
            role['shift_primary'] = analyze(natural, 'skill_01')['natural_completion']
            start = send('lock'); wait(start, lambda t: 'TARGET_CAMERA_LOCK=false|' in t)
            start = send('lock'); wait(start, lambda t: 'TARGET_CAMERA_LOCK=true|' in t)
            start = send('cycle_target'); wait(start, target_cycle_verified)
            start = send('exit'); wait(start, lambda t: restoration_result(t, 'exit')['passed'])
            skills = addition['skills']
            for interrupt in (False, True):
                requested = skills if interrupt else [skill for skill in skills if skill != 'skill_01']
                if not requested: continue
                command = [sys.executable, '-B', '-X', 'utf8', str(flow / 'test_player_skill_batch.py'), *requested]
                if interrupt: command.append('--interrupt')
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                    encoding='utf-8', errors='replace', timeout=260, creationflags=subprocess.CREATE_NO_WINDOW)
                print(result.stdout, flush=True)
                assert result.returncode == 0, result.stderr or result.stdout
            role.update(log_end=len(raw()), passed=True); save()
            print(identifier + ': ordinary selection, Shift casting, target lock and cancellation PASS', flush=True)
        select('ahua_guitoudao')
        report.update(returned_to_ahua=True, passed=True)
        return 0
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        text = raw(); last = text.rfind('[PBZBossControl] enter success=true state=ACTIVE')
        if last >= report['log_offset'] and not restoration_result(text[last:])['passed']:
            try:
                start = send('exit'); wait(start, lambda t: restoration_result(t, 'exit')['passed'])
            except Exception as cleanup: report['cleanup_error'] = str(cleanup)
        return 1
    finally:
        save(); print(json.dumps({k:v for k,v in report.items() if k != 'lines'}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('workflow', type=Path)
    args = parser.parse_args(); raise SystemExit(main(args.workflow.resolve()))
