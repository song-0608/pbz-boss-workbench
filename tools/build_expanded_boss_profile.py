"""Stage reviewed Boss profiles from closed native acceptance, without player promotion."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from build_boss_profile_candidate import lua
from build_yanqiansui_profile import camera_from, checked
import expanded_boss_developer_bundle as bundle
from mod_installation import assert_closed, unlinked_path

SLOTS = (('slot1', 'skill_01', 'F1'), ('heavy_01', 'heavy_01', 'F2'),
         ('skill_02', 'skill_02', 'F3'), ('dash', 'dash', 'F4'))
NAMES = {'071_xianzhe': 'xianzhe', '058_maddoctor': 'maddoctor', '067_motian': 'motian'}
LABELS = {'Skill_05': '技能05', 'Skill_06': '技能06', 'Skill_07': '技能07',
          'Skill_02': '技能02', 'Skill_03': '技能03', 'LightAttack_01': '轻攻击01',
          'HeavyAttack_01': '重攻击01', 'Dodge_B': '后闪', 'Dodge_L': '左闪',
          'Dodge_R': '右闪', 'Dodge_F': '前闪'}
SOURCES = ('tools/build_expanded_boss_profile.py', 'tests/test_expanded_boss_profile.py')


def validate_report(report, definition):
    identifier = definition['id']
    assert identifier in NAMES and report['id'] == identifier
    assert report['target_build_sha256'] == BUILD
    assert report['base_control_accepted'] is True and report['playable'] is False
    assert report['stability']['passed'] is True
    expected_cleanup = {'boss', 'boss_controller', 'target', 'target_controller',
                        'extra_target', 'extra_target_controller'}
    assert set(report['cleanup']) == expected_cleanup and all(v is True for v in report['cleanup'].values())
    assert all(report['movement_camera'][k] is True for k in
               ('movement_verified', 'camera_rotation_verified', 'milestone_passed'))
    assert report['metadata_identity'] == definition, 'Exact reviewed identity and pool required'
    accepted = report['accepted_skills']
    assert 'skill_01' in accepted and set(accepted) <= {row[1] for row in SLOTS}
    assert set(accepted) <= set(report['skills'])
    paths = set()
    for skill, row in accepted.items():
        assert row == report['skills'][skill], 'Accepted action differs from collected result'
        assert row['class_path'] in definition['ability_pool'], 'Foreign/unreviewed native action'
        assert row['class_path'] not in paths, 'Duplicate native action'
        paths.add(row['class_path'])
        assert row['natural_completion_verified'] is True and row['cancellation_runtime_verified'] is True
        assert row['gameplay_verified'] is True or row['movement_runtime_verified'] is True
    return accepted


def label(path):
    short = path.rsplit('.', 1)[-1]
    matches = [value for suffix, value in LABELS.items() if short.endswith('_' + suffix + '_C')]
    assert len(matches) == 1, 'Explicit action label review required: ' + short
    return matches[0]


def expected(session, identifier, root=ROOT):
    assert re.fullmatch(r'\d{8}-\d{6}', session) and identifier in NAMES
    definition, metadata_sources = bundle.definition(identifier, root)
    report_path = root / 'evidence/official-validation' / session / 'boss-candidate-acceptance.json'
    report = bundle.read(report_path)
    accepted = validate_report(report, definition)
    assert report['session'] == session
    sources = {n: checked(root, n, d) for n, d in report['sources'].items()}
    state_path = root / 'runtime' / ('official-validation-' + session) / 'state.json'
    assert state_path.resolve() in sources.values() and bundle.read(state_path)['restored'] is True
    post_path = report_path.parent / 'postcheck.json'
    assert post_path.resolve() in sources.values()
    post = bundle.read(post_path)
    assert post['validation_state'] == str(state_path)
    assert all(post[k] is True for k in ('research_box_empty', 'research_loader_removed', 'host_registry_unchanged'))
    assert not post['formal_files_changed'] and not post['host_config_files_changed']
    manifests = [p for p in sources.values() if p.name == 'manifest.json'
                 and p.parent.parent.name == 'developer-bundles']
    assert len(manifests) == 1
    developer = unlinked_path(manifests[0].parent)
    bundle.validate(identifier, developer, root=root)
    frozen = bundle.read(developer / 'manifest.json')
    assert frozen['definition'] == definition
    module = developer / 'boss_candidate.lua'
    assert module.resolve() in sources.values()
    assert sha(module) == report['module_source_sha256']['boss_candidate.lua']
    for name, digest in report['module_source_sha256'].items():
        if name != 'boss_candidate.lua':
            assert frozen['base_mod_files']['Scripts/' + name] == digest
    identity_sources = [n for n, d in metadata_sources.items() if d == definition['identity_receipt_sha256']]
    assert len(identity_sources) == 1
    evidence = report_path.relative_to(root).as_posix()
    profile = {k: definition[k] for k in ('id', 'display_name', 'class_path', 'config_path')}
    profile.update(exe_sha256=BUILD, identity_verified=True, identity_evidence=identity_sources[0],
        control_verified=True, skill_timeout_seconds=30, remote_target_verified=True,
        possession_roundtrip_verified=True, movement_position_changed_verified=True,
        training_target_profile='profiles.ahua', candidate_acceptance_evidence=evidence,
        candidate_acceptance_sha256=sha(report_path), requires_ordinary_switching_acceptance=True,
        camera=camera_from(module.read_text(encoding='utf-8')),
        input={'input_verified': True, 'mouse_scale': 0.1}, skills={})
    bindings = []
    for slot, skill, key in SLOTS:
        if skill not in accepted:
            continue
        row = accepted[skill]
        profile['skills'][skill] = dict(row, name=definition['display_name'] + '·' + label(row['class_path']),
            binding_verified=True, active_count_field='ActiveCount', requires_target=True,
            cancel_binding_verified=True, cancel_function='K2_CancelAbility',
            activation_runtime_verified=True, evidence=evidence, cancellation_evidence=evidence)
        bindings.append(dict(slot=slot, id=skill, key=key, requires_cancel=True))
    stem = NAMES[identifier]
    payloads = {stem + '.lua': '-- Independent native acceptance; ordinary selection still required.\nreturn ' + lua(profile) + '\n',
                stem + '_bindings.lua': '-- Only independently accepted native actions.\nreturn ' + lua(bindings) + '\n'}
    manifest = dict(schema=1, id=identifier, profile_module='profiles.' + stem,
        bindings_module='profiles.' + stem + '_bindings', display_name=definition['display_name'],
        base_control_accepted=True, ordinary_switching_accepted=False, playable=False,
        player_registry_modified=False, evidence=evidence, evidence_sha256=sha(report_path),
        developer_bundle=developer.relative_to(root).as_posix(), developer_manifest_sha256=sha(developer / 'manifest.json'),
        metadata_sources=metadata_sources, sources={n: sha(root / n) for n in SOURCES},
        accepted_skills=list(profile['skills']),
        skill_labels={row['slot']: profile['skills'][row['id']]['name'] for row in bindings},
        files={n: hashlib.sha256(v.encode('utf-8')).hexdigest() for n, v in payloads.items()})
    key = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:16]
    return manifest, payloads, stem + '-' + key


def verify(target, root=ROOT):
    target = unlinked_path(target)
    assert target.parent == (root / 'runtime/staged-boss-profiles').resolve()
    recorded = bundle.read(target / 'profile-candidate.json')
    evidence = Path(recorded['evidence'])
    assert evidence.parts[:2] == ('evidence', 'official-validation') and evidence.name == 'boss-candidate-acceptance.json'
    manifest, payloads, name = expected(evidence.parent.name, recorded['id'], root)
    assert target.name == name and recorded == manifest
    assert {p.name for p in target.iterdir()} == set(payloads) | {'profile-candidate.json'}
    assert all((target / n).read_bytes() == v.encode('utf-8') for n, v in payloads.items())
    return manifest


def build(session, identifier, root=ROOT):
    assert_closed(root)
    manifest, payloads, name = expected(session, identifier, root)
    target = root / 'runtime/staged-boss-profiles' / name
    if target.exists():
        assert bundle.read(target / 'profile-candidate.json') == manifest
        assert {p.name for p in target.iterdir()} == set(payloads) | {'profile-candidate.json'}
        assert all((target / n).read_bytes() == v.encode('utf-8') for n, v in payloads.items())
    else:
        target.mkdir(parents=True)
        for name, value in payloads.items():
            (target / name).write_text(value, encoding='utf-8', newline='\n')
        write_json(target / 'profile-candidate.json', manifest)
    verify(target, root)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session'); parser.add_argument('identifier', choices=NAMES)
    args = parser.parse_args()
    print(json.dumps(dict(profile=str(build(args.session, args.identifier)),
                         playable=False, installed=False), ensure_ascii=False))
