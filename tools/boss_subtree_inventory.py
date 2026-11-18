"""Freeze and parse read-only subtree CDO queries; never infer executable combos."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import math

from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from boss_metadata_jobs import canonical
from boss_offline_inventory import inputs
from build_boss_profile_candidate import lua
from mod_installation import unlinked_path

OUTPUT = 'runtime/boss-subtree-inventory'
PREFIX = 'PBZ_SUBTREE_META:'
MAX_STAGE_JOBS = 96  # 384 seconds of checked job work within the 480-second outer budget.
SOURCES = ('tools/boss_subtree_inventory.py', 'tools/boss_subtree_probe.lua',
           'tools/stage_boss_subtrees.py', 'tests/test_boss_subtree_inventory.py',
           'tests/test_boss_subtree_probe.lua', 'tools/collect_boss_subtree_progress.py',
           'tests/test_boss_subtree_progress.py')
OBJECT = re.compile(r'/[A-Za-z0-9_/]+\.[A-Za-z0-9_]+')
FULL = re.compile(r'([A-Za-z0-9_]+) (/[A-Za-z0-9_/.:]+)')


def jobs_for(characters, sources):
    jobs = []
    for character in characters:
        identifier, folder = character['id'], character['folder']
        assert re.fullmatch(r'[a-z0-9_]{1,80}', identifier)
        assert re.fullmatch(r'[A-Za-z0-9_]{1,80}', folder)
        prefix = '/PBZCombatAsset/ActorData/Mobs/' + folder + '/'
        for ability in character['abilities']:
            if ability['metadata'] != 'verified' or ability['kind'] != 'subtree':
                continue
            path = ability['path']
            assert OBJECT.fullmatch(path) and path.startswith(prefix) and path.endswith('_C')
            receipts = ability['receipts']
            assert receipts and all(p in sources and re.fullmatch(r'[0-9a-f]{64}', sources[p]) for p in receipts)
            job = dict(id=identifier, path=path, metadata_receipts={p: sources[p] for p in receipts})
            job['key'] = hashlib.sha256(canonical(job)).hexdigest()[:20]
            jobs.append(job)
    assert len(jobs) <= 256 and len({j['path'] for j in jobs}) == len(jobs)
    priority = {'057_wanjun': 0, '044_pengmeng': 1, '056_youlong': 2, '042_ahua': 3}
    return sorted(jobs, key=lambda j: (priority.get(j['id'], 10), j['id'], j['path']))


def payload(jobs, fingerprint, root=ROOT):
    assert re.fullmatch(r'[0-9a-f]{20}', fingerprint) and len(jobs) <= 256
    header = 'local jobs=' + lua([{k: j[k] for k in ('key', 'id', 'path')} for j in jobs])
    header += '\nlocal fingerprint=' + lua(fingerprint) + '\n'
    return header.encode('utf-8') + (root / 'tools/boss_subtree_probe.lua').read_bytes()


def expected(root=ROOT, *, job_keys=None):
    snapshot, *_ = inputs(root)
    jobs = jobs_for(snapshot['characters'], snapshot['sources'])
    if job_keys is not None:
        assert job_keys and len(job_keys) == len(set(job_keys)), 'nonempty unique observed job keys required'
        selected = set(job_keys)
        assert selected <= {job['key'] for job in jobs}, 'unknown subtree query key'
        jobs = [job for job in jobs if job['key'] in selected]
    identity = dict(schema=1, kind='boss_subtree_inventory', build=BUILD, jobs=jobs,
        inventory_sha256=hashlib.sha256(canonical(snapshot)).hexdigest(),
        source_sha256={p: sha(root / p) for p in SOURCES})
    fingerprint = hashlib.sha256(canonical(identity)).hexdigest()[:20]
    raw = payload(jobs, fingerprint, root)
    manifest = dict(identity, fingerprint=fingerprint, script_sha256=hashlib.sha256(raw).hexdigest(),
        max_seconds=480, max_poll_callbacks=4800, max_job_seconds=4, max_job_nodes=256,
        max_tree_nodes=128, max_job_references=1024, max_batch_nodes=4096,
        max_batch_references=16384, game_started=False, ui_input_sent=False,
        deployed=False, playable=False, activation_allowed=False, execution_order_proven=False)
    return manifest, raw


def build(root=ROOT, *, job_keys=None):
    manifest, raw = expected(root, job_keys=job_keys)
    target = unlinked_path(root / OUTPUT / manifest['fingerprint'])
    if not target.exists():
        target.mkdir(parents=True)
        (target / 'subtree-probe.lua').write_bytes(raw)
        write_json(target / 'manifest.json', manifest)
    verify(target, root)
    return target, manifest


def verify(target, root=ROOT):
    target = unlinked_path(target)
    saved = json.loads((target / 'manifest.json').read_bytes())
    manifest, raw = expected(root, job_keys=[job['key'] for job in saved['jobs']] if saved['jobs'] else None)
    assert target == unlinked_path(root / OUTPUT / manifest['fingerprint'])
    assert {p.name for p in target.iterdir()} == {'manifest.json', 'subtree-probe.lua'}
    assert json.loads((target / 'manifest.json').read_bytes()) == manifest
    assert (target / 'subtree-probe.lua').read_bytes() == raw
    return manifest, raw


def object_path(full):
    assert len(full) <= 2048
    match = FULL.fullmatch(full)
    assert match, 'exact native object name required'
    return match[2]


def analyze(lines, manifest, *, allow_incomplete=False):
    """Keep exact closed jobs; partial mode permits only a valid sequence ending at EOF.

    The interrupted job exports no graph, including trees that closed within it.
    Default callers still require the complete batch and its original END event.
    """
    expected_jobs = manifest['jobs']
    results, started, ended, active, tree = [], False, False, None, None
    batch_nodes = batch_refs = 0
    for line in lines:
        if PREFIX not in line:
            continue
        event, separator, value = line.split(PREFIX, 1)[1].rstrip('\r\n').partition('=')
        assert separator and not ended, 'event after subtree batch closure'
        parts = value.split('|')
        if event == 'START':
            assert not started and value == manifest['fingerprint']
            started = True
            continue
        assert started, 'subtree event before batch'
        if event == 'END':
            assert value == manifest['fingerprint'] and active is None and len(results) == len(expected_jobs)
            ended = True
            continue
        if event == 'JOB_BEGIN':
            assert active is None and len(results) < len(expected_jobs)
            job = expected_jobs[len(results)]
            assert parts == [job['key'], job['id'], job['path']], 'ordered exact subtree jobs required'
            active = dict(key=job['key'], id=job['id'], parent_class=job['path'], trees=[],
                          metadata_only=True, playable=False, execution_order_proven=False,
                          activation_verified=False, native_grant_verified=False)
            tree = None
            continue
        assert active and parts[0] == active['key'], 'foreign or orphan subtree event'
        if event == 'REJECTED':
            assert len(parts) == 2 and 0 < len(parts[1]) <= 1024
            active.update(mapping_observed=False, rejection=parts[1],
                          discarded_tree_count=len(active['trees']) + int(tree is not None), trees=[])
            results.append(active); active = tree = None
            continue
        if event == 'JOB_END':
            assert len(parts) == 2 and tree is None and parts[1] == str(len(active['trees']))
            active['mapping_observed'] = True
            active['referenced_ability_classes'] = sorted({object_path(r['value']) for t in active['trees']
                for r in t['references'] if r['property'] == 'AbilityToActivate'})
            results.append(active); active = None
            continue
        if event == 'TREE':
            assert len(parts) == 4 and tree is None and parts[1] == str(len(active['trees']) + 1)
            assert len(active['trees']) < 32 and OBJECT.fullmatch(parts[2])
            assert parts[2] not in {t['path'] for t in active['trees']}
            weight = float(parts[3]); assert math.isfinite(weight)
            tree = dict(path=parts[2], weight=weight, nodes=[], references=[], edges=[])
            continue
        assert tree and len(parts) >= 2 and parts[1] == str(len(active['trees']) + 1)
        if event == 'NODE':
            assert len(parts) == 3 and parts[2] not in tree['nodes']
            assert object_path(parts[2]).startswith(tree['path'] + ':'), 'foreign tree node'
            tree['nodes'].append(parts[2]); batch_nodes += 1
            assert len(tree['nodes']) <= 128 and sum(len(t['nodes']) for t in active['trees']) + len(tree['nodes']) <= 256
            assert batch_nodes <= 4096
        elif event == 'REF':
            assert len(parts) == 5 and parts[2] in tree['nodes']
            assert re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', parts[3])
            object_path(parts[4])
            if parts[3] == 'AbilityToActivate':
                assert parts[4].split(' ', 1)[0] in (
                    'Class', 'BlueprintGeneratedClass', 'LegoAbilityBlueprintGeneratedClass')
                assert OBJECT.fullmatch(object_path(parts[4])), 'exact referenced ability class required'
            assert (parts[2], parts[3]) not in {(r['node'], r['property']) for r in tree['references']}
            tree['references'].append(dict(node=parts[2], property=parts[3], value=parts[4]))
            batch_refs += 1
            assert sum(len(t['references']) for t in active['trees']) + len(tree['references']) <= 1024
            assert batch_refs <= 16384
        elif event == 'EDGE':
            assert len(parts) == 6 and parts[2] in tree['nodes']
            assert object_path(parts[3]).startswith(tree['path'] + ':')
            assert parts[4] in ('ChildTask', 'ChildComposite') and re.fullmatch(r'[1-9]\d{0,2}', parts[5])
            assert int(parts[5]) <= 128 and len(tree['edges']) < 256
            assert (parts[2], parts[4], int(parts[5])) not in {(e['parent'], e['kind'], e['index']) for e in tree['edges']}
            tree['edges'].append(dict(parent=parts[2], child=parts[3], kind=parts[4], index=int(parts[5])))
        elif event == 'TREE_END':
            assert len(parts) == 5 and parts[2:] == list(map(str, (len(tree['nodes']), len(tree['references']), len(tree['edges']))))
            assert tree['nodes'] and all(e['child'] in tree['nodes'] for e in tree['edges'])
            reachable = {tree['nodes'][0]}
            for _ in tree['nodes']:
                reachable.update(e['child'] for e in tree['edges'] if e['parent'] in reachable)
            assert reachable == set(tree['nodes']), 'disconnected node declarations'
            active['trees'].append(tree); tree = None
        else:
            raise AssertionError('unknown or stopped subtree event: ' + event)
    assert started, 'subtree batch start required'
    if allow_incomplete:
        return dict(batch_complete=ended, outcomes=results,
                    interrupted_job=active['key'] if active else None,
                    discarded_open_tree_count=(len(active['trees']) + int(tree is not None)) if active else 0,
                    unstarted_job_keys=[job['key'] for job in expected_jobs[len(results) + int(active is not None):]])
    assert ended and active is None, 'complete subtree batch required'
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', help='Closed interrupted session for missing-only continuation')
    parser.add_argument('--previous-batch', type=Path)
    parser.add_argument('--limit', type=int, default=32)
    args = parser.parse_args()
    assert bool(args.session) == bool(args.previous_batch), 'session and previous batch must be supplied together'
    assert 1 <= args.limit <= MAX_STAGE_JOBS, 'bounded continuation contains 1 to 96 jobs'
    keys = None
    if args.session:
        from collect_boss_subtree_progress import history, replay, unstarted_keys
        progress = replay(args.session, args.previous_batch)
        assert not progress['batch_complete'], 'complete batches use the normal collection workflow'
        keys = unstarted_keys(progress, history())[:args.limit]
        assert keys, 'no unstarted jobs; rejected and interrupted jobs require separate review'
    directory, manifest = build(job_keys=keys)
    print(json.dumps(dict(directory=str(directory), queries=len(manifest['jobs']), game_started=False,
                          playable=False, execution_order_proven=False), ensure_ascii=False, indent=2))
