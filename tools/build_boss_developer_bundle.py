"""Freeze an isolated developer override from closed identity and ability metadata."""
import argparse
import hashlib
import json
from pathlib import Path

from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from build_boss_profile_candidate import lua
from mod_installation import active_mod_root, unlinked_path

IDENTIFIER = '073_yanqiansui'
METADATA = 'research/boss-adaptation/ability-metadata-receipts/20261116-051216.json'
SOURCES = ('tools/build_boss_developer_bundle.py', 'tools/boss_developer_candidate.lua',
    'tools/boss_candidate_gate.py', 'tools/ahua_practice.py', 'tools/run_control_lifecycle_probe.py',
    'tools/test_player_skill_batch.py', 'tools/run_boss_candidate_milestone.py',
    'tools/collect_boss_candidate_acceptance.py', 'tests/test_boss_developer_bundle.py',
    'tests/test_boss_developer_candidate.lua')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def validate_sources(receipt, root):
    for name, expected in receipt['sources'].items():
        path = (root / name).resolve()
        assert path.is_relative_to(root.resolve()) and sha(path) == expected, 'Evidence changed: ' + name


def definition(root=ROOT):
    metadata_path = root / METADATA
    receipt = read(metadata_path)
    assert receipt['target_build_sha256'] == BUILD and receipt['metadata_only'] and not receipt['playable']
    assert not receipt['live_grants_verified'] and not receipt['activation_verified']
    validate_sources(receipt, root)
    dossier_path = root / 'research/boss-adaptation/dossiers' / (IDENTIFIER + '.json')
    dossier = read(dossier_path)
    identity = dossier['metadata_identity']
    identity_path = (root / identity['receipt']).resolve()
    assert identity_path.is_relative_to((root / 'research/boss-adaptation/identity-receipts').resolve())
    assert identity['identity_verified'] and sha(identity_path) == identity['receipt_sha256']
    identity_receipt = read(identity_path)
    assert identity_receipt['target_build_sha256'] == BUILD and not identity_receipt['playable']
    validate_sources(identity_receipt, root)
    rows = [r for r in identity_receipt['candidates'] if r['id'] == IDENTIFIER and r['identity_verified']]
    assert len(rows) == 1
    assert all(rows[0][k] == identity[k] for k in ('class_path', 'config_path', 'display_name'))
    # Explicit initial action allowlist; dependencies, counter-context and story are excluded.
    priority = ['MiddleAttack_01', 'HeavyAttack_01', 'SpecialAttack_01', 'DodgeAttack_F_Red',
        'HeavyAttack_03', 'SpecialAttack_02_Red', 'SpecialAttack_03', 'SpecialAttack_04',
        'SpecialAttack_05', 'Skill_01', 'Skill_03', 'Skill_04', 'Skill_05', 'Skill_06',
        'Skill_07', 'Skill_07_Blue', 'Skill_07_Red', 'Skill_08', 'Skill_11_Red']
    prefix = '/PBZCombatAsset/ActorData/Mobs/073_YanQianSui/Ability/'
    expected = [prefix + 'GA_YanQianSui_' + name + '.GA_YanQianSui_' + name + '_C' for name in priority]
    observed = {}
    for row in receipt['ability_metadata']:
        assert row['id'] == IDENTIFIER and row['class_path'] not in observed
        assert not row['playable'] and not row['activation_verified'] and not row['live_grant_verified']
        observed[row['class_path']] = row
    pool = [path for path in expected if observed.get(path, {}).get('metadata_verified') is True
        and observed[path]['ability_kind'] == 'leaf']
    assert pool and len(pool) <= 32
    result = {k: identity[k] for k in ('id', 'class_path', 'config_path', 'display_name')}
    result.update(identity_receipt_sha256=sha(identity_path), ability_metadata_receipt_sha256=sha(metadata_path),
        ability_pool=pool)
    evidence = {p.relative_to(root).as_posix(): sha(p) for p in (dossier_path, identity_path, metadata_path)}
    return result, evidence


def render(value, root=ROOT):
    return ('local definition=' + lua(value) + '\n').encode('utf-8') + (root / 'tools/boss_developer_candidate.lua').read_bytes()


def build(root=ROOT):
    value, evidence = definition(root)
    base = active_mod_root(root)
    files = {p.relative_to(base).as_posix(): sha(p) for p in sorted(base.rglob('*.lua'))}
    sources = {name: sha(root / name) for name in SOURCES}
    module = render(value, root)
    manifest = {'schema_version': 1, 'id': IDENTIFIER, 'target_build_sha256': BUILD,
        'developer_only': True, 'playable': False, 'auto_deploy': False,
        'definition': value, 'evidence': evidence, 'source_files': sources,
        'base_mod_files': files, 'overrides': {'Scripts/boss_candidate.lua': hashlib.sha256(module).hexdigest()},
        'scope': 'Native unique idle grants only; no manual grants, player registration or inherited skill evidence.'}
    fingerprint = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:16]
    target = root / 'research/boss-adaptation/developer-bundles' / (IDENTIFIER + '-' + fingerprint)
    if not target.exists():
        target.mkdir(parents=True)
        (target / 'boss_candidate.lua').write_bytes(module)
        write_json(target / 'manifest.json', manifest)
    validate(IDENTIFIER, target, base, root)
    return target


def validate(identifier, bundle, base=None, root=ROOT):
    assert identifier == IDENTIFIER, 'Unregistered isolated developer candidate'
    bundle = unlinked_path(bundle)
    assert bundle.parent == (root / 'research/boss-adaptation/developer-bundles').resolve()
    manifest_path = unlinked_path(bundle / 'manifest.json')
    module_path = unlinked_path(bundle / 'boss_candidate.lua')
    assert set(p.name for p in bundle.iterdir()) == {'manifest.json', 'boss_candidate.lua'}
    manifest = read(manifest_path)
    fingerprint = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:16]
    assert bundle.name == IDENTIFIER + '-' + fingerprint, 'Developer bundle name/content mismatch'
    assert manifest['schema_version'] == 1 and manifest['id'] == identifier
    assert manifest['target_build_sha256'] == BUILD and manifest['developer_only'] is True
    assert manifest['playable'] is False and manifest['auto_deploy'] is False
    value, evidence = definition(root)
    assert manifest['definition'] == value and manifest['evidence'] == evidence
    assert manifest['source_files'] == {name: sha(root / name) for name in SOURCES}, 'Developer source changed; rebuild bundle'
    base = base or active_mod_root(root)
    assert manifest['base_mod_files'] == {p.relative_to(base).as_posix(): sha(p) for p in sorted(base.rglob('*.lua'))}
    assert manifest['overrides'] == {'Scripts/boss_candidate.lua': sha(module_path)}
    assert module_path.read_bytes() == render(value, root), 'Developer override differs from generated source'
    return {'boss_candidate': identifier, 'identity_receipt_sha256': value['identity_receipt_sha256'],
        'ability_metadata_receipt_sha256': value['ability_metadata_receipt_sha256'],
        'developer_bundle_sha256': sha(manifest_path)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    target = args.verify or build()
    grant = validate(IDENTIFIER, target)
    print(json.dumps({'bundle': str(target), 'grant': grant, 'game_started': False, 'playable': False}, ensure_ascii=False))
