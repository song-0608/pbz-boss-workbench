"""Read-only handoff check for the installed, accepted three-Boss release."""
import json
from pathlib import Path
import re

from mod_installation import ROOT, MANIFEST, assert_closed, digest, installed_package, read, validate_package
from four_boss_integration_workflow import modules
from release_youlong_workbench import acceptance, source_hashes

RELEASE = 'ahua-boss-workbench-v2-7b83ce4aa5d15a03'
RELEASE_SHA = 'ce424d1c9c3063a85955a15ef016d1f7ed13fc42db932ebd4ac9eb27a1394746'
ROLES = [('ahua_guitoudao', 28, 29), ('057_wanjun', 4, 4), ('056_youlong', 4, 4)]


def check():
    assert_closed()
    receipt, installed, directory = installed_package()
    release_path = ROOT / 'releases' / RELEASE
    published = validate_package(release_path)
    assert receipt['enabled'] and installed == published
    assert directory.name == RELEASE and digest(release_path / MANIFEST) == RELEASE_SHA
    assert published['status'] == 'release' and published['complete_mod'] and published['runtime_acceptance_current']
    assert published['pending'] == [] and published['locked_previews'] == ['073_yanqiansui']
    assert [(r['id'], r['abilities'], r['bindings']) for r in published['bosses']] == ROLES
    report_path = ROOT / published['acceptance_report']
    assert digest(report_path) == published['acceptance_report_sha256']
    report = read(report_path)
    assert report['passed'] and report['release_id'] == RELEASE
    assert report['module_source_sha256'] == modules(published)
    source_hashes(report['source_sha256'])
    candidate = ROOT / 'runtime/release-candidates' / published['accepted_candidate']
    candidate_manifest, evidence = acceptance(candidate, report['session'])
    assert candidate_manifest['files'] == published['files']
    assert all(report[key] == value for key, value in evidence.items())
    checks_path = ROOT / report['local_checks']['path']
    assert digest(checks_path) == report['local_checks']['sha256']
    checks = read(checks_path)
    assert checks['passed'] and checks['personal_settings_unchanged'] and len(checks['checks']) == 13
    assert all(row['passed'] for row in checks['checks'])
    source_hashes(checks['sources'])
    baseline_path = ROOT / checks['baseline_checks']['path']
    assert digest(baseline_path) == checks['baseline_checks']['sha256']
    baseline = read(baseline_path)
    assert baseline['passed'] and len(baseline['checks']) == 79
    source_hashes(baseline['source_sha256'])
    launcher = (ROOT / '开始Boss工作台.cmd').read_text(encoding='utf-8-sig')
    assert re.search(r'"%PBZ_PYTHON%"\s+"%~dp0tools\\boss_workbench_v2_window.py"', launcher)
    pointer = read(ROOT / 'runtime/latest-official-validation.json')
    state_path = Path(pointer['state_file'])
    assert state_path.resolve().is_relative_to((ROOT / 'runtime').resolve())
    state = read(state_path)
    post = read(Path(state['work']) / 'postcheck.json')
    assert post['validation_state'] == str(state_path) and state['restored']
    for key in ('research_box_empty', 'research_loader_removed', 'host_registry_unchanged',
                'all_temporary_network_removed', 'compatibility_setting_restored', 'validation_restored'):
        assert post[key], key
    assert not any(post[key] for key in ('formal_files_changed', 'host_config_files_changed', 'remaining_games'))
    return {'passed': True, 'release': RELEASE, 'installed_manifest_sha256': RELEASE_SHA,
            'bosses': 3, 'abilities': 36, 'bindings': 37, 'locked_previews': ['073_yanqiansui'],
            'baseline_check_groups': 79, 'release_check_groups': 13, 'evidence_reparsed': True,
            'latest_session': state_path.parent.name, 'latest_postcheck_passed': True,
            'game_started': False, 'personal_settings_modified': False,
            'source_sha256': {'tools/verify_player_delivery.py': digest(Path(__file__))}}


if __name__ == '__main__':
    print(json.dumps(check(), ensure_ascii=False, indent=2))
