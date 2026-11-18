"""Stage and collect exact native-grant metadata; UI reload is a separate action.

Never starts the game, sends keys, creates Actors, grants skills or promotes a
player profile. Stage on an idle read-only carrier, reload through the ordinary
focus-gated UI workflow, capture, close the research session, then collect.
"""
import argparse
import json
from pathlib import Path
import re
import time

from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from boss_native_grant_followup import verify
from boss_metadata_jobs import analyze
from collect_boss_metadata_jobs import repository_path, batch_lines


def analysis_manifest(manifest):
    return dict(jobs=manifest['jobs'], batch_fingerprint=manifest['fingerprint'])


def idle_guard(owner, state, now):
    assert owner.get('state_file') == state.get('state_file'), 'current owned session required'
    assert owner.get('phase') == 'game_launched' and not state.get('boss_lifecycle_experiment'), 'idle carrier required'
    assert state.get('readonly_ai_experiment') and state.get('ue4ss_deployed'), 'read-only metadata carrier required'
    assert state.get('readonly_hot_reload_enabled'), 'read-only hot reload required at startup'
    assert not state.get('restored') and state.get('offline_validation') and not state.get('network_active')
    assert now < state['deadline_unix'] - 120, 'preserve time to capture and close; never extend lease'


def stem(manifest):
    return manifest['fingerprint'] + '-native-grant-metadata'


def stage(batch):
    import ahua_practice as practice
    import official_validation as validation
    from research_storage import container_path
    from mod_installation import unlinked_path
    manifest = verify(batch)
    owner, state = practice.owned_session()
    idle_guard(owner, state, time.time())
    validation.verify_build(state['ue4ss_loader_manifest'])
    assert validation.c.baseline.formal_files() == state['formal_before'], 'formal file change preserved'
    work = Path(state['work'])
    label = stem(manifest)
    assert not any(work.glob(label + '*')), 'preserve previous metadata attempt'
    rows = [r for r in state['ue4ss_loader_manifest']
            if r['physical_path'].replace('\\', '/').endswith('/PBZObserveAI/Scripts/main.lua')]
    assert len(rows) == 1, 'unique read-only loader required'
    row, = rows
    target = unlinked_path(Path(row['physical_path']))
    assert target.is_relative_to(unlinked_path(container_path())), 'research mirror only'
    original = target.read_bytes()
    assert sha(target) == row['sha256']
    raw = (Path(batch) / 'metadata-probe.lua').read_bytes()
    log = practice.log_path(state)
    offset = len(log.read_bytes())
    # Retain the exact previous script before any loader mutation. No UI input.
    (work / (label + '-before.lua')).write_bytes(original)
    (work / (label + '.lua')).write_bytes(raw)
    row['sha256'] = manifest['script_sha256']
    validation.save(validation.state_path(), state)
    target.write_bytes(raw)
    validation.verify_build(state['ue4ss_loader_manifest'])
    receipt = dict(state_file=str(validation.state_path()), fingerprint=manifest['fingerprint'],
                   batch_manifest_sha256=sha(Path(batch) / 'manifest.json'),
                   script_sha256=manifest['script_sha256'], log_byte_offset=offset,
                   metadata_only=True, ui_input_sent=False)
    write_json(work / (label + '-staged.json'), receipt)
    return dict(staged=True, ui_reload_required=True, metadata_only=True,
                fingerprint=manifest['fingerprint'], playable_bosses_added=0)


def analyze_attempt(raw, manifest):
    lines = batch_lines(raw, manifest['fingerprint'])
    return lines, analyze(lines, analysis_manifest(manifest))


