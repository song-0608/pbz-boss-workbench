"""Freeze inventoried developer moves for the protected control lifecycle."""

import hashlib
from pathlib import Path

import boss_metadata_jobs as metadata
from boss_adaptation_workflow import BUILD, ROOT, sha
from boss_offline_inventory import DOMAINS, OUTPUT, inputs, prepare_skill_pools, read
from mod_installation import active_mod_root, unlinked_path


REVIEWS = DOMAINS


def validate(identifier, bundle, base=None, root=ROOT):
    root = root.resolve()
    bundle = unlinked_path(bundle)
    identity, *_ = inputs(root)
    key = hashlib.sha256(metadata.canonical(identity)).hexdigest()[:20]
    target = root / OUTPUT / key
    assert identifier in REVIEWS and bundle == target / 'skill-pools' / identifier
    # Reconstruct the pool into an isolated temporary directory so verification
    # cannot overwrite a modified module or repair its own evidence.
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(dir=target) as scratch:
        regenerated = prepare_skill_pools(identity['characters'], identity['sources'], Path(scratch), root)
        assert any(row['id'] == identifier for row in regenerated), 'exact reviewed variant and grant required'
        expected = Path(scratch) / 'skill-pools' / identifier
        for name in ('manifest.json', 'boss_candidate.lua'):
            observed = unlinked_path(bundle / name).read_bytes()
            assert observed == (expected / name).read_bytes(), f'{identifier}: inventory pool changed: {name}'
    record = read(bundle / 'manifest.json')
    definition = record['definition']
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
