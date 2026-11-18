"""Prepare exact type queries for closed native tree references; never grant or activate."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import boss_metadata_jobs as metadata
import boss_subtree_inventory as subtrees
from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from boss_offline_inventory import inputs
from build_boss_profile_candidate import lua
from collect_boss_subtree_progress import history
from mod_installation import unlinked_path

OUTPUT = 'runtime/boss-subtree-references'
SOURCES = ('tools/prepare_boss_subtree_references.py', 'tests/test_boss_subtree_references.py',
           'tools/stage_boss_subtree_references.py', 'tests/test_stage_boss_subtree_references.py',
           'tests/test_boss_subtree_reference_collector.lua',
           'tools/stage_boss_inventory_metadata.py', 'tools/stage_readonly_contracts.py',
           'tools/native_grant_ui_stage.py', 'tools/full_boss_catalog_probe.lua',
           'tools/boss_offline_inventory.py',
           *metadata.SOURCES, *subtrees.SOURCES)
IDENTITY = ('schema', 'kind', 'build', 'inventory_sha256', 'evidence_sha256',
            'source_sha256', 'jobs', 'deferred', 'already_verified')


def plan(characters, audits):
    folders = {c['folder']: c['id'] for c in characters}
    known = {a['path']: a for c in characters for a in c['abilities']}
    origins = {}
    for audit in audits:
        assert audit['metadata_only'] is True and audit['playable'] is False
        for row in audit['outcomes']:
            if not row['mapping_observed']:
                assert not row['trees'], 'rejected jobs cannot supply references'
                continue
            assert row['activation_verified'] is False and row['native_grant_verified'] is False
            for path in row['referenced_ability_classes']:
                assert subtrees.OBJECT.fullmatch(path) and path.endswith('_C')
                origins.setdefault(path, set()).add((audit['session'], row['key'], row['parent_class']))
    jobs, deferred, verified = [], [], []
    for path, parents in sorted(origins.items()):
        match = re.fullmatch(r'/PBZCombatAsset/ActorData/Mobs/([A-Za-z0-9_]+)/.+', path)
        if not match or match[1] not in folders:
            deferred.append(dict(path=path, reason='outside observed NPC resource folders'))
            continue
        record = known.get(path)
        if record and record['metadata'] == 'verified':
            assert record['kind'] in ('leaf', 'subtree')
            verified.append(dict(path=path, kind=record['kind']))
            continue
        if record and record['metadata'] == 'conflict':
            deferred.append(dict(path=path, reason='conflicting metadata needs review'))
            continue
        if record and record['metadata'] == 'rejected':
            deferred.append(dict(path=path, reason='exact type lookup already rejected; review before an explicit retry'))
            continue
        job = dict(id=folders[match[1]], role='ability', package=path.split('.', 1)[0],
            lookup_path=path, config_candidates=[], reference_only=True,
            native_grant_verified=False, activation_allowed=False,
            origins=[dict(session=s, parent_key=k, parent_class=p) for s, k, p in sorted(parents)])
        job['key'] = hashlib.sha256(metadata.canonical(job)).hexdigest()[:20]
        jobs.append(job)
    assert len(jobs) <= 2048 and len(jobs) == len({j['lookup_path'] for j in jobs})
    return jobs, deferred, verified


def chunks(jobs):
    result, pending, identifiers = [], [], set()
    for job in jobs:
        if pending and (len(pending) == 64 or job['id'] not in identifiers and len(identifiers) == 3):
            result.append(pending); pending, identifiers = [], set()
        pending.append(job); identifiers.add(job['id'])
    if pending:
        result.append(pending)
    return result


def expected(root=ROOT):
    inventory, *_ = inputs(root)
    audits = history(root)
    jobs, deferred, verified = plan(inventory['characters'], audits)
    evidence = {}
    for audit in audits:
        for path, digest in audit['sources'].items():
            assert path not in evidence or evidence[path] == digest
            assert sha(root / path) == digest
            evidence[path] = digest
    identity = dict(schema=1, kind='boss_subtree_reference_metadata', build=BUILD,
        inventory_sha256=hashlib.sha256(metadata.canonical(inventory)).hexdigest(),
        evidence_sha256=evidence, source_sha256={p: sha(root / p) for p in SOURCES},
        jobs=jobs, deferred=deferred, already_verified=verified)
    key = hashlib.sha256(metadata.canonical(identity)).hexdigest()[:20]
    files, batches = {}, []
    for index, group in enumerate(chunks(jobs), 1):
        child = hashlib.sha256(metadata.canonical(dict(parent=key, jobs=[j['key'] for j in group]))).hexdigest()[:20]
        name = f'metadata-probe-{index:03d}.lua'
        raw = metadata.render(group, child).encode('utf-8')
        files[name] = raw
        batches.append(dict(fingerprint=child, jobs=[j['key'] for j in group],
                            script=name, script_sha256=hashlib.sha256(raw).hexdigest()))
    header = 'local fingerprint=' + lua(key) + '\nlocal budget_seconds=480\nlocal batches='
    header += lua([dict(key=b['fingerprint'], source=files[b['script']].decode('utf-8')) for b in batches]) + '\n'
    files['metadata-collector.lua'] = header.encode('utf-8') + (root / 'tools/full_boss_catalog_probe.lua').read_bytes()
    manifest = dict(identity, fingerprint=key, batches=batches,
        collector_sha256=hashlib.sha256(files['metadata-collector.lua']).hexdigest(),
        script_sha256=hashlib.sha256(files['metadata-collector.lua']).hexdigest(),
        budget_seconds=480, cleanup_seconds=120,
        metadata_only=True, game_started=False, deployed=False, stage_supported=True,
        native_grant_verified=False, activation_allowed=False, playable=False,
        execution_order_proven=False, all_boss_skills_complete=False)
    return manifest, files


def frozen(directory, root=ROOT, *, source_root=None):
    """Verify original bytes without rebuilding from later inventory receipts.

    Live staging additionally uses verify(). Closed-session replay uses archived
    sources and the original manifest, so importing its receipt cannot recurse
    through inputs() or silently substitute a newly generated query.
    """
    root, directory = unlinked_path(root), unlinked_path(directory)
    manifest = json.loads((directory / 'manifest.json').read_bytes())
    identity = {key: manifest[key] for key in IDENTITY}
    key = hashlib.sha256(metadata.canonical(identity)).hexdigest()[:20]
    assert manifest['schema'] == 1 and manifest['kind'] == 'boss_subtree_reference_metadata'
    assert manifest['build'] == BUILD and manifest['fingerprint'] == key
    assert directory == unlinked_path(root / OUTPUT / key)
    assert manifest['metadata_only'] is True and manifest['stage_supported'] is True
    for flag in ('game_started', 'deployed', 'native_grant_verified', 'activation_allowed',
                 'playable', 'execution_order_proven', 'all_boss_skills_complete'):
        assert manifest[flag] is False, flag
    assert manifest['budget_seconds'] == 480 and manifest['cleanup_seconds'] == 120
    assert re.fullmatch(r'[0-9a-f]{64}', manifest['inventory_sha256'])
    source_root = unlinked_path(source_root or root)
    assert set(manifest['source_sha256']) == set(SOURCES)
    for name, digest in manifest['source_sha256'].items():
        assert sha(unlinked_path(source_root / name)) == digest, 'original reference query source changed'
    for name, digest in manifest['evidence_sha256'].items():
        path = unlinked_path(root / name)
        assert path.is_relative_to(root) and sha(path) == digest, 'reference origin evidence changed'
    jobs = manifest['jobs']
    assert 0 <= len(jobs) <= 2048 and len(jobs) == len({j['lookup_path'] for j in jobs})
    assert len(jobs) == len({j['key'] for j in jobs})
    for job in jobs:
        unsigned = {k: v for k, v in job.items() if k != 'key'}
        assert job['key'] == hashlib.sha256(metadata.canonical(unsigned)).hexdigest()[:20]
        assert re.fullmatch(r'[a-z0-9_]{1,80}', job['id']) and job['role'] == 'ability'
        assert subtrees.OBJECT.fullmatch(job['lookup_path']) and job['lookup_path'].endswith('_C')
        assert job['lookup_path'].startswith('/PBZCombatAsset/ActorData/Mobs/')
        assert job['package'] == job['lookup_path'].split('.', 1)[0] and job['config_candidates'] == []
        assert job['reference_only'] is True and job['activation_allowed'] is False
        assert job['native_grant_verified'] is False and job['origins']
        for origin in job['origins']:
            assert re.fullmatch(r'\d{8}-\d{6}', origin['session'])
            assert re.fullmatch(r'[0-9a-f]{20}', origin['parent_key'])
            assert subtrees.OBJECT.fullmatch(origin['parent_class'])
    groups = chunks(jobs)
    assert len(groups) == len(manifest['batches'])
    files = {}
    for index, (group, row) in enumerate(zip(groups, manifest['batches']), 1):
        child = hashlib.sha256(metadata.canonical(dict(parent=key, jobs=[j['key'] for j in group]))).hexdigest()[:20]
        assert row['fingerprint'] == child and row['jobs'] == [j['key'] for j in group]
        assert row['script'] == f'metadata-probe-{index:03d}.lua'
        raw = unlinked_path(directory / row['script']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row['script_sha256']
        files[row['script']] = raw
    script = unlinked_path(directory / 'metadata-collector.lua').read_bytes()
    assert hashlib.sha256(script).hexdigest() == manifest['collector_sha256'] == manifest['script_sha256']
    files['metadata-collector.lua'] = script
    assert {p.name for p in directory.iterdir()} == {'manifest.json', *files}
    return manifest, files


def build(root=ROOT):
    manifest, files = expected(root)
    directory = unlinked_path(root / OUTPUT / manifest['fingerprint'])
    if not directory.exists():
        directory.mkdir(parents=True)
        for name, raw in files.items():
            (directory / name).write_bytes(raw)
        write_json(directory / 'manifest.json', manifest)
    verify(directory, root)
    return directory, manifest


def verify(directory, root=ROOT):
    directory = unlinked_path(directory)
    manifest, files = expected(root)
    assert directory == unlinked_path(root / OUTPUT / manifest['fingerprint'])
    assert {p.name for p in directory.iterdir()} == {'manifest.json', *files}
    assert json.loads((directory / 'manifest.json').read_bytes()) == manifest
    assert all((directory / name).read_bytes() == raw for name, raw in files.items())
    return manifest, files


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'verify'), nargs='?', default='build')
    parser.add_argument('directory', nargs='?', type=Path)
    args = parser.parse_args()
    if args.action == 'verify':
        assert args.directory is not None
        manifest, _ = verify(args.directory)
        directory = args.directory
    else:
        assert args.directory is None
        directory, manifest = build()
    print(json.dumps(dict(directory=str(directory), requests=len(manifest['jobs']),
        batches=len(manifest['batches']), deferred=len(manifest['deferred']),
        already_verified=len(manifest['already_verified']), game_started=False,
        stage_supported=manifest['stage_supported'], playable=False), ensure_ascii=False, indent=2))