def reload_gate(batch):
    """Issue a ten-second receipt for exactly Ctrl+R; never injects input."""
    import ctypes
    from ctypes import wintypes as w
    import ahua_practice as practice
    import official_validation as validation
    manifest = verify(batch)
    owner, state = practice.owned_session()
    idle_guard(owner, state, time.time())
    work, label = Path(state['work']), stem(manifest)
    staged = json.loads((work / (label + '-staged.json')).read_bytes())
    assert staged['state_file'] == str(validation.state_path())
    assert staged['fingerprint'] == manifest['fingerprint']
    assert staged['batch_manifest_sha256'] == sha(Path(batch) / 'manifest.json')
    assert staged['script_sha256'] == manifest['script_sha256']
    assert not (work / (label + '-results.json')).exists(), 'attempt already captured'
    text = practice.log_path(state).read_text(encoding='utf-8', errors='strict')
    assert 'PBZ_ADAPTER_META:START=' + manifest['fingerprint'] not in text, 'never replay a started metadata attempt'
    c = validation.c
    c.isolation.select_box('PBZSteamLab'); dll = c.isolation.api()
    c.isolation.check_policy(dll, allow_offline_validation=True)
    assert not c.host_steam_pids(dll), 'preserve host Steam'
    assert c.baseline.formal_files() == state['formal_before']
    validation.verify_build(state['ue4ss_loader_manifest'])
    pids = {p['ProcessId'] for p in c.box_processes(dll) if p['Name'].lower() == 'pbz.exe'}
    assert pids, 'owned research process required'
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetForegroundWindow.restype = w.HWND
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    user.IsWindowVisible.argtypes = [w.HWND]
    callback = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes = [callback, w.LPARAM]
    windows = []
    @callback
    def inspect(handle, _):
        pid = w.DWORD(); user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        if pid.value in pids and user.IsWindowVisible(handle):
            name = ctypes.create_unicode_buffer(256); user.GetClassNameW(handle, name, len(name))
            if name.value == 'Sandbox:PBZSteamLab:UnrealWindow': windows.append(int(handle))
        return True
    assert user.EnumWindows(inspect, 0)
    foreground = int(user.GetForegroundWindow() or 0)
    assert len(windows) == 1 and windows[0] == foreground, 'unique foreground research render window required'
    record = dict(fingerprint=manifest['fingerprint'], state_file=state['state_file'],
                  window_id=foreground, key='Control_L+r', gate_expires_at=time.time()+10,
                  input_sent=False, metadata_only=True)
    write_json(work / (label + '-gate-' + str(time.time_ns()) + '.json'), record)
    return record


def capture(batch):
    import ahua_practice as practice
    import official_validation as validation
    manifest = verify(batch)
    owner, state = practice.owned_session()
    idle_guard(owner, state, time.time())
    validation.verify_build(state['ue4ss_loader_manifest'])
    assert validation.c.baseline.formal_files() == state['formal_before'], 'formal file change preserved'
    work, label = Path(state['work']), stem(manifest)
    staged = json.loads((work / (label + '-staged.json')).read_bytes())
    assert staged['state_file'] == str(validation.state_path())
    assert staged['fingerprint'] == manifest['fingerprint']
    assert staged['batch_manifest_sha256'] == sha(Path(batch) / 'manifest.json')
    assert staged['script_sha256'] == manifest['script_sha256']
    assert staged['metadata_only'] is True and staged['ui_input_sent'] is False
    assert sha(work / (label + '.lua')) == manifest['script_sha256']
    raw = practice.log_path(state).read_bytes()
    offset = staged['log_byte_offset']
    assert type(offset) is int and 0 <= offset <= len(raw)
    lines, outcomes = analyze_attempt(raw[offset:].decode('utf-8', errors='strict'), manifest)
    target = work / (label + '-results.json')
    assert not target.exists(), 'preserve previous capture'
    result = dict(state_file=str(validation.state_path()), fingerprint=manifest['fingerprint'],
                  script_sha256=manifest['script_sha256'],
                  batch_manifest_sha256=staged['batch_manifest_sha256'], lines=lines,
                  all_metadata_requests_passed=all(r['metadata_verified'] for r in outcomes),
                  metadata_only=True, boss_control_verified=False)
    write_json(target, result)
    return result


