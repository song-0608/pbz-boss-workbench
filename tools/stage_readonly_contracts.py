"""Stage existing read-only camera/combat queries; reload only through window API."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from boss_adaptation_workflow import ROOT, sha, write_json
from mod_installation import active_mod_root, unlinked_path
import native_grant_ui_stage as controls

LABEL = 'native-readonly-contracts'
SCRIPTS = ('camera_contract.lua', 'combat_contract.lua')
TOKENS = ('PBZ_CAMERA_CONTRACT:PASS=', 'PBZ_COMBAT_CONTRACT:PASS=')


def payload():
    root = active_mod_root()
    paths = [unlinked_path(root / 'Experiments' / name) for name in SCRIPTS]
    return b'\n'.join(p.read_bytes() for p in paths), {str(p): sha(p) for p in paths}


def current():
    import ahua_practice as practice
    import official_validation as validation
    from research_storage import container_path
    owner, state = practice.owned_session()
    controls.idle_guard(owner, state, time.time())
    target = controls.mirror_guard(state, container_path())
    pid = controls.research_pid(validation)
    validation.verify_build(state['ue4ss_loader_manifest'])
    assert validation.c.baseline.formal_files() == state['formal_before']
    work = unlinked_path(Path(state['work']))
    assert work == unlinked_path(ROOT / 'evidence/official-validation' / work.name)
    return practice, validation, state, work, target, pid


def stage():
    practice, validation, state, work, target, pid = current()
    assert not list(work.glob(LABEL + '*')), 'preserve previous attempt'
    raw, sources = payload()
    log = practice.log_path(state).read_bytes()
    receipt = dict(state_file=state['state_file'], research_pid=pid, deadline_unix=state['deadline_unix'],
        script_sha256=hashlib.sha256(raw).hexdigest(), sources=sources, carrier=str(target),
        log_byte_offset=len(log), log_prefix_sha256=hashlib.sha256(log).hexdigest(),
        metadata_only=True, ui_input_sent=False, playable=False)
    (work / (LABEL + '-before.lua')).write_bytes(target.read_bytes())
    (work / (LABEL + '.lua')).write_bytes(raw)
    write_json(work / (LABEL + '-intent.json'), receipt)
    row, = [r for r in state['ue4ss_loader_manifest'] if r['physical_path'] == str(target)]
    row['sha256'] = receipt['script_sha256']
    validation.save(validation.state_path(), state)
    target.write_bytes(raw)
    validation.verify_build(state['ue4ss_loader_manifest'])
    write_json(work / (LABEL + '-staged.json'), receipt)
    return dict(staged=True, metadata_only=True, ui_input_sent=False, research_pid=pid)


def snapshot():
    practice, validation, state, work, target, pid = current()
    receipt = json.loads((work / (LABEL + '-staged.json')).read_bytes())
    assert receipt == json.loads((work / (LABEL + '-intent.json')).read_bytes())
    assert receipt['state_file'] == state['state_file'] and receipt['research_pid'] == pid
    assert receipt['deadline_unix'] == state['deadline_unix']
    assert receipt['metadata_only'] is True and receipt['ui_input_sent'] is False and receipt['playable'] is False
    raw, sources = payload()
    assert receipt['sources'] == sources and hashlib.sha256(raw).hexdigest() == receipt['script_sha256']
    assert target.read_bytes() == (work / (LABEL + '.lua')).read_bytes() == raw
    assert receipt['carrier'] == str(target)
    log = practice.log_path(state).read_bytes(); offset = receipt['log_byte_offset']
    assert type(offset) is int and 0 <= offset <= len(log)
    assert hashlib.sha256(log[:offset]).hexdigest() == receipt['log_prefix_sha256']
    return validation, state, work, receipt, log[offset:].decode('utf-8', errors='strict')


def reload_gate():
    validation, state, work, receipt, tail = snapshot()
    assert not any(token in tail for token in ('PBZ_CAMERA_CONTRACT:', 'PBZ_COMBAT_CONTRACT:'))
    hwnd = controls.foreground_window(validation, receipt['research_pid'])
    now = time.time(); assert now + 10 < state['deadline_unix'] - 120
    result = dict(window_id=hwnd, research_pid=receipt['research_pid'], key='Control_L+r',
        gate_expires_at=now + 10, state_file=state['state_file'], input_sent=False, metadata_only=True,
        staged_receipt_sha256=sha(work / (LABEL + '-staged.json')))
    write_json(work / (LABEL + '-gate-' + str(time.time_ns()) + '.json'), result)
    return result


def analyze(tail):
    assert all(tail.count(token) == 1 for token in TOKENS), 'one complete read-only query required'
    assert not any(token in tail for token in ('PBZ_CONTROL_LIFECYCLE:', 'PBZ_CAMERA_CONTRACT:ISSUE=',
                                              'PBZ_COMBAT_CONTRACT:ISSUE='))
    return dict(query_completed=True, metadata_only=True, playable=False, lines=tail.splitlines())


def capture():
    _, state, work, receipt, tail = snapshot()
    result = dict(analyze(tail), state_file=state['state_file'], research_pid=receipt['research_pid'],
                  script_sha256=receipt['script_sha256'])
    path = work / (LABEL + '-capture.json'); assert not path.exists(), 'preserve previous capture'
    write_json(path, result)
    return dict(query_completed=True, metadata_only=True, research_pid=receipt['research_pid'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('stage', 'reload-gate', 'capture')); args = parser.parse_args()
    result = {'stage': stage, 'reload-gate': reload_gate, 'capture': capture}[args.action]()
    print(json.dumps(result, ensure_ascii=False, indent=2))
