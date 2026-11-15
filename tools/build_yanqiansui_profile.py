"""Stage YanQianSui's four accepted actions without changing the player registry."""
import argparse
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from build_boss_profile_candidate import lua

IDENTIFIER = '073_yanqiansui'
SLOTS = [('slot1', 'skill_01', 'F1', '特殊攻击03', 'SpecialAttack_03'),
         ('heavy_01', 'heavy_01', 'F2', '特殊攻击04', 'SpecialAttack_04'),
         ('skill_02', 'skill_02', 'F3', '技能03', 'Skill_03'),
         ('dash', 'dash', 'F4', '技能04', 'Skill_04')]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def checked(root, name, digest):
    path = (root / name).resolve()
    assert path.is_relative_to(root.resolve()) and sha(path) == digest, 'Evidence changed: ' + name
    return path


def validate_report(report):
    assert report['id'] == IDENTIFIER and report['target_build_sha256'] == BUILD
    assert report['base_control_accepted'] is True and report['playable'] is False
    assert report['stability']['passed'] is True
    assert set(report['cleanup']) == {'boss', 'boss_controller', 'target', 'target_controller',
                                      'extra_target', 'extra_target_controller'}
    assert all(v is True for v in report['cleanup'].values())
    assert all(report['movement_camera'][k] is True for k in
               ('movement_verified', 'camera_rotation_verified', 'milestone_passed'))
    accepted = report['accepted_skills']
    assert set(accepted) == {row[1] for row in SLOTS}, 'Four independently accepted actions required'
    prefix = '/PBZCombatAsset/ActorData/Mobs/073_YanQianSui/Ability/GA_YanQianSui_'
    for _, skill, _, _, native in SLOTS:
        row = accepted[skill]
        expected = prefix + native + '.GA_YanQianSui_' + native + '_C'
        assert row['class_path'] == expected, 'Unexpected action class: ' + skill
        assert row['natural_completion_verified'] is True and row['cancellation_runtime_verified'] is True
        assert row['gameplay_verified'] is True or row['movement_runtime_verified'] is True
    return accepted


def camera_from(source):
    matches = re.findall(r'camera=\{([^{}]+)\}', source)
    assert len(matches) == 1, 'One exact candidate camera required'
    result = {}
    for item in matches[0].split(','):
        key, value = item.strip().split('=', 1)
        assert re.fullmatch(r'[a-z_]+', key) and key not in result
        assert value in ('true', 'false') or re.fullmatch(r'-?\d+(?:\.\d+)?', value)
        result[key] = (value == 'true') if value in ('true', 'false') else float(value) if '.' in value else int(value)
    assert result['binding_verified'] is False
    result['binding_verified'] = True
    return result


def build(session, root=ROOT):
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    report_path = root / 'evidence/official-validation' / session / 'boss-candidate-acceptance.json'
    report = read(report_path)
    accepted = validate_report(report)
    sources = {name: checked(root, name, digest) for name, digest in report['sources'].items()}
    state_path = root / 'runtime' / ('official-validation-' + session) / 'state.json'
    assert state_path.resolve() in sources.values() and read(state_path)['restored'] is True
    post_path = report_path.parent / 'postcheck.json'
    assert post_path.resolve() in sources.values()
    post = read(post_path)
    assert post['validation_state'] == str(state_path)
    assert post['research_box_empty'] and post['research_loader_removed'] and post['host_registry_unchanged']
    assert not post['formal_files_changed'] and not post['host_config_files_changed']
    manifests = [p for p in sources.values() if p.name == 'manifest.json'
                 and p.parent.parent.name == 'developer-bundles']
    assert len(manifests) == 1, 'Exact independently tested developer override required'
    bundle = read(manifests[0])
    assert bundle['id'] == IDENTIFIER and bundle['target_build_sha256'] == BUILD
    assert bundle['developer_only'] is True and bundle['playable'] is False
    module = manifests[0].parent / 'boss_candidate.lua'
    digest = report['module_source_sha256']['boss_candidate.lua']
    assert module.resolve() in sources.values() and sha(module) == digest
    assert bundle['overrides'] == {'Scripts/boss_candidate.lua': digest}
    for name, expected in report['module_source_sha256'].items():
        if name != 'boss_candidate.lua':
            checked(root, 'mod/PBZBossControl/Scripts/' + name, expected)
    identity = report['metadata_identity']
    assert identity['identity_verified'] is True and identity['id'] == IDENTIFIER
    definition = bundle['definition']
    assert all(identity[k] == definition[k] for k in ('id', 'class_path', 'config_path', 'display_name'))
    checked(root, identity['receipt'], identity['receipt_sha256'])
    evidence = report_path.relative_to(root).as_posix()
    profile = {'id': IDENTIFIER, 'display_name': identity['display_name'], 'exe_sha256': BUILD,
        'identity_verified': True, 'class_path': identity['class_path'], 'config_path': identity['config_path'],
        'identity_evidence': identity['receipt'], 'control_verified': True, 'skill_timeout_seconds': 30,
        'remote_target_verified': True, 'possession_roundtrip_verified': True,
        'movement_position_changed_verified': True, 'training_target_profile': 'profiles.ahua',
        'candidate_acceptance_evidence': evidence, 'candidate_acceptance_sha256': sha(report_path),
        'requires_ordinary_switching_acceptance': True,
        'camera': camera_from(module.read_text(encoding='utf-8')),
        'input': {'input_verified': True, 'mouse_scale': 0.1}, 'skills': {}}
    bindings = []
    for slot, skill, key, label, _ in SLOTS:
        row = accepted[skill]
        profile['skills'][skill] = dict(row, name='烟千岁' + label,
            binding_verified=True, active_count_field='ActiveCount', requires_target=True,
            cancel_binding_verified=True, cancel_function='K2_CancelAbility', activation_runtime_verified=True,
            evidence=evidence, cancellation_evidence=evidence)
        bindings.append({'slot': slot, 'id': skill, 'key': key, 'requires_cancel': True})
    contents = {'yanqiansui.lua': '-- Independent base accepted; ordinary switching remains required.\nreturn ' + lua(profile) + '\n',
                'yanqiansui_bindings.lua': '-- Four independently accepted native actions only.\nreturn ' + lua(bindings) + '\n'}
    target = root / 'runtime/staged-boss-profiles' / ('yanqiansui-' + sha(report_path)[:16])
    target.mkdir(parents=True, exist_ok=True)
    for name, content in contents.items():
        path = target / name
        payload = content.encode('utf-8')
        if path.exists():
            assert path.read_bytes() == payload, 'Preserve existing staged profile'
        else:
            path.write_bytes(payload)
    write_json(target / 'profile-candidate.json', {'id': IDENTIFIER, 'base_control_accepted': True,
        'ordinary_switching_accepted': False, 'playable': False, 'player_registry_modified': False,
        'evidence': evidence, 'evidence_sha256': sha(report_path),
        'generator_sha256': sha(Path(__file__)), 'files': {name: sha(target / name) for name in contents}})
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session')
    args = parser.parse_args()
    print(json.dumps({'staged_directory': str(build(args.session)), 'player_registry_modified': False,
                      'playable': False}, ensure_ascii=False))
