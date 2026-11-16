"""Read-only final installation and entry check; does not start the game."""
import json
from pathlib import Path
import re

from mod_installation import ROOT, MANIFEST, assert_closed, digest, installed_package, read, validate_package
from boss_workbench_v3_window import check_installed
from four_boss_integration_workflow import modules
from release_youlong_workbench import source_hashes

RELEASE = 'ahua-boss-workbench-v3-f7034432a74d819b'
MANIFEST_SHA = '5cb110f21013baea5ae714ad334c54dcd7fb0215e35b697e6559004cd8235d0d'
SESSION = '20261116-173808'
ROLES = [('ahua_guitoudao', 28, 29), ('057_wanjun', 4, 4),
         ('073_yanqiansui', 4, 4), ('056_youlong', 4, 4)]


def check():
    assert_closed()
    receipt, installed, directory = installed_package()
    published = validate_package(ROOT / 'releases' / RELEASE)
    assert installed == published == check_installed()
    assert receipt['enabled'] and directory.name == RELEASE
    assert digest(ROOT / 'releases' / RELEASE / MANIFEST) == MANIFEST_SHA
    assert published['pending'] == published['locked_previews'] == []
    assert [(r['id'], r['abilities'], r['bindings']) for r in published['bosses']] == ROLES
    acceptance_path = ROOT / published['acceptance_report']
    assert digest(acceptance_path) == published['acceptance_report_sha256']
    acceptance = read(acceptance_path)
    assert acceptance['passed'] and acceptance['release_id'] == RELEASE
    assert acceptance['module_source_sha256'] == modules(published)
    source_hashes(acceptance['source_sha256'])
    checks_path = ROOT / acceptance['local_checks']['path']
    assert digest(checks_path) == acceptance['local_checks']['sha256']
    checks = read(checks_path)
    assert checks['passed'] and checks['personal_settings_unchanged']
    assert len(checks['checks']) == 12 and all(r['passed'] for r in checks['checks'])
    source_hashes(checks['source_sha256'])
    integration = acceptance['yanqiansui']
    assert integration['session'] == SESSION
    proof_path = ROOT / integration['ordinary_integration']['path']
    assert digest(proof_path) == integration['ordinary_integration']['sha256']
    proof = read(proof_path)
    assert all(proof[k] for k in ('passed', 'ordinary_roundtrip_verified',
        'input_layers_recovered', 'owned_object_cleanup_verified', 'new_profile_world_cycle_verified'))
    assert proof['world_cycle']['passed'] and proof['world_cycle']['skill_natural_damage']
    source_hashes(proof['sources'])
    launcher = (ROOT / '开始Boss工作台.cmd').read_text(encoding='utf-8-sig')
    assert re.search(r'"%PBZ_PYTHON%"\s+"%~dp0tools\\boss_workbench_v3_window.py"', launcher)
    assert '70-四Boss工作台v3操作说明.md' in launcher
    state_path = ROOT / 'runtime' / ('official-validation-' + SESSION) / 'state.json'
    state = read(state_path)
    assert state['restored']
    post = read(Path(state['work']) / 'postcheck.json')
    assert post['validation_state'] == str(state_path)
    for key in ('research_box_empty', 'research_loader_removed', 'host_registry_unchanged',
                'all_temporary_network_removed', 'compatibility_setting_restored', 'validation_restored'):
        assert post[key], key
    assert not any(post[k] for k in ('formal_files_changed', 'host_config_files_changed', 'remaining_games'))
    return {'passed': True, 'release': RELEASE, 'installed_manifest_sha256': MANIFEST_SHA,
            'bosses': 4, 'abilities': 40, 'bindings': 41, 'locked_previews': [],
            'baseline_check_groups': 79, 'inherited_release_check_groups': 13,
            'four_boss_offline_groups': 12, 'integration_session': SESSION,
            'closed_integration_collector_passed': True, 'publisher_evidence_replay_passed': True,
            'installation_and_default_entry_verified': True, 'postcheck_passed': True,
            'game_started': False, 'personal_settings_modified': False,
            'source_sha256': {n: digest(ROOT / n) for n in (
                'tools/verify_four_boss_delivery.py', '开始Boss工作台.cmd',
                '70-四Boss工作台v3操作说明.md', '71-后端优先与集中验收.md')}}


if __name__ == '__main__':
    print(json.dumps(check(), ensure_ascii=False, indent=2))
