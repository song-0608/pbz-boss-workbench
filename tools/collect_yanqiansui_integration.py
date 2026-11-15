"""Verify the closed three-Boss candidate's new ordinary profile and original-menu world cycle."""
import argparse
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from collect_auto_world_reassembly import proof as world_proof
from collect_multi_boss_switching import exact_role_proof, movement_camera_proof
from candidate_effect_scope import local_effect
from control_action_evidence import restoration_result
from build_yanqiansui_profile import validate_report

IDENTIFIER = '073_yanqiansui'
CHECKS = ['active_ahua_open_restores_player', 'ahua_to_yanqiansui_cleanup',
          'four_ordinary_bindings_natural_cancel', 'ordinary_movement_camera_and_auto_restore',
          'return_ahua_controls_restored', 'yanqiansui_ready_for_original_menu_world_cycle',
          'new_world_ordinary_skill_and_restoration']


def collect(session):
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    state_path = ROOT / 'runtime' / ('official-validation-' + session) / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    work = ROOT / 'evidence/official-validation' / session
    assert state['restored'] and Path(state['work']).resolve() == work.resolve()
    def read(name):
        return json.loads((work / name).read_text(encoding='utf-8'))
    post = read('postcheck.json')
    assert post['validation_state'] == str(state_path)
    assert all(post[k] for k in ('research_box_empty', 'research_loader_removed', 'host_registry_unchanged'))
    assert not any(post[k] for k in ('formal_files_changed', 'host_config_files_changed', 'remaining_games'))
    deployments = list(work.glob('control-lifecycle-deployment-*.json'))
    assert len(deployments) == 1, 'One ordinary deployment with no manual rearm required'
    deployment = json.loads(deployments[0].read_text(encoding='utf-8'))
    assert deployment['player_entry'] and deployment['boss_id'] == 'ahua_guitoudao'
    assert not deployment['boss_candidate'] and not deployment['scene_transition_trial']
    assert deployment['grant']['exe_sha256'] == BUILD
    base_path = ROOT / 'evidence/official-validation/20261116-055334/boss-candidate-acceptance.json'
    base = json.loads(base_path.read_text(encoding='utf-8'))
    accepted = validate_report(base)
    for name, digest in base['sources'].items():
        assert sha(ROOT / name) == digest, 'Independent evidence changed: ' + name
    current = deployment['module_source_sha256']
    changes = {name for name, digest in base['module_source_sha256'].items() if current.get(name) != digest}
    assert changes == {'boss_candidate.lua', 'boss_catalog.lua', 'workbench_catalog.lua'}
    assert set(current) - set(base['module_source_sha256']) == {'profiles/yanqiansui.lua', 'profiles/yanqiansui_bindings.lua'}
    raw_path = work / 'UE4SS.log'
    raw = raw_path.read_text(encoding='utf-8', errors='replace')
    action = read('yanqiansui-integration-actions.json')
    assert action['state_file'] == str(state_path) and action['roundtrip_passed'] and action['world_finished']
    assert action['checks'] == CHECKS and not action.get('error')
    start, end = action['log_offset'], action['log_end']
    assert 0 <= start < action['world_scope_offset'] < end <= len(raw)
    segment = raw[start:end]
    assert action['lines'] == segment.splitlines()
    assert re.findall(r'WORKBENCH_BOSS_SELECTED=([^\r\n]+)', segment) == [IDENTIFIER, 'ahua_guitoudao', IDENTIFIER]
    ready = list(re.finditer(r'PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=([^\r\n]+)', segment))
    assert [r[1] for r in ready] == [IDENTIFIER, 'ahua_guitoudao', IDENTIFIER, IDENTIFIER]
    assert action['world_scope_offset'] == start + ready[2].start()
    expected = {'boss', 'boss_controller', 'target', 'target_controller', 'extra_target', 'extra_target_controller'}
    for interval in (segment[:ready[0].start()], segment[ready[0].end():ready[1].start()],
                     segment[ready[1].end():ready[2].start()]):
        assert set(re.findall(r'OWNED_DESTROY_VERIFIED=([^|\r\n]+)\|engine_unusable=true', interval)) == expected
    assert segment.count('WORKBENCH_INPUT_LOCKED=') == segment.count('WORKBENCH_INPUT_RESTORED=true') == 3
    assert restoration_result(segment[:ready[0].start()], 'auto_exit')['passed']
    yan_segment = segment[ready[0].end():ready[1].start()]
    movement_segment = yan_segment[yan_segment.rfind('[PBZBossControl] enter success=true state=ACTIVE'):]
    motion = movement_camera_proof(movement_segment)
    assert motion['passed'] and action['movement_camera'] == motion
    assert restoration_result(movement_segment, 'auto_exit')['passed']
    from build_ahua_acceptance_matrix import capabilities
    classes = {'ahua_guitoudao': {r['skill']: r['class_path'] for r in capabilities()},
               IDENTIFIER: {key: row['class_path'] for key, row in accepted.items()}}
    proofs = []
    for row in read('player-extra-skill-actions.json'):
        a, b = row['log_offset'], row['log_end']
        if not start <= a < b <= end:
            continue
        assert row['state_file'] == str(state_path) and row['lines'] == raw[a:b].splitlines()
        assert row['passed'] is True and row['cast_dispatched'] is True
        boss = re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)', raw[:a])[-1]
        proof = exact_role_proof(raw, row, boss, classes[boss][row['skill']])
        if boss == IDENTIFIER:
            proof = local_effect(proof, raw[a:b], 3000)
            assert proof['local_displacement_verified']
        assert proof['active_cancel_and_restoration'] if row['interrupt'] else proof['natural_completion'] and proof['restoration']['passed']
        proofs.append(dict(proof, boss=boss, skill=row['skill'], interrupt=row['interrupt'], log_offset=a))
    first_yan = [p for p in proofs if p['boss'] == IDENTIFIER and p['log_offset'] < start + ready[1].start()]
    assert {(p['skill'], p['interrupt']) for p in first_yan} == {(s, i) for s in accepted for i in (False, True)}
    ahua = [p for p in proofs if p['boss'] == 'ahua_guitoudao']
    assert {(p['skill'], p['interrupt']) for p in ahua} == {('skill_01', False), ('skill_08', True)}
    witness_path = work / 'auto-world-witness.json'
    witness = read(witness_path.name)
    assert witness['state_file'] == str(state_path) and witness['pre_pid'] == witness['post_pid']
    assert sha_bytes(raw[:witness['log_end']].encode('utf-8')) == witness['log_prefix_sha256']
    assert witness['log_end'] <= end
    world = world_proof(raw[action['world_scope_offset']:witness['log_end']])
    assert world['passed']
    assert not any(token in segment for token in ('state=FAULTED', 'PBZ_CONTROL_LIFECYCLE:ISSUE_',
        'HUD_UNAVAILABLE=', 'PBZ_CONTROL_RESTORE:FAILED=', 'PREREQUISITE_NOT_READY='))
    menu_actions = read('settings-menu-actions.json')
    assert len([r for r in menu_actions if r['purpose'] == 'control_menu_confirm']) == 1
    assert len([r for r in menu_actions if r['purpose'] == 'control_menu_continue']) == 1
    paths = [state_path, work / 'postcheck.json', raw_path, work / 'yanqiansui-integration-actions.json',
        work / 'player-extra-skill-actions.json', witness_path, work / 'settings-menu-actions.json', base_path, *deployments]
    result = {'passed': True, 'session': session, 'id': IDENTIFIER, 'target_build_sha256': BUILD,
        'module_source_sha256': current, 'ordinary_roundtrip_verified': True, 'input_layers_recovered': True,
        'owned_object_cleanup_verified': True, 'movement_camera': motion, 'skill_proofs': proofs,
        'world_cycle': world, 'new_profile_world_cycle_verified': True, 'complete_mod': False,
        'sources': {p.relative_to(ROOT).as_posix(): sha(p) for p in paths}}
    output = work / 'yanqiansui-integration-acceptance.json'
    assert not output.exists(), 'Preserve collected integration evidence'
    write_json(output, result)
    return {'passed': True, 'report': str(output), 'world_cycle_passed': world['passed']}


def sha_bytes(value):
    import hashlib
    return hashlib.sha256(value).hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session')
    print(json.dumps(collect(parser.parse_args().session), ensure_ascii=False))
