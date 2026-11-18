"""Retain complete jobs from a cleanly closed, interrupted subtree query."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import boss_subtree_inventory as subtrees
from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from boss_metadata_jobs import canonical
from boss_offline_inventory import closed, read
from collect_boss_metadata_jobs import repository_path
from mod_installation import unlinked_path
from stage_boss_subtrees import location, lines_for


def replay(session, batch, root=ROOT, *, allow_complete=False):
    root = unlinked_path(root)
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    work = unlinked_path(root / 'evidence/official-validation' / session)
    state = unlinked_path(root / ('runtime/official-validation-' + session) / 'state.json')
    post = unlinked_path(work / 'postcheck.json')
    assert closed(state, post, work), 'closed isolation and formal-file checks required'
    batch = unlinked_path(batch)
    manifest_path = unlinked_path(batch / 'manifest.json'); manifest = read(manifest_path)
    identity = {k: manifest[k] for k in ('schema', 'kind', 'build', 'jobs', 'inventory_sha256', 'source_sha256')}
    fingerprint = hashlib.sha256(canonical(identity)).hexdigest()[:20]
    assert manifest['fingerprint'] == fingerprint and manifest['kind'] == 'boss_subtree_inventory'
    assert manifest['schema'] == 1 and manifest['build'] == BUILD
    assert batch == unlinked_path(root / subtrees.OUTPUT / fingerprint)
    for flag in ('game_started', 'ui_input_sent', 'deployed', 'playable', 'activation_allowed', 'execution_order_proven'):
        assert manifest[flag] is False
    keys = [j['key'] for j in manifest['jobs']]
    assert 1 <= len(keys) <= 256 and len(keys) == len(set(keys))
    sources = {}
    archived_sources = work / 'subtree-source-snapshot'
    for name, digest in manifest['source_sha256'].items():
        assert name in subtrees.SOURCES, 'unrecognized historical subtree source'
        snapshot = unlinked_path(repository_path(archived_sources, name))
        assert sha(snapshot) == digest, 'historical query source changed'
        sources[snapshot.relative_to(root).as_posix()] = digest
    assert {'tools/boss_subtree_inventory.py', 'tools/boss_subtree_probe.lua'} <= set(manifest['source_sha256'])
    staged_path = unlinked_path(location(work, manifest, 'staged.json'))
    intent_path = unlinked_path(location(work, manifest, 'intent.json'))
    staged = read(staged_path)
    assert staged == read(intent_path)
    assert staged['state_file'] == str(state) and staged['batch'] == fingerprint
    assert staged['metadata_only'] is True and staged['ui_input_sent'] is False
    assert staged['manifest_sha256'] == sha(manifest_path)
    assert staged['script_sha256'] == manifest['script_sha256']
    archived_manifest = unlinked_path(location(work, manifest, 'manifest.json'))
    assert read(archived_manifest) == manifest
    script = unlinked_path(location(work, manifest, 'probe.lua'))
    assert script.read_bytes() == unlinked_path(batch / 'subtree-probe.lua').read_bytes()
    assert sha(script) == manifest['script_sha256']
    log = unlinked_path(work / 'UE4SS.log'); raw = log.read_bytes(); offset = staged['log_byte_offset']
    assert type(offset) is int and 0 <= offset <= len(raw)
    assert hashlib.sha256(raw[:offset]).hexdigest() == staged['log_prefix_sha256']
    progress = subtrees.analyze(lines_for(raw[offset:].decode('utf-8', errors='strict'), fingerprint),
                                manifest, allow_incomplete=True)
    captured_path = location(work, manifest, 'capture.json')
    if progress['batch_complete']:
        assert allow_complete, 'complete queries use the ordinary capture/collect workflow'
        lines = lines_for(raw[offset:].decode('utf-8', errors='strict'), fingerprint)
        assert read(captured_path) == dict(state_file=str(state), research_pid=staged['research_pid'],
            batch=fingerprint, script_sha256=manifest['script_sha256'], metadata_only=True,
            playable=False, execution_order_proven=False, lines=lines, outcomes=progress['outcomes'])
    for path in (state, post, manifest_path, staged_path, intent_path, archived_manifest, script, log):
        sources[path.relative_to(root).as_posix()] = sha(path)
    if progress['batch_complete']:
        sources[captured_path.relative_to(root).as_posix()] = sha(captured_path)
    report = dict(schema=1, session=session, batch=fingerprint, **progress, metadata_only=True,
        native_grant_verified=False, activation_verified=False, playable=False,
        execution_order_proven=False, runtime_acceptance_current=False, sources=sources,
        audit_source_sha256={name: sha(root / name) for name in (
            'tools/collect_boss_subtree_progress.py', 'tools/boss_subtree_inventory.py',
            'tools/stage_boss_subtrees.py', 'tests/test_boss_subtree_progress.py')})
    return report


def history(root=ROOT):
    """Replay each closed attempt, including complete batches, without changing receipts."""
    results = []
    for staged_path in sorted((root / 'evidence/official-validation').glob('*/boss-subtree-query-*-staged.json')):
        session = staged_path.parent.name
        assert re.fullmatch(r'\d{8}-\d{6}', session)
        state = root / ('runtime/official-validation-' + session) / 'state.json'
        post = staged_path.parent / 'postcheck.json'
        if not post.exists():
            continue  # A running attempt is not closed history or a reusable result.
        assert closed(state, post, staged_path.parent), 'preserve failed cleanup history'
        fingerprint = read(staged_path)['batch']
        results.append(replay(session, root / subtrees.OUTPUT / fingerprint, root, allow_complete=True))
    return results


def unstarted_keys(progress, prior):
    """Do not repeat any begun query, including rejections and interrupted queries."""
    attempted = {row['key'] for report in prior for row in report['outcomes']}
    attempted.update(report['interrupted_job'] for report in prior if report['interrupted_job'])
    return [key for key in progress['unstarted_job_keys'] if key not in attempted]


def unattempted_jobs(jobs, audits, root=ROOT):
    """Select by exact class identity, even when its receipt-derived key changes.

    Completed rejections and interrupted native calls remain attempted. Retrying
    them needs a separately reviewed explicit selection, never a fresh default.
    """
    root = unlinked_path(root)
    attempted = set()
    for audit in audits:
        assert audit['metadata_only'] is True and audit['playable'] is False
        assert re.fullmatch(r'[0-9a-f]{20}', audit['batch'])
        path = unlinked_path(root / subtrees.OUTPUT / audit['batch'] / 'manifest.json')
        assert audit['sources'][path.relative_to(root).as_posix()] == sha(path), 'historical job identities changed'
        original = {job['key']: job for job in read(path)['jobs']}
        for row in audit['outcomes']:
            job = original[row['key']]
            assert row['id'] == job['id'] and row['parent_class'] == job['path']
            attempted.add((job['id'], job['path']))
        if audit['interrupted_job'] is not None:
            job = original[audit['interrupted_job']]
            attempted.add((job['id'], job['path']))
    return [job for job in jobs if (job['id'], job['path']) not in attempted]


def collect(session, batch, root=ROOT):
    report = replay(session, batch, root)
    destination = root / 'evidence/official-validation' / session / 'subtree-interrupted-progress.json'
    if destination.exists():
        assert read(destination) == report, 'preserve previous progress audit'
    else:
        write_json(destination, report)
    return destination, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session'); parser.add_argument('batch', type=Path)
    args = parser.parse_args()
    path, result = collect(args.session, args.batch)
    print(json.dumps(dict(report=str(path), completed_jobs=len(result['outcomes']),
        successful_mappings=sum(r['mapping_observed'] for r in result['outcomes']),
        interrupted_job=result['interrupted_job'], unstarted_jobs=len(result['unstarted_job_keys']),
        batch_complete=False, playable=False), ensure_ascii=False, indent=2))
