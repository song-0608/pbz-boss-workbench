"""Stage exact reference CDO queries; capture only one complete serial execution.

No game launch, input, Actor creation, grants or activation occur in this tool.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import time

from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from boss_offline_inventory import closed, read
import boss_metadata_jobs as metadata
from mod_installation import unlinked_path
import prepare_boss_subtree_references as references
import stage_boss_inventory_metadata as core

LABEL = 'boss-subtree-references'
SNAPSHOT = 'subtree-reference-source-snapshot'
PREFIXES = ('PBZ_FULL_CATALOG:', 'PBZ_ADAPTER_META:')


def location(work, manifest, suffix):
    return work / f"{LABEL}-{manifest['fingerprint']}-{suffix}"


def verify(directory):
    manifest, files = references.verify(directory)
    return manifest, files['metadata-collector.lua']


@contextmanager
def controller(manifest=None, expected_session=None):
    old_verify, old_label, old_current = core.verify, core.QUERY_LABEL, core.current
    core.verify, core.QUERY_LABEL = verify, LABEL
    if manifest is not None:
        def reserved_current():
            result = old_current()
            if expected_session is not None:
                assert session_identity(result) == expected_session, 'research session changed while archiving sources'
            reserve(manifest, result[2])
            return result
        core.current = reserved_current
    try:
        yield
    finally:
        core.verify, core.QUERY_LABEL, core.current = old_verify, old_label, old_current


def archive_sources(manifest, work, *, create=False, root=ROOT):
    snapshot = unlinked_path(work / SNAPSHOT)
    assert set(manifest['source_sha256']) == set(references.SOURCES)
    for name, digest in manifest['source_sha256'].items():
        target = unlinked_path(snapshot / name)
        assert target.is_relative_to(snapshot)
        if create:
            raw = unlinked_path(root / name).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == digest, 'source drift before staging'
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as handle:
                handle.write(raw)
        assert sha(target) == digest, 'archived reference source changed'


def reserve(manifest, state):
    now = time.time()
    assert now + manifest['budget_seconds'] + manifest['cleanup_seconds'] < state['deadline_unix'], \
        'reserve the full query and cleanup budget'
    return now


def session_identity(current):
    _, _, state, work, carrier, pid = current
    return state['state_file'], state['deadline_unix'], str(work), str(carrier), pid


def stage(directory):
    manifest, _ = verify(directory)
    assert manifest['jobs'] and manifest['batches'], 'do not stage an empty reference query'
    current = core.current()
    _, _, state, work, *_ = current
    expected_session = session_identity(current)
    assert not list(work.glob(LABEL + '-*')), 'preserve the session reference attempt'
    reserve(manifest, state)
    archive_sources(manifest, work, create=True)
    # The shared core rechecks ownership, idle/offline state, isolation, PID,
    # formal files and carrier hashes immediately before writing the carrier.
    with controller(manifest, expected_session):
        result = core.stage(directory)
    reserve(manifest, state)
    return result


def snapshot(directory):
    with controller():
        result = core.snapshot(directory)
    archive_sources(result[0], result[3])
    return result


def reload_gate(directory):
    manifest, validation, state, work, staged, tail = snapshot(directory)
    assert not any(prefix in tail for prefix in PREFIXES), 'reference query already has events'
    reserve(manifest, state)
    window = core.foreground_window(validation, staged['research_pid'])
    now = reserve(manifest, state)  # Foreground inspection can consume time.
    gate = dict(window_id=window, research_pid=staged['research_pid'], batch=manifest['fingerprint'],
        state_file=state['state_file'], key='Control_L+r', purpose=LABEL,
        gate_expires_at=now + 10, input_sent=False, metadata_only=True,
        staged_sha256=sha(location(work, manifest, 'staged.json')))
    write_json(location(work, manifest, f'gate-{time.time_ns()}.json'), gate)
    return gate


def lines_for(raw):
    return [line for line in raw.splitlines() if any(prefix in line for prefix in PREFIXES)]


def analyze(lines, manifest):
    """Require exact outer/child order, complete results and no post-END events."""
    jobs = {job['key']: job for job in manifest['jobs']}
    children = manifest['batches']
    assert len(jobs) == len(manifest['jobs']) and len(children) == len({b['fingerprint'] for b in children})
    assert [key for child in children for key in child['jobs']] == [job['key'] for job in manifest['jobs']]
    state, index, active, child_lines, outcomes = 'unstarted', 0, None, [], []
    pattern = re.compile(r'PBZ_(FULL_CATALOG|ADAPTER_META):([A-Z_]+)=(.*)$')
    for line in lines:
        match = pattern.search(line)
        assert match, 'unrecognized reference query event'
        owner, event, payload = match.groups(); payload = payload.strip()
        assert state != 'complete', 'event after reference collector END'
        if owner == 'FULL_CATALOG':
            if event == 'START':
                assert state == 'unstarted' and payload == manifest['fingerprint'], 'single exact collector START required'
                state = 'active'
            else:
                assert (event == 'END' and state == 'active' and active is None
                    and index == len(children) and payload == manifest['fingerprint']), 'complete collector END required; STOP is not evidence'
                state = 'complete'
            continue
        assert state == 'active', 'child outside reference collector'
        if event == 'START':
            assert active is None and index < len(children) and payload == children[index]['fingerprint'], \
                'single serial child START required'
            active = children[index]
            child_lines = [line]
        else:
            assert active is not None, 'orphan reference metadata event'
            assert event in ('OUTCOME', 'REJECTED', 'END'), 'stopped or unknown reference child'
            child_lines.append(line)
            if event in ('OUTCOME', 'REJECTED'):
                completed_jobs = sum('PBZ_ADAPTER_META:OUTCOME=' in item or 'PBZ_ADAPTER_META:REJECTED=' in item
                                     for item in child_lines) - 1
                assert completed_jobs < len(active['jobs']) and payload.split('|', 1)[0] == active['jobs'][completed_jobs], \
                    'single ordered exact child result required'
            if event == 'END':
                assert payload == active['fingerprint'], 'foreign reference child END'
                outcomes.extend(metadata.analyze(child_lines, dict(batch_fingerprint=active['fingerprint'],
                    jobs=[jobs[key] for key in active['jobs']])))
                index += 1; active = None
    assert state == 'complete' and len(outcomes) == len(jobs), 'complete serial reference query required'
    return outcomes


def capture_value(manifest, state_file, staged, lines):
    return dict(state_file=str(state_file), research_pid=staged['research_pid'],
        batch=manifest['fingerprint'], script_sha256=manifest['script_sha256'],
        metadata_only=True, reference_only=True, native_grant_verified=False,
        activation_verified=False, playable=False, lines=lines, outcomes=analyze(lines, manifest))


def capture(directory):
    manifest, _, state, work, staged, tail = snapshot(directory)
    result = capture_value(manifest, state['state_file'], staged, lines_for(tail))
    with location(work, manifest, 'results.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    return dict(queries=len(result['outcomes']), verified=sum(r['metadata_verified'] for r in result['outcomes']),
                metadata_only=True, playable=False)


def replay(directory, session, root=ROOT):
    """Replay original closed evidence; deliberately never call expected()/inputs()."""
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    root, directory = unlinked_path(root), unlinked_path(directory)
    work = unlinked_path(root / 'evidence/official-validation' / session)
    state_path = unlinked_path(root / ('runtime/official-validation-' + session) / 'state.json')
    post_path = unlinked_path(work / 'postcheck.json')
    assert closed(state_path, post_path, work), 'cleanly closed isolation checks required'
    manifest, files = references.frozen(directory, root, source_root=work / SNAPSHOT)
    archive_sources(manifest, work, root=root)
    staged_path, intent_path = (unlinked_path(location(work, manifest, suffix)) for suffix in ('staged.json', 'intent.json'))
    staged = read(staged_path)
    assert staged == read(intent_path)
    assert staged['state_file'] == str(state_path) and staged['batch'] == manifest['fingerprint']
    assert staged['metadata_only'] is True and staged['input_sent'] is False
    assert staged['manifest_sha256'] == sha(directory / 'manifest.json')
    assert staged['script_sha256'] == manifest['script_sha256']
    archived_manifest = unlinked_path(location(work, manifest, 'manifest.json'))
    assert read(archived_manifest) == manifest
    archived_script = unlinked_path(location(work, manifest, 'metadata.lua'))
    assert archived_script.read_bytes() == files['metadata-collector.lua']
    log_path = unlinked_path(work / 'UE4SS.log'); raw = log_path.read_bytes()
    offset = staged['log_byte_offset']
    assert type(offset) is int and 0 <= offset <= len(raw)
    assert hashlib.sha256(raw[:offset]).hexdigest() == staged['log_prefix_sha256']
    result_path = unlinked_path(location(work, manifest, 'results.json'))
    result = capture_value(manifest, state_path, staged, lines_for(raw[offset:].decode('utf-8', errors='strict')))
    assert read(result_path) == result, 'closed log and captured reference results differ'
    paths = [state_path, post_path, staged_path, intent_path, archived_manifest, archived_script,
             log_path, result_path, directory / 'manifest.json', *[directory / name for name in files]]
    paths.extend(unlinked_path(work / SNAPSHOT / name) for name in manifest['source_sha256'])
    sources = dict(manifest['evidence_sha256'])
    for path in paths:
        sources[path.relative_to(root).as_posix()] = sha(path)
    return dict(schema=1, kind='boss_subtree_reference_receipt', build=BUILD, session=session,
        batch=manifest['fingerprint'], directory=directory.relative_to(root).as_posix(),
        outcomes=result['outcomes'], jobs=manifest['jobs'], metadata_only=True,
        reference_only=True, native_grant_verified=False, activation_verified=False,
        playable=False, runtime_acceptance_current=False, sources=sources)


def verify_receipt(path, root=ROOT):
    root, path = unlinked_path(root), unlinked_path(path)
    report = read(path)
    assert re.fullmatch(r'\d{8}-\d{6}', report['session']) and re.fullmatch(r'[0-9a-f]{20}', report['batch'])
    target = root / 'research/boss-adaptation/subtree-reference-receipts' / (report['session'] + '-' + report['batch'] + '.json')
    assert path == unlinked_path(target), 'canonical reference receipt required'
    directory = unlinked_path(root / report['directory'])
    assert directory.is_relative_to(root)
    assert report == replay(directory, report['session'], root), 'reference receipt drift'
    return report


def collect(directory, session, root=ROOT):
    report = replay(directory, session, root)
    target = root / 'research/boss-adaptation/subtree-reference-receipts' / (session + '-' + report['batch'] + '.json')
    if target.exists():
        assert read(target) == report, 'preserve prior reference receipt'
    else:
        write_json(target, report)
    verify_receipt(target, root)
    return dict(receipt=str(target), queries=len(report['outcomes']),
                verified=sum(r['metadata_verified'] for r in report['outcomes']), playable=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('verify', 'stage', 'reload-gate', 'capture', 'collect'))
    parser.add_argument('directory', type=Path)
    parser.add_argument('--session')
    args = parser.parse_args()
    if args.action == 'verify':
        manifest, _ = verify(args.directory)
        result = dict(queries=len(manifest['jobs']), batches=len(manifest['batches']), stage_supported=True, playable=False)
    elif args.action == 'collect':
        assert args.session
        result = collect(args.directory, args.session)
    else:
        assert args.session is None
        result = {'stage': stage, 'reload-gate': reload_gate, 'capture': capture}[args.action](args.directory)
    print(json.dumps(result, ensure_ascii=False, indent=2))