def closed_evidence(session, batch, root=ROOT):
    root, batch = Path(root).resolve(), Path(batch).resolve()
    assert re.fullmatch(r'\d{8}-\d{6}', session), 'exact closed session identifier required'
    manifest = verify(batch, root)
    state_path = repository_path(root, 'runtime/official-validation-' + session + '/state.json')
    work = repository_path(root, 'evidence/official-validation/' + session)
    state = json.loads(state_path.read_bytes())
    assert state['restored'] is True and Path(state['work']).resolve() == work
    post_path = work / 'postcheck.json'
    post = json.loads(post_path.read_bytes())
    assert post['validation_state'] == str(state_path)
    for key in ('research_box_empty', 'research_loader_removed', 'host_registry_unchanged'):
        assert post[key] is True, key
    assert not post['formal_files_changed'] and not post['host_config_files_changed']
    label = stem(manifest)
    staged_path, action_path = (work / (label + suffix) for suffix in ('-staged.json', '-results.json'))
    staged, action = (json.loads(p.read_bytes()) for p in (staged_path, action_path))
    for row in (staged, action):
        assert row['state_file'] == str(state_path) and row['fingerprint'] == manifest['fingerprint']
        assert row['batch_manifest_sha256'] == sha(batch / 'manifest.json')
        assert row['script_sha256'] == manifest['script_sha256'] and row['metadata_only'] is True
    assert staged['ui_input_sent'] is False and action['boss_control_verified'] is False
    script = work / (label + '.lua')
    assert sha(script) == manifest['script_sha256']
    log = work / 'UE4SS.log'
    raw = log.read_bytes()
    offset = staged['log_byte_offset']
    assert type(offset) is int and 0 <= offset <= len(raw)
    lines, outcomes = analyze_attempt(raw[offset:].decode('utf-8', errors='strict'), manifest)
    # Also inspect the full log to reject a duplicate attempt before staging.
    full_lines, _ = analyze_attempt(raw.decode('utf-8', errors='strict'), manifest)
    assert lines == full_lines == action['lines'], 'retain every exact raw attempt line'
    assert action['all_metadata_requests_passed'] is all(r['metadata_verified'] for r in outcomes)
    sources = [state_path, post_path, staged_path, action_path, script, log,
               batch / 'manifest.json', batch / 'metadata-probe.lua']
    assert all(p.resolve().is_relative_to(root) for p in sources)
    return dict(schema=1, kind='native_grant_metadata_receipt', session=session,
                fingerprint=manifest['fingerprint'], target_build_sha256=BUILD,
                batch_directory=batch.relative_to(root).as_posix(),
                metadata_only=True, playable=False, control_verified=False,
                runtime_acceptance_current=False, outcomes=outcomes,
                sources={p.relative_to(root).as_posix(): sha(p) for p in sources})


def collect(session, batch, root=ROOT):
    root = Path(root).resolve()
    receipt = closed_evidence(session, batch, root)
    target = root / 'research/boss-adaptation/native-grant-metadata-receipts' / (session + '-' + receipt['fingerprint'] + '.json')
    if target.exists():
        assert json.loads(target.read_bytes()) == receipt, 'preserve closed receipt'
    else:
        write_json(target, receipt)
    return target


def verify_receipt(target, root=ROOT):
    root, target = Path(root).resolve(), Path(target).resolve()
    receipt = json.loads(target.read_bytes())
    assert receipt['schema'] == 1 and receipt['kind'] == 'native_grant_metadata_receipt'
    expected_path = root / 'research/boss-adaptation/native-grant-metadata-receipts' / (receipt['session'] + '-' + receipt['fingerprint'] + '.json')
    assert target == expected_path, 'canonical receipt location required'
    batch = repository_path(root, receipt['batch_directory'])
    assert receipt == closed_evidence(receipt['session'], batch, root), 'closed receipt drift'
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('stage', 'reload-gate', 'capture'):
        sub.add_parser(name).add_argument('batch', type=Path)
    close = sub.add_parser('collect')
    close.add_argument('session'); close.add_argument('batch', type=Path)
    sub.add_parser('verify').add_argument('receipt', type=Path)
    args = parser.parse_args()
    if args.action == 'stage': result = stage(args.batch)
    elif args.action == 'reload-gate': result = reload_gate(args.batch)
    elif args.action == 'capture': result = capture(args.batch)
    elif args.action == 'collect': result = dict(receipt=str(collect(args.session, args.batch)), playable_bosses_added=0)
    else:
        record = verify_receipt(args.receipt)
        result = dict(verified=True, fingerprint=record['fingerprint'], playable_bosses_added=0)
    print(json.dumps(result, ensure_ascii=False, indent=2))
