"""Reconcile observed Boss assets, closed-session grants and v5 skill mappings offline."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

import boss_metadata_jobs as metadata
from boss_adaptation_workflow import BUILD, ROOT, sha, write_json
from build_boss_profile_candidate import lua
from collect_boss_metadata_jobs import batch_lines, repository_path, verify_receipt
from native_grant_metadata_workflow import verify_receipt as verify_grant_receipt


CATALOG = 'research/boss-adaptation/catalog.json'
RELEASE = 'releases/ahua-boss-workbench-v5-3f29975fe3b8826f'
OUTPUT = 'runtime/boss-offline-inventory'
QUERY_LABEL = 'boss-inventory-metadata'
EVENT = re.compile(r'\[Lua\] PBZ_CONTROL_LIFECYCLE:([A-Z_]+)=(.*)$')
OBJECT = re.compile(r'/[A-Za-z0-9_/]+\.[A-Za-z0-9_]+')
GRANT = re.compile(r'[A-Za-z0-9_]+ (/[A-Za-z0-9_/]+\.[A-Za-z0-9_]+)')
FIELD = re.compile(r'''(?:\["class_path"\]|\bclass_path)\s*=\s*["']([^"']+)["']''')
CONFIG = re.compile(r'''(?:\["config_path"\]|\bconfig_path)\s*=\s*["']([^"']+)["']''')
ACTOR_CDO = re.compile(r'class_default\|object=([A-Za-z0-9_]+_C) (/[A-Za-z0-9_/]+)\.Default__([A-Za-z0-9_]+_C)\|.*')
BOUNDARIES = {'SPAWN_ATTEMPT', 'INTERACTIVE_READY', 'ISSUE_READY', 'CANDIDATE_LIVE_BINDING', 'END'}
DOMAINS = {
    '071_xianzhe': ('GA_XianZhe_Skill_01_C', 'GA_XianZhe_CA_C'),
    '067_motian': ('GA_MoTian_Dodge_F_02_C', 'GA_MoTian_Dodge_R_02_C',
                   'GA_MoTian_Dodge_L_02_C', 'GA_MoTian_Dodge_B_03_C'),
    '058_maddoctor': ('GA_MadDoctor_SpecialAttack_01_C', 'GA_MadDoctor_SpecialAttack_02_4Wave_C',
                      'GA_MadDoctor_Dodge_B_C', 'GA_MadDoctor_Dodge_R_C'),
}
SUPPLEMENTAL_PRIORITY = ('057_wanjun', '071_xianzhe', '056_youlong', '058_maddoctor', '073_yanqiansui', '042_ahua')


def read(path):
    return json.loads(Path(path).read_bytes())


def grant_snapshots(lines, folders, profiles=()):
    """Join only complete ordered grant dumps to their exact spawn identity."""
    published = {row['actor']: (row['folder'], row['actor'], row['config'], 'spawn_cdo_and_v5_config') for row in profiles}
    identity = None
    count = None
    values = []
    first_line = 0
    spawning = False
    for line_number, line in enumerate(lines, 1):
        event = EVENT.search(line)
        if event is None:
            continue
        key, value = event.groups()
        if key != 'GRANTED_ABILITY' and count is not None:
            if count == len(values) and identity is not None:
                yield dict(id=identity[0], actor=identity[1], config=identity[2], identity_source=identity[3],
                           grant_count_line=first_line, grants=dict(sorted(Counter(values).items())))
            count = None
            values = []
            identity = None
        if key in BOUNDARIES:
            identity = None
            spawning = key == 'SPAWN_ATTEMPT'
        elif key == 'CANDIDATE_IDENTITY_READY':
            parts = value.split('|')
            folder = folders.get(parts[0])
            prefix = f'/PBZCombatAsset/ActorData/Mobs/{folder}/'
            identity = None
            if (spawning and len(parts) == 3 and folder and parts[1].endswith('_C')
                    and all(path.startswith(prefix) and OBJECT.fullmatch(path) for path in parts[1:])):
                identity = (*parts, 'explicit_candidate_identity')
            spawning = False  # a second identity cannot replace this spawn's identity
        elif key == 'SPAWN_STATE' and (spawning or identity is not None) and value.startswith('class_default|'):
            match = ACTOR_CDO.fullmatch(value)
            actor = None
            if match and match[1] == match[3]:
                actor = match[2] + '.' + match[1]
            if identity is None:
                identity = published.get(actor)
            elif identity[1] != actor:
                identity = None
            spawning = False
        elif key == 'GRANTED_COUNT' and identity is not None:
            if re.fullmatch(r'[1-9]\d{0,2}', value) and int(value) <= 512:
                count = int(value)
                first_line = line_number
            else:
                identity = None
        elif key == 'GRANTED_ABILITY' and count is not None:
            match = GRANT.fullmatch(value)
            if match and len(values) < count:
                values.append(match[1])
            else:
                count = None
                identity = None
                values = []


def historical_grants(root, folders, roster, sources):
    snapshots = []
    ignored = Counter()
    directory = root / 'evidence/official-validation'
    for log in sorted(directory.glob('*/UE4SS.log')):
        session = log.parent.name
        if not re.fullmatch(r'\d{8}-\d{6}', session):
            continue
        log = repository_path(root, log.relative_to(root).as_posix())
        with log.open(encoding='utf-8', errors='replace') as stream:
            results = list(grant_snapshots(stream, folders, roster.values()))
        if not results:
            continue
        state_path = repository_path(root, f'runtime/official-validation-{session}/state.json')
        post_path = repository_path(root, f'evidence/official-validation/{session}/postcheck.json')
        if not state_path.is_file() or not post_path.is_file():
            ignored['missing closure files'] += 1
            continue
        if not closed(state_path, post_path, log.parent):
            ignored['closure checks did not pass'] += 1
            continue
        for path in (log, state_path, post_path):
            sources[path.relative_to(root).as_posix()] = sha(path)
        snapshots.extend(dict(row, session=session) for row in results)
    return snapshots, dict(ignored)


def closed(state_path, post_path, work):
    state, post = read(state_path), read(post_path)
    return (state.get('restored') is True and Path(state.get('work', '')).resolve() == work
            and post.get('validation_state') == str(state_path)
            and all(post.get(key) is True for key in ('validation_restored', 'research_box_empty',
                    'research_loader_removed', 'host_registry_unchanged'))
            and post.get('formal_files_changed') == [] and post.get('host_config_files_changed') == [])


def release_profiles(root, sources):
    manifest_path = root / RELEASE / 'pbz-release.json'
    manifest = read(manifest_path)
    assert manifest['exe_sha256'] == BUILD and manifest['release_id'] == Path(RELEASE).name
    sources[manifest_path.relative_to(root).as_posix()] = sha(manifest_path)
    roster = {}
    for boss in manifest['bosses']:
        identifier = boss['id']
        profile = 'ahua' if identifier == 'ahua_guitoudao' else identifier.split('_', 1)[1]
        relative = f'PBZBossControl/Scripts/profiles/{profile}.lua'
        path = root / RELEASE / relative
        digest = sha(path)
        assert manifest['files'][relative] == digest
        sources[path.relative_to(root).as_posix()] = digest
        text = path.read_text(encoding='utf-8')
        class_paths = set(FIELD.findall(text))
        skills = {p for p in class_paths if OBJECT.fullmatch(p) and p.rsplit('.', 1)[1].startswith('GA_')}
        actors = class_paths - skills
        assert len(skills) == boss['abilities'] and len(actors) == 1, identifier
        actor, = actors
        config, = CONFIG.findall(text)
        folder = actor.split('/')[4].casefold()
        assert OBJECT.fullmatch(config) and config.split('/')[4].casefold() == folder
        roster[folder] = dict(boss, actor=actor, config=config, folder=folder, skills=sorted(skills))
    return roster


def observations(root, sources):
    indexed = defaultdict(list)
    for directory, verify in (('adapter-metadata-receipts', verify_receipt),
                              ('native-grant-metadata-receipts', verify_grant_receipt)):
        for path in sorted((root / 'research/boss-adaptation' / directory).glob('*.json')):
            receipt = verify(path, root)
            name = path.relative_to(root).as_posix()
            sources[name] = sha(path)
            for row in receipt['outcomes']:
                indexed[row['id'], row['class_path']].append(dict(row, receipt=name))
    return indexed


def observation_state(rows, fields):
    successful = [row for row in rows if row['metadata_verified']]
    values = {metadata.canonical({key: row[key] for key in fields}) for row in successful}
    if len(values) > 1:
        return 'conflict', None
    if successful:
        return 'verified', {key: successful[0][key] for key in fields}
    return ('rejected' if rows else 'unqueried'), None


def special_ability(path):
    # These names are review hints. Treating them as normal combat input can
    # select phase/stance transitions or utilities instead of a player move.
    return any(part in path.casefold() for part in
               ('/passive/', '/retarget/', '/child/', '/grab/', 'switchphase', '_stance', '_passive', 'resurrect'))


def plan(catalog, receipts, snapshots, roster):
    historical = defaultdict(list)
    for snapshot in snapshots:
        historical[snapshot['id']].append(snapshot)
    rows = []
    priorities = {}
    for candidate in catalog['candidates']:
        identifier, folder = candidate['id'], candidate['resource_folder']
        if folder == 'Common':
            continue
        released = roster.get(identifier)
        installed = set(released['skills']) if released else set()
        known_actors = defaultdict(set)
        grants = defaultdict(list)
        prefix = f'/PBZCombatAsset/ActorData/Mobs/{folder}/'
        for snapshot in historical[identifier]:
            actor, config = snapshot['actor'], snapshot['config']
            known_actors[actor].add(config)
            for path, count in snapshot['grants'].items():
                grants[path].append(dict(actor=actor, config=config, session=snapshot['session'],
                                         identity_source=snapshot['identity_source'],
                                         grant_count_line=snapshot['grant_count_line'], count=count))
        jobs = metadata.jobs_for(candidate)
        variants = []
        ability_jobs = {job['lookup_path']: job for job in jobs if job['role'] == 'ability'}
        for job in jobs:
            if job['role'] != 'character':
                continue
            path = job['lookup_path']
            history = receipts.get((identifier, path), [])
            state, fact = observation_state(history, ('observed_config', 'display_name', 'lineage'))
            variants.append(dict(path=path, metadata=state, observation=fact,
                                 spawn_configs=sorted(known_actors.pop(path, ())),
                                 receipts=sorted({x['receipt'] for x in history})))
            if (state in ('unqueried', 'rejected') and not variants[-1]['spawn_configs']
                    and (not released or released['actor'] != path)):
                # Review already observed combat variants and config pairs first.
                priorities[job['key']] = 1 if job['config_candidates'] else 2
        variants.extend(dict(path=path, metadata='unqueried', observation=None,
                             spawn_configs=sorted(configs), receipts=[])
                        for path, configs in sorted(known_actors.items()))
        # Receipts from exact grants may contain classes the FName catalog missed.
        supplemental = {path for owner, path in receipts if owner == identifier
                        and any(row['role'] == 'ability' for row in receipts[owner, path])}
        abilities = []
        for path in sorted(set(ability_jobs) | set(grants) | installed | supplemental):
            history = receipts.get((identifier, path), [])
            state, fact = observation_state(history, ('ability_kind',))
            is_local = path.startswith(prefix) and path.rsplit('.', 1)[1].startswith('GA_')
            unique_grant = any(x['count'] == 1 for x in grants[path])
            if path in installed:
                route = 'in_v5_profile'
            elif not is_local or special_ability(path):
                route = 'utility_or_dependency_review'
            elif state == 'conflict' or (fact and fact['ability_kind'] != 'leaf'):
                route = 'metadata_or_subtree_review'
            elif unique_grant and fact:
                route = 'leaf_with_historical_grant'
            elif unique_grant:
                route = 'exact_grant_needs_metadata'
            elif grants[path]:
                route = 'duplicate_grant_review'
            else:
                route = 'needs_variant_grant'
            abilities.append(dict(path=path, catalog_clue=path in ability_jobs, v5_skill=path in installed,
                                  metadata=state, kind=fact['ability_kind'] if fact else None,
                                  grants=grants[path], receipts=sorted({x['receipt'] for x in history}), route=route))
        rows.append(dict(id=identifier, folder=folder, v5_id=released['id'] if released else None,
                         variants=variants, abilities=abilities,
                         historical_snapshot_count=len(historical[identifier])))
    candidates = [c for c in catalog['candidates'] if not c['reference_only'] and c['resource_folder'] != 'Common']
    selected_keys = {job['key'] for candidate in candidates for job in metadata.jobs_for(candidate)}
    batches = [batch for priority in (1, 2) for batch in metadata.batches(candidates,
               [key for key, value in priorities.items() if value == priority and key in selected_keys])]
    return rows, batches


def prepare_skill_pools(rows, sources, target, root):
    """Generate exact variant-bound developer modules for the reviewed moves."""
    prepared = []
    module_path = root / 'tools/boss_developer_candidate.lua'
    for row in rows:
        identifier = row['id']
        if identifier not in DOMAINS:
            continue
        abilities, compatible = [], None
        for short in DOMAINS[identifier]:
            matches = [a for a in row['abilities'] if a['path'].rsplit('.', 1)[1] == short
                       and a['route'] == 'leaf_with_historical_grant']
            if len(matches) != 1:
                break
            ability, = matches
            variants = {(g['actor'], g['config']) for g in ability['grants'] if g['count'] == 1}
            compatible = variants if compatible is None else compatible & variants
            abilities.append(ability)
        if len(abilities) != len(DOMAINS[identifier]) or len(compatible) != 1:
            continue
        actor, config = next(iter(compatible))
        variants = [v for v in row['variants'] if v['path'] == actor and v['observation']
                    and v['observation']['observed_config'] == config]
        if len(variants) != 1:
            continue
        variant, = variants
        display_name = variant['observation']['display_name']
        assert display_name not in ('None', 'NA', 'N/A', '') and variant['receipts']
        identity_inputs = {p: sources[p] for p in variant['receipts']}
        ability_inputs = {p: sources[p] for a in abilities for p in a['receipts']}
        pool = [a['path'] for a in abilities]
        definition = dict(id=identifier, class_path=actor, config_path=config, display_name=display_name,
                          ability_pool=pool,
                          identity_receipt_sha256=hashlib.sha256(metadata.canonical(identity_inputs)).hexdigest(),
                          ability_metadata_receipt_sha256=hashlib.sha256(metadata.canonical(ability_inputs)).hexdigest())
        directory = target / 'skill-pools' / identifier
        directory.mkdir(parents=True, exist_ok=True)
        module = ('local definition=' + lua(definition) + '\n').encode() + module_path.read_bytes()
        (directory / 'boss_candidate.lua').write_bytes(module)
        write_json(directory / 'manifest.json', dict(definition=definition, identity_receipts=identity_inputs,
                   ability_receipts=ability_inputs, historical_unique_grants={a['path']: a['grants'] for a in abilities},
                   module_sha256=hashlib.sha256(module).hexdigest(), playable=False, runtime_verified=False,
                   build=BUILD, activation_allowed=False))
        prepared.append(dict(id=identifier, skills=pool, directory=directory.relative_to(root).as_posix(),
                             manifest_sha256=sha(directory / 'manifest.json')))
    return prepared


def exact_requests(rows):
    """Group exact grants together regardless of coverage in the name catalog."""
    groups = {}
    for character in rows:
        jobs = []
        for ability in character['abilities']:
            path = ability['path']
            if ability['route'] != 'exact_grant_needs_metadata':
                continue
            assert OBJECT.fullmatch(path) and path.endswith('_C')
            job = dict(id=character['id'], role='ability', lookup_path=path,
                       package=path.split('.', 1)[0], config_candidates=[],
                       historical_grants=[g for g in ability['grants'] if g['count'] == 1])
            job['key'] = hashlib.sha256(metadata.canonical(job)).hexdigest()[:20]
            jobs.append(job)
        if jobs:
            groups[character['id']] = jobs
    rank = {identifier: index for index, identifier in enumerate(SUPPLEMENTAL_PRIORITY)}
    batches = []
    for identifier in sorted(groups, key=lambda value: (rank.get(value, len(rank)), value)):
        for job in groups[identifier]:
            if (not batches or len(batches[-1]) >= 64
                    or len({entry['id'] for entry in [*batches[-1], job]}) > 3):
                batches.append([])
            batches[-1].append(job)
    return batches


def exact_payload(jobs, inventory_key):
    manifest = dict(schema=1, target_build_sha256=BUILD, inventory=inventory_key, jobs=jobs,
                    metadata_only=True, runtime_verified=False, activation_allowed=False)
    fingerprint = hashlib.sha256(metadata.canonical(manifest)).hexdigest()[:20]
    raw = metadata.render(jobs, fingerprint).encode()
    return dict(manifest, fingerprint=fingerprint, script_sha256=hashlib.sha256(raw).hexdigest()), raw


def captured_metadata(root, sources, receipts, snapshots):
    """Reuse complete metadata from closed carriers after replaying the original log."""
    grant_index = set()
    for snapshot in snapshots:
        for path, count in snapshot['grants'].items():
            if count == 1:
                grant_index.add((snapshot['id'], path, snapshot['actor'], snapshot['config'], snapshot['session'],
                                 snapshot['grant_count_line'], snapshot['identity_source']))
    results = (root / 'evidence/official-validation').glob(f'*/{QUERY_LABEL}-*-results.json')
    for result_path in sorted(results):
        result_path = repository_path(root, result_path.relative_to(root).as_posix())
        work = result_path.parent
        if not re.fullmatch(r'\d{8}-\d{6}', work.name):
            continue
        state_path = root / 'runtime' / ('official-validation-' + work.name) / 'state.json'
        post_path = work / 'postcheck.json'
        if not state_path.is_file() or not post_path.is_file() or not closed(state_path, post_path, work):
            continue
        result = read(result_path)
        fingerprint = result['batch']
        assert re.fullmatch(r'[0-9a-f]{20}', fingerprint)
        base = work / f'{QUERY_LABEL}-{fingerprint}'
        assert result_path == base.with_name(base.name + '-results.json')
        manifest_path = base.with_name(base.name + '-manifest.json')
        script_path = base.with_name(base.name + '-metadata.lua')
        stage_path = base.with_name(base.name + '-staged.json')
        stage, manifest = read(stage_path), read(manifest_path)
        assert stage == read(base.with_name(base.name + '-intent.json'))
        assert stage['metadata_only'] is True and stage['input_sent'] is False
        assert stage['state_file'] == result['state_file'] == str(state_path)
        assert stage['research_pid'] == result['research_pid'] and stage['batch'] == fingerprint
        expected, script = exact_payload(manifest['jobs'], manifest['inventory'])
        assert manifest == expected and script_path.read_bytes() == script
        assert manifest['fingerprint'] == fingerprint and stage['script_sha256'] == manifest['script_sha256']
        for job in manifest['jobs']:
            assert job['role'] == 'ability' and job['historical_grants']
            assert job['key'] == hashlib.sha256(metadata.canonical(
                {key: value for key, value in job.items() if key != 'key'})).hexdigest()[:20]
            for grant in job['historical_grants']:
                key = (job['id'], job['lookup_path'], grant['actor'], grant['config'], grant['session'],
                       grant['grant_count_line'], grant['identity_source'])
                assert grant['count'] == 1 and key in grant_index, 'historical grant evidence changed'
        log_path = work / 'UE4SS.log'
        raw = log_path.read_bytes()
        offset = stage['log_byte_offset']
        assert type(offset) is int and 0 <= offset <= len(raw)
        assert hashlib.sha256(raw[:offset]).hexdigest() == stage['log_prefix_sha256']
        lines = batch_lines(raw[offset:].decode('utf-8'), fingerprint)
        assert lines == result['lines'] == batch_lines(raw.decode('utf-8'), fingerprint)
        outcomes = metadata.analyze(lines, dict(batch_fingerprint=fingerprint, jobs=manifest['jobs']))
        assert outcomes == result['outcomes'] and result['metadata_only'] is True and result['playable'] is False
        receipt = result_path.relative_to(root).as_posix()
        for path in (result_path, manifest_path, script_path, stage_path, log_path, state_path, post_path):
            sources[path.relative_to(root).as_posix()] = sha(path)
        for outcome in outcomes:
            receipts[outcome['id'], outcome['class_path']].append(dict(outcome, receipt=receipt))


def write_exact_batches(rows, target, root, inventory_key):
    result = []
    for jobs in exact_requests(rows):
        manifest, raw = exact_payload(jobs, inventory_key)
        fingerprint = manifest['fingerprint']
        directory = target / 'exact-grant-metadata' / fingerprint
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'metadata-probe.lua').write_bytes(raw)
        write_json(directory / 'manifest.json', manifest)
        result.append(dict(directory=directory.relative_to(root).as_posix(), requests=len(jobs),
                           manifest_sha256=sha(directory / 'manifest.json')))
    return result


def inputs(root):
    root = root.resolve()
    sources = {path: sha(root / path) for path in (CATALOG, 'tools/boss_offline_inventory.py',
               'tools/boss_developer_candidate.lua', 'tools/build_boss_profile_candidate.py',
               'tools/boss_metadata_jobs.py', 'tools/collect_boss_metadata_jobs.py',
               'tools/native_grant_metadata_workflow.py', 'tools/stage_boss_inventory_metadata.py',
               'tests/test_boss_offline_inventory.py')}
    catalog = read(root / CATALOG)
    assert catalog['target_build_sha256'] == BUILD
    for row in catalog['sources']:
        assert row['path'].startswith('evidence/')
        assert sha(repository_path(root, row['path'])) == row['sha256']
    roster = release_profiles(root, sources)
    assert all(row['id'] in {c['id'] for c in catalog['candidates']} for row in roster.values() if row['id'] != 'ahua_guitoudao')
    receipts = observations(root, sources)
    folders = {c['id']: c['resource_folder'] for c in catalog['candidates']}
    snapshots, ignored = historical_grants(root, folders, roster, sources)
    captured_metadata(root, sources, receipts, snapshots)
    rows, batches = plan(catalog, receipts, snapshots, roster)
    identity = dict(schema=1, target_build_sha256=BUILD, sources=sources, characters=rows,
                    queued_job_keys=[[job['key'] for job in batch] for batch in batches],
                    runtime_acceptance_current=False, game_started=False, installed=False)
    return identity, catalog, roster, snapshots, ignored, batches


def build(root=ROOT):
    root = root.resolve()
    identity, catalog, roster, snapshots, ignored, batches = inputs(root)
    rows, sources = identity['characters'], identity['sources']
    routes = Counter(row['route'] for character in rows for row in character['abilities'])
    assert routes['in_v5_profile'] == sum(len(boss['skills']) for boss in roster.values())
    key = hashlib.sha256(metadata.canonical(identity)).hexdigest()[:20]
    target = root / OUTPUT / key
    skill_pools = prepare_skill_pools(rows, sources, target, root)
    exact_batches = write_exact_batches(rows, target, root, key)
    # Materialize only the first priority group. The rest are deterministic
    # requests; preserving a bounded set avoids dozens of unnecessary reloads.
    prepared = metadata.freeze(batches[0], target / 'metadata', root) if batches else None
    first_exact = read(root / exact_batches[0]['directory'] / 'manifest.json') if exact_batches else None
    next_jobs = {job['lookup_path'] for job in first_exact['jobs']} if first_exact else set()
    leaf_reviews, metadata_gaps, variant_review = [], [], []
    for character in rows:
        for variant in character['variants']:
            observed = variant['observation']
            if observed and observed['display_name'] not in ('None', 'N/A', 'NA', '') and not variant['spawn_configs']:
                variant_review.append(dict(id=character['id'], actor=variant['path'],
                                           display_name=observed['display_name'], config=observed['observed_config']))
        for ability in character['abilities']:
            route = ability['route']
            entry = dict(id=character['id'], path=ability['path'],
                         grant_variants=sorted({(grant['actor'], grant['config']) for grant in ability['grants']
                                                if grant['count'] == 1}))
            if route == 'leaf_with_historical_grant':
                leaf_reviews.append(dict(entry, disposition='review exact variant before candidate activation'))
            elif route == 'exact_grant_needs_metadata':
                metadata_gaps.append(dict(entry, in_catalog=ability['catalog_clue'], in_first_batch=ability['path'] in next_jobs))
    report = dict(fingerprint=key, resource_folders=len(catalog['candidates']), character_folders=len(rows),
                  variants=sum(len(x['variants']) for x in rows), catalog_ability_clues=sum(
                      x['catalog_clue'] for row in rows for x in row['abilities']),
                  historical_grant_snapshots=len(snapshots), historical_sessions=len({x['session'] for x in snapshots}),
                  ignored_sessions=ignored, v5_profiles=len(roster), ability_routes=dict(routes),
                  queued_character_requests=sum(map(len, batches)), queued_character_batches=len(batches),
                  first_character_batch=prepared.relative_to(root).as_posix() if prepared else None,
                  first_batch=exact_batches[0]['directory'] if exact_batches else None,
                  first_batch_requests=len(next_jobs), leaf_review_queue=leaf_reviews, exact_grant_metadata_gaps=metadata_gaps,
                  skill_pools=skill_pools, exact_grant_batches=exact_batches, named_variants_for_grant_review=variant_review,
                  game_started=False, installed=False, new_playable_bosses=0)
    write_json(target / 'inventory.json', dict(identity, summary=report))
    write_json(target / 'summary.json', report)
    return target, report


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    directory, summary = build()
    print(json.dumps(dict(directory=str(directory), **{k: v for k, v in summary.items() if not isinstance(v, list)}),
                     ensure_ascii=False, indent=2))
