"""Freeze native-grant follow-up pools from independently closed leaf metadata.

These are isolated experiments, not player profiles. XianZhe has two attack
candidates; MoTian has two dodge candidates and no accepted attack adaptation.
"""
import argparse
import hashlib
import json
from pathlib import Path

from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from build_boss_profile_candidate import lua
import expanded_boss_developer_bundle as previous
from native_grant_metadata_workflow import verify_receipt
from mod_installation import active_mod_root, assert_closed, unlinked_path

RECEIPT = 'research/boss-adaptation/native-grant-metadata-receipts/20261118-185553-adc62361d82826f37842.json'
REVIEWS = {
    '071_xianzhe': dict(priority=('GA_XianZhe_Skill_01_C', 'GA_XianZhe_CA_C'), kind='attack-candidate'),
    '067_motian': dict(priority=('GA_MoTian_Dodge_F_02_C', 'GA_MoTian_Dodge_R_02_C'), kind='dodge-only-candidate'),
}
SOURCES = ('tools/native_grant_developer_bundle.py', 'tools/native_grant_developer_workflow.py',
           'tools/native_grant_metadata_workflow.py', 'tools/expanded_boss_developer_bundle.py',
           'tools/boss_developer_candidate.lua', 'tests/test_native_grant_developer.py',
           'tests/test_native_grant_candidate.lua')


def read(path): return json.loads(Path(path).read_bytes())


def definition(identifier, root=ROOT):
    assert identifier in REVIEWS, 'explicit native-grant follow-up required'
    baseline, evidence = previous.definition(identifier, root)
    receipt_path = root / RECEIPT
    receipt = verify_receipt(receipt_path, root)
    assert receipt['metadata_only'] is True and receipt['playable'] is False
    assert receipt['target_build_sha256'] == BUILD and receipt['control_verified'] is False
    assert receipt['runtime_acceptance_current'] is False
    folder = previous.REVIEWS[identifier]['folder']
    prefix = '/PBZCombatAsset/ActorData/Mobs/' + folder + '/Ability/'
    rows = [r for r in receipt['outcomes'] if r['id'] == identifier]
    assert len(rows) == len(REVIEWS[identifier]['priority']), 'exact reviewed metadata set required'
    pool = []
    for short in REVIEWS[identifier]['priority']:
        found = [r for r in rows if r['class_path'].rsplit('.', 1)[-1] == short]
        assert len(found) == 1
        row, = found
        assert row['role'] == 'ability' and row['metadata_verified'] is True and row['ability_kind'] == 'leaf'
        assert row['class_path'].startswith(prefix) and '/Retarget/' not in row['class_path']
        assert all(row[k] is False for k in ('identity_verified', 'live_grant_verified', 'activation_verified', 'playable'))
        pool.append(row['class_path'])
    assert len(set(pool)) == len(pool)
    value = {k: baseline[k] for k in ('id', 'class_path', 'config_path', 'display_name', 'identity_receipt_sha256')}
    value.update(ability_metadata_receipt_sha256=sha(receipt_path), ability_pool=pool,
                 blocked_scene_abilities=sorted(set(baseline['ability_pool'] + baseline['blocked_scene_abilities']) - set(pool)),
                 max_local_displacement_cm=3000, followup_action_kind=REVIEWS[identifier]['kind'])
    evidence = dict(evidence); evidence[RECEIPT] = sha(receipt_path)
    return value, evidence


def expected(identifier, root=ROOT, base=None):
    value, evidence = definition(identifier, root)
    base = base or active_mod_root(root)
    module = ('local definition=' + lua(value) + '\n').encode('utf-8') + (root / 'tools/boss_developer_candidate.lua').read_bytes()
    manifest = dict(schema_version=1, kind='native_grant_developer_bundle', id=identifier,
        target_build_sha256=BUILD, developer_only=True, playable=False, auto_deploy=False,
        definition=value, evidence=evidence, source_files={n: sha(root / n) for n in SOURCES},
        base_mod_files={p.relative_to(base).as_posix(): sha(p) for p in sorted(base.rglob('*.lua'))},
        overrides={'Scripts/boss_candidate.lua': hashlib.sha256(module).hexdigest()},
        scope='Exact closed leaf CDOs; fresh unique idle native grants still required; no manual grants or player promotion.')
    key = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:16]
    return manifest, module, 'native-grant-' + identifier + '-' + key


def build(identifier, root=ROOT):
    assert_closed(root)
    manifest, module, name = expected(identifier, root)
    target = root / 'research/boss-adaptation/developer-bundles' / name
    if not target.exists():
        target.mkdir(parents=True); (target / 'boss_candidate.lua').write_bytes(module)
        write_json(target / 'manifest.json', manifest)
    validate(identifier, target, root=root)
    return target


def validate(identifier, bundle, base=None, root=ROOT):
    target = unlinked_path(bundle)
    assert target.parent == (root / 'research/boss-adaptation/developer-bundles').resolve()
    manifest, module, name = expected(identifier, root, base)
    assert target.name == name and {p.name for p in target.iterdir()} == {'manifest.json', 'boss_candidate.lua'}
    assert read(target / 'manifest.json') == manifest
    assert unlinked_path(target / 'boss_candidate.lua').read_bytes() == module
    value = manifest['definition']
    return dict(boss_candidate=identifier, identity_receipt_sha256=value['identity_receipt_sha256'],
                ability_metadata_receipt_sha256=value['ability_metadata_receipt_sha256'],
                developer_max_displacement_cm=value['max_local_displacement_cm'],
                developer_bundle_sha256=sha(target / 'manifest.json'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('identifier', choices=REVIEWS); parser.add_argument('--verify', type=Path)
    args = parser.parse_args(); target = args.verify or build(args.identifier)
    print(json.dumps(dict(bundle=str(target), grant=validate(args.identifier, target),
                          game_started=False, playable=False), ensure_ascii=False))
