"""Freeze missing-only metadata requests for every observed character and ability."""

from collections import Counter
import hashlib
import json

from boss_adaptation_workflow import BUILD, ROOT, sha, write_json
import boss_metadata_jobs as metadata
from boss_offline_inventory import inputs
from build_boss_profile_candidate import lua


def select(catalog, inventory):
    """Never repeat successes, conflicting results or dedicated grant queries."""
    rows = {row['id']: row for row in inventory['characters']}
    candidates, pending = [], []
    reasons = Counter()
    for candidate in catalog['candidates']:
        if candidate['reference_only'] or candidate['resource_folder'] == 'Common':
            continue
        candidates.append(candidate)
        row = rows[candidate['id']]
        variants = {v['path']: v for v in row['variants']}
        abilities = {a['path']: a for a in row['abilities']}
        for job in metadata.jobs_for(candidate):
            path = job['lookup_path']
            record = variants[path] if job['role'] == 'character' else abilities[path]
            if record['metadata'] in ('verified', 'conflict'):
                reasons['verified_or_conflicting_metadata'] += 1
            elif (job['role'] == 'character' and record['spawn_configs']
                    or job['role'] == 'ability' and record['v5_skill']):
                reasons['existing_spawn_or_v5_mapping'] += 1
            elif job['role'] == 'ability' and record['route'] == 'exact_grant_needs_metadata':
                reasons['dedicated_exact_grant_batch'] += 1
            else:
                pending.append(job['key'])
                reasons['pending_' + job['role']] += 1
    batches = metadata.batches(candidates, pending)
    assert len({job['key'] for batch in batches for job in batch}) == len(pending)
    return batches, dict(reasons)


def build(root=ROOT):
    inventory, catalog, *_ = inputs(root)
    batches, counts = select(catalog, inventory)
    identity = dict(schema=1, build=BUILD,
                    inventory_sha256=hashlib.sha256(metadata.canonical(inventory)).hexdigest(),
                    source_sha256=sha(root / 'tools/prepare_full_boss_catalog.py'),
                    probe_sha256=sha(root / 'tools/full_boss_catalog_probe.lua'),
                    jobs=[[job['key'] for job in batch] for batch in batches])
    fingerprint = hashlib.sha256(metadata.canonical(identity)).hexdigest()[:20]
    target = root / 'runtime/full-boss-catalog' / fingerprint
    frozen = []
    for jobs in batches:
        path = metadata.freeze(jobs, target, root)
        manifest = metadata.verify_batch(path, root)
        frozen.append(dict(directory=path.relative_to(root).as_posix(), requests=len(jobs),
                           roles=dict(Counter(job['role'] for job in jobs)),
                           ids=sorted({job['id'] for job in jobs}),
                           manifest_sha256=sha(path / 'metadata-probe-manifest.json'),
                           script_sha256=manifest['script_sha256']))
    report = dict(identity, fingerprint=fingerprint, counts=counts, batches=frozen,
                  only_observed_catalog=True, complete_package_inventory=False,
                  game_started=False, deployed=False, playable=False)
    script = collector(report, root)
    (target / 'metadata-collector.lua').write_bytes(script)
    report['collector_sha256'] = hashlib.sha256(script).hexdigest()
    report['budget_seconds'] = 480
    write_json(target / 'queue.json', report)
    write_json(target / 'manifest.json', dict(report, script_sha256=report['collector_sha256']))
    return target, report


def collector(report, root=ROOT):
    probes = []
    for row in report['batches']:
        directory = root / row['directory']
        manifest = metadata.verify_batch(directory, root)
        probes.append(dict(key=manifest['batch_fingerprint'],
                           source=(directory / 'metadata-probe.lua').read_text(encoding='utf-8')))
    header = ('local fingerprint=' + lua(report['fingerprint']) + '\nlocal budget_seconds=480\n'
              + 'local batches=' + lua(probes) + '\n')
    return header.encode('utf-8') + (root / 'tools/full_boss_catalog_probe.lua').read_bytes()


if __name__ == '__main__':
    directory, report = build()
    print(json.dumps(dict(directory=str(directory), batches=len(report['batches']), counts=report['counts'],
                          game_started=False, playable=False), ensure_ascii=False, indent=2))
