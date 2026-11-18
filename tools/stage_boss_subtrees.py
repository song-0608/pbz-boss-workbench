"""Stage/capture subtree metadata without launching a game or sending input."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

import boss_subtree_inventory as subtrees
from boss_adaptation_workflow import ROOT, sha, write_json
from boss_offline_inventory import read, closed
from mod_installation import unlinked_path
from native_grant_ui_stage import foreground_window
from stage_readonly_contracts import current

LABEL = 'boss-subtree-query'


def location(work, manifest, suffix):
    return work / (LABEL + '-' + manifest['fingerprint'] + '-' + suffix)


def lines_for(raw, fingerprint):
    # This probe owns a different prefix from metadata, controls and prior tree probes.
    # Keep every event: the parser rejects repeats, interleaving and trailing events.
    lines = [line for line in raw.splitlines() if subtrees.PREFIX in line]
    assert sum(subtrees.PREFIX + 'START=' + fingerprint in line for line in lines) == 1
    return lines


def archive_sources(manifest, work, *, create=False, root=None):
    """Bind the exact original sources to this session before live deployment."""
    root = ROOT if root is None else root
    snapshot = work / 'subtree-source-snapshot'
    for name, digest in manifest['source_sha256'].items():
        assert name in subtrees.SOURCES, 'unrecognized subtree source'
        target = unlinked_path(snapshot / name)
        if create:
            source = unlinked_path(root / name)
            raw = source.read_bytes()
            assert hashlib.sha256(raw).hexdigest() == digest, 'source changed before subtree staging'
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as handle:
                handle.write(raw)
        assert sha(target) == digest, 'archived subtree source changed'


def stage(batch):
    manifest, script = subtrees.verify(batch)
    assert manifest['jobs'], 'do not deploy an empty subtree query'
    assert len(manifest['jobs']) <= 64, 'stage a bounded continuation, not the complete parent inventory'
    practice, validation, state, work, carrier, pid = current()
    assert not list(work.glob(LABEL + '*')), 'preserve the session subtree attempt'
    assert time.time() + manifest['max_seconds'] + 120 < state['deadline_unix'], 'reserve query and cleanup time'
    raw = practice.log_path(state).read_bytes()
    receipt = dict(state_file=state['state_file'], research_pid=pid, deadline_unix=state['deadline_unix'],
        batch=manifest['fingerprint'], manifest_sha256=sha(Path(batch) / 'manifest.json'),
        script_sha256=manifest['script_sha256'], carrier=str(carrier), log_byte_offset=len(raw),
        log_prefix_sha256=hashlib.sha256(raw).hexdigest(), metadata_only=True, ui_input_sent=False)
    with location(work, manifest, 'intent.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    archive_sources(manifest, work, create=True)
    location(work, manifest, 'before.lua').write_bytes(carrier.read_bytes())
    location(work, manifest, 'probe.lua').write_bytes(script)
    write_json(location(work, manifest, 'manifest.json'), manifest)
    row, = [r for r in state['ue4ss_loader_manifest'] if r['physical_path'] == str(carrier)]
    row['sha256'] = receipt['script_sha256']
    validation.save(validation.state_path(), state)
    carrier.write_bytes(script)
    validation.verify_build(state['ue4ss_loader_manifest'])
    write_json(location(work, manifest, 'staged.json'), receipt)
    return receipt


def snapshot(batch):
    manifest, script = subtrees.verify(batch)
    practice, validation, state, work, carrier, pid = current()
    receipt = read(location(work, manifest, 'staged.json'))
    assert receipt == read(location(work, manifest, 'intent.json'))
    assert receipt['state_file'] == state['state_file'] and receipt['research_pid'] == pid
    assert receipt['deadline_unix'] == state['deadline_unix'] and receipt['carrier'] == str(carrier)
    assert receipt['batch'] == manifest['fingerprint'] and receipt['script_sha256'] == manifest['script_sha256']
    assert receipt['manifest_sha256'] == sha(Path(batch) / 'manifest.json')
    archive_sources(manifest, work)
    assert read(location(work, manifest, 'manifest.json')) == manifest
    assert carrier.read_bytes() == location(work, manifest, 'probe.lua').read_bytes() == script
    raw = practice.log_path(state).read_bytes(); offset = receipt['log_byte_offset']
    assert type(offset) is int and 0 <= offset <= len(raw)
    assert hashlib.sha256(raw[:offset]).hexdigest() == receipt['log_prefix_sha256']
    return manifest, validation, state, work, receipt, raw[offset:].decode('utf-8', errors='strict')


def reload_gate(batch):
    manifest, validation, state, work, receipt, tail = snapshot(batch)
    assert subtrees.PREFIX not in tail, 'subtree query already started'
    assert time.time() + manifest['max_seconds'] + 120 < state['deadline_unix']
    hwnd = foreground_window(validation, receipt['research_pid'])
    now = time.time()
    assert now + manifest['max_seconds'] + 120 < state['deadline_unix']
    gate = dict(window_id=hwnd, research_pid=receipt['research_pid'], batch=manifest['fingerprint'],
        state_file=state['state_file'], key='Control_L+r', gate_expires_at=now + 10,
        input_sent=False, metadata_only=True, staged_sha256=sha(location(work, manifest, 'staged.json')))
    write_json(location(work, manifest, 'gate-' + str(time.time_ns()) + '.json'), gate)
    return gate


def capture(batch):
    manifest, _, state, work, receipt, tail = snapshot(batch)
    lines = lines_for(tail, manifest['fingerprint'])
    outcomes = subtrees.analyze(lines, manifest)
    result = dict(state_file=state['state_file'], research_pid=receipt['research_pid'],
        batch=manifest['fingerprint'], script_sha256=manifest['script_sha256'],
        metadata_only=True, playable=False, execution_order_proven=False, lines=lines, outcomes=outcomes)
    with location(work, manifest, 'capture.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    return dict(queries=len(outcomes), mappings=sum(r['mapping_observed'] for r in outcomes),
                metadata_only=True, playable=False)


def collect(batch, session, root=ROOT):
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    manifest, script = subtrees.verify(batch, root)
    state_path = unlinked_path(root / ('runtime/official-validation-' + session + '/state.json'))
    work = unlinked_path(root / ('evidence/official-validation/' + session))
    post_path = unlinked_path(work / 'postcheck.json')
    assert closed(state_path, post_path, work), 'cleanly closed research session required'
    receipt = read(location(work, manifest, 'staged.json'))
    assert receipt == read(location(work, manifest, 'intent.json'))
    assert receipt['state_file'] == str(state_path) and receipt['batch'] == manifest['fingerprint']
    assert receipt['metadata_only'] is True and receipt['ui_input_sent'] is False
    assert receipt['manifest_sha256'] == sha(Path(batch) / 'manifest.json')
    assert receipt['script_sha256'] == manifest['script_sha256']
    archive_sources(manifest, work, root=root)
    assert read(location(work, manifest, 'manifest.json')) == manifest
    archived = unlinked_path(location(work, manifest, 'probe.lua'))
    assert archived.read_bytes() == script
    log = unlinked_path(work / 'UE4SS.log'); raw = log.read_bytes(); offset = receipt['log_byte_offset']
    assert type(offset) is int and 0 <= offset <= len(raw)
    assert hashlib.sha256(raw[:offset]).hexdigest() == receipt['log_prefix_sha256']
    lines = lines_for(raw[offset:].decode('utf-8', errors='strict'), manifest['fingerprint'])
    outcomes = subtrees.analyze(lines, manifest)
    captured = read(location(work, manifest, 'capture.json'))
    assert captured == dict(state_file=str(state_path), research_pid=receipt['research_pid'],
        batch=manifest['fingerprint'], script_sha256=manifest['script_sha256'],
        metadata_only=True, playable=False, execution_order_proven=False, lines=lines, outcomes=outcomes)
    paths = (state_path, post_path, log, archived, Path(batch) / 'manifest.json',
             location(work, manifest, 'intent.json'), location(work, manifest, 'staged.json'),
             location(work, manifest, 'capture.json'))
    report = dict(schema=1, session=session, batch=manifest['fingerprint'], outcomes=outcomes,
        metadata_only=True, playable=False, execution_order_proven=False, native_grant_verified=False,
        runtime_acceptance_current=False, sources={p.relative_to(root).as_posix(): sha(p) for p in paths})
    target = root / 'research/boss-adaptation/subtree-receipts' / (session + '-' + manifest['fingerprint'] + '.json')
    if target.exists():
        assert read(target) == report, 'preserve prior subtree receipt'
    else:
        write_json(target, report)
    return dict(receipt=str(target), queries=len(outcomes), mappings=sum(r['mapping_observed'] for r in outcomes),
                playable=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('verify', 'stage', 'reload-gate', 'capture', 'collect'))
    parser.add_argument('batch', type=Path)
    parser.add_argument('--session')
    args = parser.parse_args()
    if args.action == 'verify':
        manifest, _ = subtrees.verify(args.batch)
        result = dict(queries=len(manifest['jobs']), metadata_only=True, playable=False)
    elif args.action == 'collect':
        assert args.session
        result = collect(args.batch, args.session)
    else:
        assert args.session is None
        result = {'stage': stage, 'reload-gate': reload_gate, 'capture': capture}[args.action](args.batch)
    print(json.dumps(result, ensure_ascii=False, indent=2))
