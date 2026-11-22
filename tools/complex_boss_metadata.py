"""Freeze and collect the complex Boss configuration checks in one research reload."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys

import boss_metadata_jobs as metadata
from boss_adaptation_workflow import ROOT, sha
from build_boss_profile_candidate import lua
from mod_installation import unlinked_path
import prepare_complex_boss_configuration as configurations
from prepare_boss_subtree_references import chunks
import stage_boss_subtree_references as stage


OUTPUT = 'runtime/complex-boss-metadata'
LABEL = 'complex-boss-metadata'
SNAPSHOT = 'complex-boss-source-snapshot'
SOURCES = ('tools/complex_boss_metadata.py', 'tools/prepare_complex_boss_configuration.py',
           'tools/stage_boss_subtree_references.py', 'tools/stage_boss_inventory_metadata.py',
           'tools/prepare_boss_subtree_references.py', 'tools/full_boss_catalog_probe.lua', *metadata.SOURCES)


def render(manifest, root):
    jobs = {job['key']: job for job in manifest['jobs']}
    sources = [dict(key=batch['fingerprint'], source=metadata.render(
        [jobs[key] for key in batch['jobs']], batch['fingerprint'])) for batch in manifest['batches']]
    prefix = f"local fingerprint={lua(manifest['fingerprint'])}\nlocal budget_seconds={manifest['budget_seconds']}\n"
    return (prefix + 'local batches=' + lua(sources) + '\n').encode('utf-8') + (
        root / 'tools/full_boss_catalog_probe.lua').read_bytes()


def identity(config, root=ROOT):
    jobs = [job for profile in config['profiles'] for job in profile['metadata_jobs']]
    if not jobs or len({job['key'] for job in jobs}) != len(jobs):
        raise ValueError('Unique complex Boss class checks required')
    batches = []
    for group in chunks(jobs):
        keys = [job['key'] for job in group]
        fingerprint = hashlib.sha256(metadata.canonical(keys)).hexdigest()[:20]
        batches.append(dict(fingerprint=fingerprint, jobs=keys))
    return dict(schema=1, build=config['build_sha256'],
        configuration_sha256=hashlib.sha256(metadata.canonical(config)).hexdigest(),
        source_sha256={name: sha(root / name) for name in SOURCES}, evidence_sha256={},
        jobs=jobs, batches=batches, budget_seconds=240, cleanup_seconds=120,
        metadata_only=True, released=False)


def expected(root=ROOT):
    config = configurations.plan(root)
    record = identity(config, root)
    key = hashlib.sha256(metadata.canonical(record)).hexdigest()[:20]
    manifest = dict(record, fingerprint=key)
    raw = render(manifest, root)
    return dict(manifest, script_sha256=hashlib.sha256(raw).hexdigest()), raw


def frozen(directory, root=ROOT, *, source_root=None):
    """Verify historical receipts against source bytes archived at staging."""
    root, directory = unlinked_path(root), unlinked_path(directory)
    manifest = json.loads((directory / 'manifest.json').read_bytes())
    record = {key: value for key, value in manifest.items() if key not in ('fingerprint', 'script_sha256')}
    key = hashlib.sha256(metadata.canonical(record)).hexdigest()[:20]
    if manifest['fingerprint'] != key or directory != root / OUTPUT / key:
        raise ValueError('Exact frozen metadata directory required')
    source_root = Path(source_root or root)
    if set(manifest['source_sha256']) != set(SOURCES) or any(sha(source_root / name) != digest
            for name, digest in manifest['source_sha256'].items()):
        raise ValueError('Frozen complex Boss probe source changed')
    path = unlinked_path(directory / 'metadata-collector.lua')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest['script_sha256']:
        raise ValueError('Frozen complex Boss probe changed')
    return manifest, {'metadata-collector.lua': raw}


def verify(directory, root=ROOT):
    observed, files = frozen(directory, root)
    manifest, raw = expected(root)
    if observed != manifest or files['metadata-collector.lua'] != raw:
        raise ValueError('Complex Boss declarations changed since freezing')
    return manifest, files


def build(root=ROOT):
    manifest, raw = expected(root)
    directory = root / OUTPUT / manifest['fingerprint']
    if not directory.exists():
        directory.mkdir(parents=True)
        (directory / 'metadata-collector.lua').write_bytes(raw)
        (directory / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
                                                 encoding='utf-8')
    verify(directory, root)
    return directory, manifest


@contextmanager
def controller():
    # Use the shared metadata carrier, foreground and cleanup checks with this
    # batch's verifier and a distinct namespace for its original receipts.
    old = stage.references, stage.LABEL, stage.SNAPSHOT
    stage.references, stage.LABEL, stage.SNAPSHOT = sys.modules[__name__], LABEL, SNAPSHOT
    try:
        yield
    finally:
        stage.references, stage.LABEL, stage.SNAPSHOT = old


def closed_receipt(directory, session, root=ROOT):
    with controller():
        report = stage.replay(directory, session, root)
    return dict(report, kind='complex_boss_configuration_receipt')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'stage', 'reload-gate', 'capture', 'collect'))
    parser.add_argument('directory', type=Path, nargs='?')
    parser.add_argument('--session')
    args = parser.parse_args()
    if args.action == 'build':
        path, manifest = build()
        result = dict(directory=str(path), jobs=len(manifest['jobs']), batches=len(manifest['batches']))
    elif args.action == 'collect':
        if not args.directory or not args.session:
            parser.error('collect requires directory and --session')
        result = closed_receipt(args.directory, args.session)
        output = args.directory / f"{args.session}-metadata-receipt.json"
        with output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        result = dict(receipt=str(output), verified=sum(row['metadata_verified'] for row in result['outcomes']))
    else:
        if not args.directory:
            parser.error('directory required')
        with controller():
            result = {'stage': stage.stage, 'reload-gate': stage.reload_gate, 'capture': stage.capture}[args.action](args.directory)
    print(json.dumps(result, ensure_ascii=False, indent=2))
