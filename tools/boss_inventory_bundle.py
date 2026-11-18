"""Freeze inventoried developer moves for the protected control lifecycle."""

import hashlib
from pathlib import Path

import boss_metadata_jobs as metadata
from boss_adaptation_workflow import BUILD, ROOT, sha
from boss_offline_inventory import DOMAINS, OUTPUT, inputs, prepare_skill_pools, read
from mod_installation import active_mod_root, unlinked_path
import prepare_boss_skill_pages as skill_pages


REVIEWS = skill_pages.REVIEWED_ROLES


def candidate_ids(root=ROOT):
    # CLI scope only. Each bundle still needs exact closed CDO/leaf proofs and
    # fresh native grants; a catalog entry cannot register a playable character.
    catalog = read(root / 'research/boss-adaptation/catalog.json')
    assert catalog['target_build_sha256'] == BUILD
    return tuple(sorted(set(REVIEWS) | {row['id'] for row in catalog['candidates']
        if not row['reference_only'] and row['resource_folder'] != 'Common'}))


def historical_pool(identifier, bundle, root):
    identity, *_ = inputs(root)
    key = hashlib.sha256(metadata.canonical(identity)).hexdigest()[:20]
    target = root / OUTPUT / key
    assert identifier in candidate_ids(root), 'observed catalog candidate required'
    legacy = bundle == target / 'skill-pools' / identifier
    if not legacy:
        page_identity, identities, sources, page_key = skill_pages.inputs(root)
        target = root / 'runtime/boss-skill-pages' / page_key
        assert bundle.parent == target / 'skill-pages' / identifier, 'current exact skill page required'
    # Reconstruct the pool into an isolated temporary directory so verification
    # cannot overwrite a modified module or repair its own evidence.
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(dir=target) as scratch:
        if legacy:
            assert identifier in DOMAINS
            regenerated = prepare_skill_pools(identity['characters'], identity['sources'], Path(scratch), root)
            assert any(row['id'] == identifier for row in regenerated), 'exact reviewed variant and grant required'
            expected = Path(scratch) / 'skill-pools' / identifier
        else:
            regenerated, _ = skill_pages.write_pages(page_identity['characters'], identities, sources, Path(scratch), root)
            assert any(row['id'] == identifier and row['page'] == bundle.name for row in regenerated)
            expected = Path(scratch) / 'skill-pages' / identifier / bundle.name
        for name in ('manifest.json', 'boss_candidate.lua'):
            observed = unlinked_path(bundle / name).read_bytes()
            assert observed == (expected / name).read_bytes(), f'{identifier}: inventory pool changed: {name}'
    return read(bundle / 'manifest.json')


def validate(identifier, bundle, base=None, root=ROOT):
    root = root.resolve()
    bundle = unlinked_path(bundle)
    import prepare_boss_variant_candidates as variants
    if bundle.is_relative_to(root / variants.OUTPUT):
        record = variants.verify(bundle, root)
    else:
        record = historical_pool(identifier, bundle, root)
    definition = record['definition']
    assert identifier == definition['id'], 'exact candidate identity required'
    base = base or active_mod_root(root)
    frozen_release = root / 'releases/ahua-boss-workbench-v5-3f29975fe3b8826f'
    manifest = read(frozen_release / 'pbz-release.json')
    assert manifest['exe_sha256'] == BUILD
    paths = {name.removeprefix('PBZBossControl/'): value for name, value in manifest['files'].items()
             if name.startswith('PBZBossControl/Scripts/') and name.endswith('.lua')}
    assert paths == {path.relative_to(base).as_posix(): sha(path) for path in (base / 'Scripts').rglob('*.lua')}
    return dict(boss_candidate=identifier, identity_receipt_sha256=definition['identity_receipt_sha256'],
                ability_metadata_receipt_sha256=definition['ability_metadata_receipt_sha256'],
                developer_max_displacement_cm=3000, developer_bundle_sha256=sha(bundle / 'manifest.json'))
