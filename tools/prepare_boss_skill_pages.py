"""Freeze four-slot skill pages from exact closed native grants and leaf metadata.

Pages are developer experiments. They neither register player characters nor
activate abilities. A page is usable only when every listed native grant is
present, unique and idle in the current research process.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import boss_metadata_jobs as metadata
import boss_offline_inventory as inventory
from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from build_boss_profile_candidate import lua
from collect_boss_identity import analyze as identity_outcomes
from collect_boss_metadata_jobs import repository_path


REVIEWED_ROLES = ('056_youlong', '057_wanjun', '058_maddoctor',
                  '067_motian', '071_xianzhe', '073_yanqiansui')
SOURCES = ('tools/prepare_boss_skill_pages.py', 'tools/boss_developer_candidate.lua',
           'tests/test_boss_skill_pages.py')


def deferred_reason(path):
    short = path.rsplit('.', 1)[-1].casefold()
    if inventory.special_ability(path):
        return 'utility, phase or dependency needs separate review'
    if '_gex' in short or '_ca_' in short:
        return 'counter-context ability needs a separately verified native trigger'
    if any(token in short for token in ('passive', 'subtitle', 'ritualistheal', 'frontrecovery', 'summon')):
        return 'passive, story, heal, recovery or summon needs separate review'
    # The earlier closed attempt observed this exact move leaving the local
    # training area by over 1.6 km. New leaf metadata cannot erase that failure.
    if short == 'ga_yanqiansui_skill_01_c':
        return 'historical nonlocal displacement; scene dependency unresolved'
    return None


def closed_identities(root, sources):
    """Replay old exact CDO pairs instead of deriving config paths from names."""
    found = defaultdict(list)
    directory = root / 'research/boss-adaptation/identity-receipts'
    for path in sorted(directory.glob('*.json')):
        receipt = inventory.read(path)
        assert receipt['target_build_sha256'] == BUILD and receipt['metadata_only'] is True
        assert receipt['playable'] is False
        inputs = {}
        for relative, expected in receipt['sources'].items():
            name = relative.replace('\\', '/')
            source = repository_path(root, name)
            assert sha(source) == expected, 'identity evidence changed: ' + name
            inputs[name] = expected
        session = receipt['session']
        state = root / f'runtime/official-validation-{session}/state.json'
        work = root / 'evidence/official-validation' / session
        assert inventory.closed(state, work / 'postcheck.json', work)
        manifests = [name for name in inputs if name.endswith('/identity-probe-manifest.json')]
        assert len(manifests) == 1
        manifest = inventory.read(root / manifests[0])
        result = inventory.read(work / 'multi-boss-identity-results.json')
        assert manifest['target_build_sha256'] == BUILD
        assert result['state_file'] == str(state) and result['metadata_only'] is True
        assert result['script_sha256'] == manifest['script_sha256']
        assert result['batch_manifest_sha256'] == manifest['batch_manifest_sha256']
        raw = (work / 'UE4SS.log').read_text(encoding='utf-8', errors='replace')
        cursor = 0
        for line in result['lines']:
            cursor = raw.index(line, cursor) + len(line)
        outcomes = identity_outcomes(result['lines'], manifest['requests'])
        assert outcomes == receipt['candidates'], 'identity replay differs'
        name = path.relative_to(root).as_posix()
        sources[name] = sha(path)
        sources.update(inputs)
        for row in outcomes:
            if row['identity_verified']:
                found[row['id'], row['class_path'], row['config_path']].append(
                    dict(display_name=row['display_name'], receipt=name))
    return found


def page_definitions(characters, identities, sources):
    pages, deferred = [], []
    for character in characters:
        identifier = character['id']
        if identifier not in REVIEWED_ROLES:
            continue
        groups = defaultdict(list)
        for ability in character['abilities']:
            if ability['route'] != 'leaf_with_historical_grant':
                continue
            path = ability['path']
            reason = deferred_reason(path)
            if reason:
                deferred.append(dict(id=identifier, path=path, reason=reason))
                continue
            assert ability['kind'] == 'leaf' and ability['metadata'] == 'verified' and ability['receipts']
            prefix = f"/PBZCombatAsset/ActorData/Mobs/{character['folder']}/"
            assert path.startswith(prefix) and inventory.OBJECT.fullmatch(path)
            variants = {(g['actor'], g['config']) for g in ability['grants'] if g['count'] == 1}
            for actor, config in sorted(variants):
                assert actor.startswith(prefix) and config.startswith(prefix)
                groups[actor, config].append(ability)
        for (actor, config), abilities in sorted(groups.items()):
            observations = []
            for variant in character['variants']:
                fact = variant['observation']
                if variant['path'] == actor and fact and fact['observed_config'] == config:
                    observations.extend(dict(display_name=fact['display_name'], receipt=receipt)
                                        for receipt in variant['receipts'])
            observations.extend(identities.get((identifier, actor, config), ()))
            names = {row['display_name'] for row in observations}
            if len(names) != 1 or names & {'', 'None', 'NA', 'N/A'}:
                deferred.extend(dict(id=identifier, path=a['path'], reason='missing or conflicting exact CDO identity')
                                for a in abilities)
                continue
            identity_inputs = {row['receipt']: sources[row['receipt']] for row in observations}
            ordered = sorted(abilities, key=lambda a: a['path'])
            assert len({a['path'] for a in ordered}) == len(ordered)
            for offset in range(0, len(ordered), 4):
                selected = ordered[offset:offset + 4]
                ability_inputs = {p: sources[p] for a in selected for p in a['receipts']}
                definition = dict(id=identifier, class_path=actor, config_path=config, display_name=next(iter(names)),
                    ability_pool=[a['path'] for a in selected], require_complete_pool=True,
                    identity_receipt_sha256=hashlib.sha256(metadata.canonical(identity_inputs)).hexdigest(),
                    ability_metadata_receipt_sha256=hashlib.sha256(metadata.canonical(ability_inputs)).hexdigest())
                page = hashlib.sha256(metadata.canonical(definition)).hexdigest()[:16]
                pages.append(dict(page=page, definition=definition, identity_receipts=identity_inputs,
                    ability_receipts=ability_inputs, historical_unique_grants={a['path']:
                        [g for g in a['grants'] if g['count'] == 1 and (g['actor'], g['config']) == (actor, config)]
                        for a in selected}))
    return pages, deferred


def write_pages(characters, identities, sources, target, root=ROOT):
    pages, deferred = page_definitions(characters, identities, sources)
    prepared = []
    for page in pages:
        definition = page['definition']
        directory = target / 'skill-pages' / definition['id'] / page['page']
        raw = ('local definition=' + lua(definition) + '\n').encode('utf-8')
        raw += (root / 'tools/boss_developer_candidate.lua').read_bytes()
        record = dict(page, source_files={p: sha(root / p) for p in SOURCES},
            module_sha256=hashlib.sha256(raw).hexdigest(), build=BUILD,
            playable=False, runtime_verified=False, activation_allowed=False)
        directory.mkdir(parents=True, exist_ok=True)
        for name, payload in (('boss_candidate.lua', raw),
                              ('manifest.json', (json.dumps(record, indent=2, ensure_ascii=False) + '\n').encode('utf-8'))):
            path = directory / name
            if path.exists():
                assert path.read_bytes() == payload, 'preserve changed skill page: ' + str(path)
            else:
                path.write_bytes(payload)
        prepared.append(dict(id=definition['id'], page=page['page'], skills=definition['ability_pool'],
                             directory=directory.relative_to(root).as_posix(), manifest_sha256=sha(directory / 'manifest.json')))
    return prepared, deferred


def inputs(root=ROOT):
    root = root.resolve()
    identity, *_ = inventory.inputs(root)
    sources = dict(identity['sources'])
    identities = closed_identities(root, sources)
    sources.update({name: sha(root / name) for name in SOURCES})
    key = hashlib.sha256(metadata.canonical(dict(inventory=identity, sources=sources))).hexdigest()[:20]
    return identity, identities, sources, key


def build(root=ROOT):
    root = root.resolve()
    identity, identities, sources, key = inputs(root)
    target = root / 'runtime/boss-skill-pages' / key
    pages, deferred = write_pages(identity['characters'], identities, sources, target, root)
    report = dict(fingerprint=key, pages=pages, deferred=deferred, source_sha256=sources,
                  game_started=False, installed=False, playable=False, all_boss_skills_complete=False)
    write_json(target / 'summary.json', report)
    return target, report


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    target, report = build()
    print(json.dumps(dict(directory=str(target), pages=len(report['pages']),
          skills=sum(len(p['skills']) for p in report['pages']), deferred=len(report['deferred']),
          game_started=False, installed=False), ensure_ascii=False, indent=2))
