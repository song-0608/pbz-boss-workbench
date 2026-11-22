"""Build fixed-slot development candidates from the closed complex Boss probe."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

import boss_metadata_jobs as metadata
import complex_boss_metadata as probe
import prepare_complex_boss_configuration as config
from boss_adaptation_workflow import BUILD, ROOT, sha, write_json
from boss_catalog_database import DATABASE, Catalog, check_identity, encode, verify as verify_database, write_complex_configs
from boss_combat_candidate_policy import ability_reason, deferred_reason
from boss_offline_inventory import read
from mod_installation import unlinked_path
from prepare_boss_variant_candidates import write_candidates
from research_storage import PROJECT_STORAGE


OUTPUT = 'runtime/complex-boss-candidates'
SLOTS = dict(zip(config.SLOT_KEYS, ('skill_01', 'heavy_01', 'skill_02', 'dash')))
SOURCES = ('tools/prepare_complex_boss_candidates.py', 'tools/prepare_boss_variant_candidates.py',
           'tools/boss_developer_candidate.lua', 'tools/boss_combat_candidate_policy.py')
REVIEWED_DASH = ('054_zuoshang', 'F4', '/PBZCombatAsset/ActorData/Mobs/054_ZuoShang/Ability/Abilities/'
                 'GA_ZuoShang_Dash_B.GA_ZuoShang_Dash_B_C')


def digest(value):
    return hashlib.sha256(metadata.canonical(value)).hexdigest()


def definitions(profiles, receipt):
    expected = [job for profile in profiles for job in profile['metadata_jobs']]
    outcomes = {row['key']: row for row in receipt['outcomes']}
    if receipt['jobs'] != expected or list(outcomes) != [job['key'] for job in expected]:
        raise ValueError('Closed probe does not match the configured exact jobs')
    entries, deferred = [], []
    evidence = digest(receipt)
    for profile in profiles:
        identifier, actor, actor_config = profile['id'], profile['class_path'], profile['config_path']
        if actor is None:
            deferred.append(dict(id=identifier, reason='combat_body_identity_unresolved'))
            continue
        character, *abilities = [outcomes[job['key']] for job in profile['metadata_jobs']]
        display = character.get('display_name', '').strip()
        if not (character['metadata_verified'] and character['role'] == 'character'
                and character['id'] == identifier and character['class_path'] == actor
                and character.get('observed_config') == actor_config and character.get('config_in_observed_candidates')
                and '/Script/Engine.Character' in character.get('lineage', ())
                and display.casefold() not in ('', 'none', 'n/a', 'na')):
            deferred.append(dict(id=identifier, reason='exact_native_character_metadata_unverified'))
            continue
        slots = profile['direct_controls']
        if (tuple(slot['key'] for slot in slots) != tuple(SLOTS) or len(abilities) != len(SLOTS)
                or len({slot['class_path'] for slot in slots}) != len(SLOTS)):
            deferred.append(dict(id=identifier, reason='incomplete_fixed_slots'))
            continue
        bindings = []
        for slot, observed in zip(slots, abilities):
            key, path = slot['key'], slot['class_path']
            reason = ability_reason(path)
            if (identifier, key, path) == REVIEWED_DASH:
                reason = deferred_reason(path)
            if (reason or not observed['metadata_verified'] or observed['role'] != 'ability'
                    or observed.get('ability_kind') != 'leaf' or observed['id'] != identifier
                    or observed['class_path'] != path or not slot['requires_native_grant']):
                deferred.append(dict(id=identifier, key=key, class_path=path,
                    reason=reason or 'exact_native_leaf_metadata_unverified'))
                break
            bindings.append(dict(key=key, skill=SLOTS[key], class_path=path, declared_by=slot['declared_by'],
                                 shared=slot['shared']))
        if len(bindings) != len(SLOTS):
            continue
        definition = dict(id=identifier, class_path=actor, config_path=actor_config,
            display_name=character['display_name'], ability_pool=[row['class_path'] for row in bindings],
            require_complete_pool=True, identity_receipt_sha256=digest([evidence, character]),
            ability_metadata_receipt_sha256=digest([evidence, abilities]))
        entries.append(dict(definition=definition, bindings=bindings, metadata_receipt_sha256=evidence,
            metadata_directory=receipt['directory'], metadata_session=receipt['session'],
            runtime_verified=False, playable=False, activation_allowed=False))
    return entries, deferred


def inputs(directory, session, root=ROOT):
    receipt = probe.closed_receipt(directory, session, root)
    current = config.plan(root)
    manifest = read(directory / 'manifest.json')
    if receipt['build'] != BUILD or manifest['configuration_sha256'] != digest(current):
        raise ValueError('Closed probe must cover the current serialized configuration')
    entries, deferred = definitions(current['profiles'], receipt)
    identity = dict(schema=1, build=BUILD, definitions=entries, deferred=deferred,
        source_sha256={name: sha(root / name) for name in SOURCES}, configuration_sha256=digest(current),
        metadata_receipt_sha256=digest(receipt), installed=False, playable=False)
    return identity, digest(identity)[:20]


def build(directory, session, root=ROOT):
    directory, root = unlinked_path(directory), unlinked_path(root)
    identity, key = inputs(directory, session, root)
    target = root / OUTPUT / key
    target.mkdir(parents=True, exist_ok=True)
    rows = write_candidates(identity, key, target, root)
    report = dict(identity, candidates=rows, fingerprint=key)
    summary = target / 'summary.json'
    if summary.exists():
        if read(summary) != report:
            raise ValueError('Frozen complex Boss candidate summary changed')
    else:
        write_json(summary, report)
    return target, report


def verify(directory, root=ROOT):
    directory, root = unlinked_path(directory), unlinked_path(root)
    if (directory.parent.parent.parent != root / OUTPUT or
            {p.name for p in directory.iterdir()} != {'manifest.json', 'boss_candidate.lua'}):
        raise ValueError('Exact complex Boss candidate directory required')
    record = read(unlinked_path(directory / 'manifest.json'))
    source = unlinked_path(root / record['metadata_directory'])
    if source.parent != root / probe.OUTPUT:
        raise ValueError('Exact complex Boss metadata directory required')
    identity, key = inputs(source, record['metadata_session'], root)
    if directory.parent.parent.name != key:
        raise ValueError('Complex Boss candidate fingerprint changed')
    entries = [entry for entry in identity['definitions'] if entry['definition']['id'] == directory.parent.name]
    if len(entries) != 1:
        raise ValueError('Complex Boss candidate lacks exact closed metadata')
    with TemporaryDirectory(dir=directory.parent.parent) as scratch:
        rows = write_candidates(dict(identity, definitions=entries), key, Path(scratch), root)
        [row] = rows
        expected = root / row['directory']
        if expected.name != directory.name or any(unlinked_path(directory / name).read_bytes() !=
                (expected / name).read_bytes() for name in ('manifest.json', 'boss_candidate.lua')):
            raise ValueError('Complex Boss candidate module or evidence changed')
    return record


def index_profiles(report, root=ROOT, storage=PROJECT_STORAGE):
    current = config.plan(root, storage)
    if digest(current) != report['configuration_sha256']:
        raise ValueError('Database index requires the matching complex Boss configuration')
    indexed = {item['definition']['id']: item for item in report['definitions']}
    rows = []
    for profile in current['profiles']:
        entry = indexed.get(profile['id'])
        payload = dict(profile, metadata_verified=entry is not None, native_grants_verified=False,
            display_name=entry['definition']['display_name'] if entry else None,
            bindings=entry['bindings'] if entry else [], metadata_receipt_sha256=report['metadata_receipt_sha256'])
        rows.append((profile['folder'], profile['class_path'], encode(payload)))
    database = unlinked_path(Path(storage) / DATABASE)
    catalog = Catalog(root, storage)
    verify_database(database, catalog)
    with closing(sqlite3.connect(database.as_uri() + '?mode=rw', uri=True)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        check_identity(db, catalog)
        write_complex_configs(db, rows)
    return verify_database(database, catalog)['complex_profiles']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('metadata', type=Path)
    parser.add_argument('--session', required=True)
    parser.add_argument('--index', action='store_true', help='Record the verified evidence in the Boss database')
    args = parser.parse_args()
    output, report = build(args.metadata, args.session)
    result = dict(directory=str(output), candidates=report['candidates'], deferred=report['deferred'])
    if args.index:
        result['indexed_profiles'] = index_profiles(report)
    print(json.dumps(result, ensure_ascii=False, indent=2))
