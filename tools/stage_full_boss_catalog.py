"""Run one frozen sequential metadata collector through separately gated UI reload."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import time

import boss_metadata_jobs as metadata
from boss_adaptation_workflow import ROOT, sha, write_json
from boss_offline_inventory import read
from collect_boss_metadata_jobs import batch_lines, collect as collect_batch, repository_path
from mod_installation import unlinked_path
from prepare_full_boss_catalog import collector, inputs, select
import stage_boss_inventory_metadata as core


LABEL = 'boss-full-catalog'


def verify(directory, current=True):
    directory = unlinked_path(directory)
    report = read(directory / 'queue.json')
    identity = {key: report[key] for key in ('schema', 'build', 'inventory_sha256', 'source_sha256', 'probe_sha256', 'jobs')}
    if current:
        inventory, catalog, *_ = inputs(ROOT)
        batches, counts = select(catalog, inventory)
        assert report['inventory_sha256'] == hashlib.sha256(metadata.canonical(inventory)).hexdigest()
        assert report['jobs'] == [[job['key'] for job in batch] for batch in batches] and report['counts'] == counts
    assert report['source_sha256'] == sha(ROOT / 'tools/prepare_full_boss_catalog.py')
    assert report['probe_sha256'] == sha(ROOT / 'tools/full_boss_catalog_probe.lua')
    key = hashlib.sha256(metadata.canonical(identity)).hexdigest()[:20]
    assert report['fingerprint'] == key and directory == ROOT / 'runtime/full-boss-catalog' / key
    raw = collector(report)
    assert raw == (directory / 'metadata-collector.lua').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == report['collector_sha256'] and report['budget_seconds'] == 480
    assert read(directory / 'manifest.json') == dict(report, script_sha256=report['collector_sha256'])
    assert len(report['batches']) == len(report['jobs'])
    for row, keys in zip(report['batches'], report['jobs']):
        manifest = metadata.verify_batch(ROOT / row['directory'])
        assert [job['key'] for job in manifest['jobs']] == keys
    return dict(report, script_sha256=report['collector_sha256']), raw


def use_controller():
    # This process uses a separate label and verifier while retaining all mirror,
    # idle-session, source, lease and input separation checks in the shared core.
    core.verify = verify
    core.QUERY_LABEL = LABEL


def stage(directory):
    report, _ = verify(directory)
    assert report['batches'], 'nothing to query; do not stage an empty catalog'
    _, _, state, *_ = core.current()
    assert time.time() + report['budget_seconds'] < state['deadline_unix'] - 120, 'preserve full query and cleanup time'
    return core.stage(directory)


def reload_gate(directory):
    report, validation, state, work, staged, tail = core.snapshot(directory)
    assert f"PBZ_FULL_CATALOG:START={report['fingerprint']}" not in tail
    assert time.time() + report['budget_seconds'] < state['deadline_unix'] - 120
    hwnd = core.foreground_window(validation, staged['research_pid'])
    result = dict(window_id=hwnd, research_pid=staged['research_pid'], state_file=state['state_file'],
                  key='Control_L+r', input_sent=False, gate_expires_at=time.time()+10)
    write_json(core.location(work, report, f'gate-{time.time_ns()}.json'), result)
    return result


def progress(raw, report):
    """Replay serial execution and retain only complete child batches.

    An outer timeout does not invalidate earlier completed batches. It also
    cannot turn a half-read batch, an orphan outcome or a second execution into
    evidence. Capturing a live attempt still requires an outer terminal event.
    """
    manifests = [metadata.verify_batch(ROOT / row['directory']) for row in report['batches']]
    expected = [manifest['batch_fingerprint'] for manifest in manifests]
    assert len(expected) == len(set(expected)), 'duplicate child batch in full queue'
    owned_jobs = {job['key'] for manifest in manifests for job in manifest['jobs']}
    state, active, halted = 'unstarted', None, False
    later_batch = None
    complete, started = [], []
    event_pattern = re.compile(r'PBZ_(FULL_CATALOG|ADAPTER_META):([A-Z_]+)=(.*)$')
    for line in raw.splitlines():
        match = event_pattern.search(line)
        if not match:
            continue
        owner, event, payload = match.groups()
        payload = payload.strip()
        if state in ('complete', 'stopped'):
            # Other independently staged metadata queries may follow this one
            # before shutdown. They cannot repeat this queue or add late results
            # to either its complete or its unfinished child batches.
            assert owner == 'ADAPTER_META', 'repeated collector after terminal event'
            if event == 'START':
                assert later_batch is None and payload not in expected, 'repeated or interleaved later batch'
                later_batch = payload
            elif event == 'END':
                assert later_batch == payload, 'orphan later batch end'
                later_batch = None
            elif event == 'STOP':
                assert later_batch is not None, 'orphan later batch stop'
                later_batch = None
            elif event in ('OUTCOME', 'REJECTED'):
                assert later_batch is not None, 'orphan result after collector terminal event'
                assert payload.split('|', 1)[0] not in owned_jobs, 'late result for original collector'
            else:
                raise AssertionError('unexpected later child event: ' + event)
            continue
        if owner == 'FULL_CATALOG':
            if event == 'START':
                assert state == 'unstarted' and payload == report['fingerprint'], 'repeated or foreign collector start'
                state = 'active'
            elif event == 'END':
                assert (state == 'active' and active is None and not halted and complete == expected
                        and payload == report['fingerprint']), 'incomplete or repeated collector end'
                state = 'complete'
            elif event == 'STOP':
                assert state == 'active', 'collector stopped outside active attempt'
                state = 'stopped'
            else:
                raise AssertionError('unexpected collector event: ' + event)
            continue
        assert state == 'active', 'child event outside active collector'
        if event == 'START':
            assert (active is None and not halted and len(complete) < len(expected)
                    and payload == expected[len(complete)]), 'repeated, foreign or out-of-order child batch'
            active = payload
            started.append(payload)
        elif event == 'END':
            assert active == payload and not halted, 'orphan or stopped child completion'
            complete.append(payload)
            active = None
        elif event == 'STOP':
            assert active is not None and not halted, 'orphan or duplicate child stop'
            halted = True
        elif event in ('OUTCOME', 'REJECTED'):
            assert active is not None and not halted, 'orphan child metadata result'
        else:
            raise AssertionError('unexpected child event: ' + event)
    assert state != 'unstarted', 'collector start required'
    outcomes = []
    for manifest in manifests[:len(complete)]:
        lines = batch_lines(raw, manifest['batch_fingerprint'])
        outcomes.extend(metadata.analyze(lines, manifest))
    return dict(outcomes=outcomes, completed_batch_keys=complete, started_batch_keys=started,
                pending_batch_keys=expected[len(complete):], complete=state == 'complete',
                terminal=state in ('complete', 'stopped'))


def analyze(raw, report):
    result = progress(raw, report)
    assert result['complete'], 'complete collector required'
    return result['outcomes']


def capture(directory):
    report, _, state, work, staged, raw = core.snapshot(directory)
    observed = progress(raw, report)
    assert observed['terminal'], 'collector still running; preserve capture until END or STOP'
    result = dict(state_file=state['state_file'], research_pid=staged['research_pid'],
                  fingerprint=report['fingerprint'], **observed, lines=raw.splitlines(),
                  metadata_only=True, playable=False)
    with core.location(work, report, 'results.json').open('x', encoding='utf-8') as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    record_children(report, state, work, raw, observed['completed_batch_keys'])
    return dict(requests=len(observed['outcomes']), complete=observed['complete'],
                pending_batches=len(observed['pending_batch_keys']), metadata_only=True, playable=False)


def record_children(report, state, work, raw, completed=None):
    """Retain every child source and result for the existing closed collector."""
    for row in report['batches']:
        batch = ROOT / row['directory']
        manifest = metadata.verify_batch(batch)
        fingerprint = manifest['batch_fingerprint']
        if completed is not None and fingerprint not in completed:
            continue
        stem = fingerprint + '-adapter-metadata'
        lines = batch_lines(raw, fingerprint)
        outcomes = metadata.analyze(lines, manifest)
        result = dict(state_file=state['state_file'], metadata_only=True, boss_control_verified=False,
                      metadata_kind='adapter_metadata_jobs', batch_fingerprint=fingerprint,
                      script_sha256=manifest['script_sha256'],
                      batch_manifest_sha256=sha(batch / 'metadata-probe-manifest.json'), lines=lines,
                      all_metadata_requests_passed=all(row['metadata_verified'] for row in outcomes))
        script = work / (stem + '.lua')
        with script.open('xb') as file:
            file.write((batch / 'metadata-probe.lua').read_bytes())
        with (work / (stem + '-results.json')).open('x', encoding='utf-8') as file:
            json.dump(result, file, ensure_ascii=False, indent=2)


def collect(directory, session):
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    directory = unlinked_path(directory)
    # The sources used for this query must still match. Collection is not an
    # excuse to regenerate the queue from later receipts.
    report, script = verify(directory, current=False)
    work = repository_path(ROOT, 'evidence/official-validation/' + session)
    state_file = repository_path(ROOT, 'runtime/official-validation-' + session + '/state.json')
    state = read(state_file)
    assert state['restored'] is True and Path(state['work']).resolve() == work
    post = read(work / 'postcheck.json')
    assert post['validation_state'] == str(state_file)
    for key in ('research_box_empty', 'research_loader_removed', 'host_registry_unchanged'):
        assert post[key] is True, key
    assert not post['formal_files_changed'] and not post['host_config_files_changed']
    stage = read(core.location(work, report, 'staged.json'))
    assert stage == read(core.location(work, report, 'intent.json'))
    assert stage['state_file'] == str(state_file) and stage['script_sha256'] == report['script_sha256']
    assert stage['batch'] == report['fingerprint'] and stage['metadata_only'] is True and stage['input_sent'] is False
    assert stage['manifest_sha256'] == sha(directory / 'manifest.json')
    assert read(core.location(work, report, 'manifest.json')) == report
    assert core.location(work, report, 'metadata.lua').read_bytes() == script
    raw = (work / 'UE4SS.log').read_bytes()
    offset = stage['log_byte_offset']
    assert type(offset) is int and 0 <= offset <= len(raw)
    assert hashlib.sha256(raw[:offset]).hexdigest() == stage['log_prefix_sha256']
    tail = raw[offset:].decode('utf-8')
    result = read(core.location(work, report, 'results.json'))
    assert result['fingerprint'] == report['fingerprint'], 'capture belongs to another collector'
    if 'completed_batch_keys' in result:
        observed = progress(tail, report)
        assert observed['terminal']
        assert all(result[key] == value for key, value in observed.items()), 'collector progress changed after capture'
        completed = observed['completed_batch_keys']
    else:
        assert result['outcomes'] == analyze(tail, report)
        completed = None
    assert result['lines'] == tail.splitlines()[:len(result['lines'])], 'preserve captured prefix through shutdown'
    assert result['research_pid'] == stage['research_pid'] and result['state_file'] == str(state_file)
    assert result['metadata_only'] is True and result['playable'] is False
    receipts = [str(collect_batch(session, ROOT / row['directory'])) for row in report['batches']
                if completed is None or metadata.verify_batch(ROOT / row['directory'])['batch_fingerprint'] in completed]
    return dict(receipts=receipts, complete=result.get('complete', True),
                pending_batch_keys=result.get('pending_batch_keys', []), playable=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('verify', 'stage', 'reload-gate', 'capture', 'collect'))
    parser.add_argument('directory', type=Path)
    parser.add_argument('--session')
    args = parser.parse_args()
    use_controller()
    if args.action == 'verify':
        report, _ = verify(args.directory)
        result = dict(fingerprint=report['fingerprint'], requests=sum(row['requests'] for row in report['batches']))
    elif args.action == 'collect':
        result = collect(args.directory, args.session)
    else:
        result = {'stage': stage, 'reload-gate': reload_gate, 'capture': capture}[args.action](args.directory)
    print(json.dumps(result, ensure_ascii=False, indent=2))
