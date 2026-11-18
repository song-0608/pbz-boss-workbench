"""Stage a frozen inventory query on the idle research game, without sending input."""

import argparse
import hashlib
import json
from pathlib import Path
import time

import boss_metadata_jobs as metadata
from boss_offline_inventory import OUTPUT, QUERY_LABEL, ROOT, exact_payload, exact_requests, inputs, read
from boss_adaptation_workflow import sha, write_json
from collect_boss_metadata_jobs import batch_lines
from mod_installation import unlinked_path
from native_grant_ui_stage import foreground_window
from stage_readonly_contracts import current


def verify(batch, root=ROOT):
    root = root.resolve()
    identity, *_ = inputs(root)
    inventory = hashlib.sha256(metadata.canonical(identity)).hexdigest()[:20]
    batch = unlinked_path(batch)
    for jobs in exact_requests(identity['characters']):
        manifest, script = exact_payload(jobs, inventory)
        expected = root / OUTPUT / inventory / 'exact-grant-metadata' / manifest['fingerprint']
        if batch == expected:
            assert read(batch / 'manifest.json') == manifest, 'inventory job manifest drift'
            assert (batch / 'metadata-probe.lua').read_bytes() == script, 'inventory job script drift'
            return manifest, script
    raise ValueError('Expected a current exact-grant batch from boss_offline_inventory.py')


def location(work, manifest, suffix):
    return work / f"{QUERY_LABEL}-{manifest['fingerprint']}-{suffix}"


def stage(batch):
    manifest, script = verify(batch)
    practice, validation, state, work, carrier, pid = current()
    label = f"{QUERY_LABEL}-{manifest['fingerprint']}"
    assert not list(work.glob(label + '*')), 'preserve previous attempt'
    for intent in work.glob(f'{QUERY_LABEL}-*-intent.json'):
        assert intent.with_name(intent.name.replace('-intent.json', '-results.json')).is_file(), 'previous batch remains open'
    log = practice.log_path(state).read_bytes()
    row, = [row for row in state['ue4ss_loader_manifest'] if row['physical_path'] == str(carrier)]
    receipt = dict(state_file=state['state_file'], research_pid=pid, deadline_unix=state['deadline_unix'],
                   batch=manifest['fingerprint'], script_sha256=manifest['script_sha256'],
                   manifest_sha256=sha(Path(batch) / 'manifest.json'), carrier=str(carrier),
                   log_byte_offset=len(log), log_prefix_sha256=hashlib.sha256(log).hexdigest(),
                   metadata_only=True, input_sent=False)
    # Reserve this attempt before changing the mirror or the tracked loader hash.
    with location(work, manifest, 'intent.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    location(work, manifest, 'before.lua').write_bytes(carrier.read_bytes())
    location(work, manifest, 'metadata.lua').write_bytes(script)
    write_json(location(work, manifest, 'manifest.json'), manifest)
    row['sha256'] = manifest['script_sha256']
    validation.save(validation.state_path(), state)
    carrier.write_bytes(script)
    validation.verify_build(state['ue4ss_loader_manifest'])
    write_json(location(work, manifest, 'staged.json'), receipt)
    return receipt


def snapshot(batch):
    manifest, script = verify(batch)
    practice, validation, state, work, carrier, pid = current()
    staged = read(location(work, manifest, 'staged.json'))
    assert staged == read(location(work, manifest, 'intent.json'))
    assert staged['state_file'] == state['state_file'] and staged['research_pid'] == pid
    assert staged['deadline_unix'] == state['deadline_unix'] and staged['carrier'] == str(carrier)
    assert staged['batch'] == manifest['fingerprint'] and staged['script_sha256'] == manifest['script_sha256']
    assert staged['manifest_sha256'] == sha(Path(batch) / 'manifest.json')
    assert carrier.read_bytes() == script == location(work, manifest, 'metadata.lua').read_bytes()
    assert read(location(work, manifest, 'manifest.json')) == manifest
    raw = practice.log_path(state).read_bytes()
    offset = staged['log_byte_offset']
    assert type(offset) is int and 0 <= offset <= len(raw)
    assert hashlib.sha256(raw[:offset]).hexdigest() == staged['log_prefix_sha256']
    return manifest, validation, state, work, staged, raw[offset:].decode('utf-8', errors='strict')


def reload_gate(batch):
    manifest, validation, state, work, staged, tail = snapshot(batch)
    assert 'PBZ_ADAPTER_META:START=' + manifest['fingerprint'] not in tail, 'batch already started'
    window = foreground_window(validation, staged['research_pid'])
    deadline = time.time() + 10
    assert deadline < state['deadline_unix'] - 120
    gate = dict(window_id=window, research_pid=staged['research_pid'], batch=manifest['fingerprint'],
                state_file=state['state_file'], key='Control_L+r', gate_expires_at=deadline, input_sent=False)
    write_json(location(work, manifest, f'gate-{time.time_ns()}.json'), gate)
    return gate


def capture(batch):
    manifest, _, state, work, staged, tail = snapshot(batch)
    lines = batch_lines(tail, manifest['fingerprint'])
    outcomes = metadata.analyze(lines, dict(jobs=manifest['jobs'], batch_fingerprint=manifest['fingerprint']))
    result = dict(state_file=state['state_file'], research_pid=staged['research_pid'], batch=manifest['fingerprint'],
                  metadata_only=True, playable=False, lines=lines, outcomes=outcomes)
    with location(work, manifest, 'results.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
    return dict(batch=result['batch'], outcomes=len(outcomes), verified=sum(row['metadata_verified'] for row in outcomes),
                metadata_only=True, playable=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('verify', 'stage', 'reload-gate', 'capture'))
    parser.add_argument('batch', type=Path)
    args = parser.parse_args()
    if args.action == 'verify':
        record, _ = verify(args.batch)
        result = dict(batch=record['fingerprint'], requests=len(record['jobs']), metadata_only=True)
    else:
        result = {'stage': stage, 'reload-gate': reload_gate, 'capture': capture}[args.action](args.batch)
    print(json.dumps(result, ensure_ascii=False, indent=2))
