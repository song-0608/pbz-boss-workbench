"""Build metadata-first native-grant experiments for exact named character variants.

The output is not a player roster. Each module must still find its own unique,
idle native grants in the current process. No manual grants, gameplay input,
installation, spawning or activation is performed by this offline builder.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

import boss_metadata_jobs as metadata
import boss_offline_inventory as inventory
from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from build_boss_profile_candidate import lua
from mod_installation import unlinked_path
from prepare_boss_skill_pages import deferred_reason


OUTPUT = 'runtime/boss-variant-candidates'
SOURCES = ('tools/prepare_boss_variant_candidates.py', 'tests/test_boss_variant_candidates.py',
           'tools/boss_developer_candidate.lua', 'tools/prepare_boss_skill_pages.py')
ACTOR_CONTEXTS = ('_forseq', '_ending', '_tutorial', '_teaching', '_summon', '_phantom',
                  '_stuntdouble', '_preview', '_stand', '_npchelper', '_npc', '_base')


def ability_reason(path):
    reason = deferred_reason(path)
    if reason:
        return reason
    name = path.rsplit('.', 1)[-1].casefold()
    if any(token in name for token in ('_child', '_ged', '_bed', '_behit', '_qte', '_seq')):
        return 'child, victim or sequence context requires a separate trigger'
    if not re.search(r'(?:lightattack|middleattack|heavyattack|specialattack|dodge|skill)_', name):
        return 'not a reviewed independent combat-input family'
    return None


def definitions(characters, sources):
    prepared, deferred = [], []
    for character in characters:
        prefix = f"/PBZCombatAsset/ActorData/Mobs/{character['folder']}/"
        pool, ability_sources = [], {}
        for ability in character['abilities']:
            path = ability['path']
            if ability['metadata'] != 'verified' or ability['kind'] != 'leaf':
                continue
            assert path.startswith(prefix) and inventory.OBJECT.fullmatch(path), 'same-folder exact leaf required'
            reason = ability_reason(path)
            if reason:
                deferred.append(dict(id=character['id'], path=path, reason=reason))
                continue
            assert ability['receipts'], 'closed leaf metadata receipts required'
            pool.append(path)
            ability_sources.update({name: sources[name] for name in ability['receipts']})
        pool = sorted(set(pool))
        for variant in character['variants']:
            if variant['spawn_configs'] or variant['metadata'] != 'verified':
                continue  # Existing exact grants use the separate fixed-page workflow.
            fact, path = variant['observation'], variant['path']
            if not fact or fact['display_name'] in ('', 'None', 'N/A', 'NA'):
                continue
            short = path.rsplit('.', 1)[-1].casefold()
            reason = next((token for token in ACTOR_CONTEXTS if token in short), None)
            if reason:
                deferred.append(dict(id=character['id'], path=path, reason='actor requires separate context: ' + reason))
                continue
            if not pool:
                deferred.append(dict(id=character['id'], path=path, reason='no independently reviewed leaf family'))
                continue
            assert variant['receipts'], 'closed exact character metadata receipts required'
            assert path.startswith(prefix) and inventory.OBJECT.fullmatch(path) and path.endswith('_C')
            config = fact['observed_config']
            assert config.startswith(prefix) and inventory.OBJECT.fullmatch(config), 'exact same-folder CDO config required'
            lineage = fact['lineage']
            assert lineage[0] == path and '/Script/ProjectPBZ.PBZCharacter_NPC' in lineage \
                and '/Script/Engine.Character' in lineage, 'complete native NPC character lineage required'
            identity_sources = {name: sources[name] for name in variant['receipts']}
            # A group is only a bounded candidate pool. Native grants determine
            # its actual four bindings at assembly, and are captured verbatim.
            for offset in range(0, len(pool), 32):
                definition = dict(id=character['id'], class_path=path, config_path=config,
                    display_name=fact['display_name'], ability_pool=pool[offset:offset + 32],
                    identity_receipt_sha256=hashlib.sha256(metadata.canonical(identity_sources)).hexdigest(),
                    ability_metadata_receipt_sha256=hashlib.sha256(metadata.canonical(ability_sources)).hexdigest())
                prepared.append(dict(definition=definition, identity_receipts=identity_sources,
                    ability_receipts=ability_sources, historical_native_grants_verified=False,
                    runtime_verified=False, playable=False, activation_allowed=False))
    return prepared, deferred


def inputs(root=ROOT):
    snapshot, *_ = inventory.inputs(root)
    sources = dict(snapshot['sources'])
    sources.update({name: sha(root / name) for name in SOURCES})
    definitions_, deferred = definitions(snapshot['characters'], sources)
    identity = dict(schema=1, build=BUILD, definitions=definitions_, deferred=deferred,
        source_sha256=sources, installed=False, playable=False, game_started=False,
        all_boss_skills_complete=False)
    key = hashlib.sha256(metadata.canonical(identity)).hexdigest()[:20]
    return identity, key


def captured_grants(tail, definition, bindings):
    """Separate a missing native grant from a present move outside four UI slots."""
    identifier = definition['id']
    folder = definition['class_path'].split('/')[4]
    snapshots = list(inventory.grant_snapshots(tail.splitlines(), {identifier: folder}))
    assert len(snapshots) == 1, 'one complete native grant dump required'
    observed, = snapshots
    assert observed['id'] == identifier and observed['actor'] == definition['class_path'] \
        and observed['config'] == definition['config_path'], 'native dump belongs to another variant'
    allowed = definition['ability_pool']
    assert len(set(allowed)) == len(allowed)
    bound = {row['class_path'] for row in bindings}
    assert bound <= set(allowed) and all(observed['grants'].get(path) == 1 for path in bound), \
        'every binding needs exactly one observed native grant'
    return dict(native_grant_counts=observed['grants'],
        missing_native_grants=[path for path in allowed if path not in observed['grants']],
        unbound_candidates=[path for path in allowed if path not in bound],
        duplicate_native_candidates=[path for path in allowed if observed['grants'].get(path, 0) > 1])


def write_candidates(identity, key, target, root=ROOT):
    rows = []
    for entry in identity['definitions']:
        definition = entry['definition']
        module = ('local definition=' + lua(definition) + '\n').encode('utf-8')
        module += (root / 'tools/boss_developer_candidate.lua').read_bytes()
        variant = hashlib.sha256(metadata.canonical(definition)).hexdigest()[:16]
        directory = target / definition['id'] / variant
        record = dict(entry, inventory_fingerprint=key, build=BUILD,
            source_files={name: sha(root / name) for name in SOURCES},
            module_sha256=hashlib.sha256(module).hexdigest())
        directory.mkdir(parents=True, exist_ok=True)
        for name, raw in (('boss_candidate.lua', module),
                          ('manifest.json', (json.dumps(record, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))):
            path = directory / name
            if path.exists():
                assert path.read_bytes() == raw, 'preserve changed variant candidate: ' + str(path)
            else:
                path.write_bytes(raw)
        rows.append(dict(id=definition['id'], variant=variant, display_name=definition['display_name'],
            class_path=definition['class_path'], config_path=definition['config_path'],
            leaf_candidates=len(definition['ability_pool']), skills=definition['ability_pool'],
            directory=directory.relative_to(root).as_posix(), manifest_sha256=sha(directory / 'manifest.json')))
    return rows


def build(root=ROOT):
    root = root.resolve()
    identity, key = inputs(root)
    target = root / OUTPUT / key
    rows = write_candidates(identity, key, target, root)
    report = dict(identity, fingerprint=key, candidates=rows)
    write_json(target / 'summary.json', report)
    return target, report


def verify(directory, root=ROOT):
    root, directory = root.resolve(), unlinked_path(directory)
    identity, key = inputs(root)
    target = root / OUTPUT / key
    assert directory.parent.parent == target, 'current exact variant candidate required'
    assert {p.name for p in directory.iterdir()} == {'manifest.json', 'boss_candidate.lua'}
    with TemporaryDirectory(dir=target) as name:
        scratch = Path(name)
        rows = write_candidates(identity, key, scratch, root)
        matches = [row for row in rows if row['id'] == directory.parent.name and row['variant'] == directory.name]
        assert len(matches) == 1, 'variant has no current closed metadata proof'
        expected = root / matches[0]['directory']
        for name in ('manifest.json', 'boss_candidate.lua'):
            assert unlinked_path(directory / name).read_bytes() == (expected / name).read_bytes(), 'variant evidence or module changed'
    return inventory.read(directory / 'manifest.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    if args.verify:
        result = verify(args.verify)
        print(json.dumps(dict(id=result['definition']['id'], verified=True, playable=False)))
    else:
        directory, report = build()
        print(json.dumps(dict(directory=str(directory), variants=len({r['class_path'] for r in report['candidates']}),
            candidate_pools=len(report['candidates']), resource_folders=len({r['id'] for r in report['candidates']}),
            deferred=len(report['deferred']), game_started=False, playable=False), ensure_ascii=False))
