"""Independently re-read source hashes, logs and staged payload after a backend run."""
import json
from pathlib import Path
import re
from build_phantom_boss_candidate import ROOT, SOURCES, sha, safe_file, verify_candidate, verify_upstream, verify_release, COMMIT
from check_phantom_boss_backend import TESTS, LAUNCH_SOURCES


def verify(path=None):
    path = Path(path) if path else ROOT / 'evidence/adaptation/phantom-pact-backend.json'
    report = json.loads(path.read_bytes())
    assert report['schema'] == 1 and report['status'] == 'backend-milestone-only' and report['passed'] is True
    for key in ('complete_mod', 'runtime_acceptance_current', 'game_started', 'native_relay_executed', 'installed'):
        assert report[key] is False, key
    expected_sources = {*SOURCES, *TESTS, *LAUNCH_SOURCES, 'tools/check_phantom_boss_backend.py', 'tools/verify_phantom_boss_backend.py'}
    assert set(report['source_sha256']) == expected_sources, 'incomplete source graph'
    for name, digest in report['source_sha256'].items():
        assert sha(safe_file(ROOT, name).read_bytes()) == digest, 'source drift: ' + name
    relative = report['candidate']
    assert relative.startswith('runtime/online-candidates/bwb-phantompact-')
    candidate = safe_file(ROOT, relative)
    manifest = verify_candidate(candidate)
    assert sha((candidate / 'candidate.json').read_bytes()) == report['candidate_manifest_sha256']
    assert manifest['own_sources'] == {name: report['source_sha256'][name] for name in SOURCES}
    assert report['pending'] == manifest['pending']
    pins = verify_upstream(ROOT / 'runtime/integration-research/PhantomPact' / COMMIT)
    assert pins == manifest['upstream_files'] and report['upstream_reviewed_sources'] == len(pins) == 19
    _, accepted = verify_release(ROOT)
    assert report['singleplayer_payload_files_verified'] == len(accepted['files'])
    assert report['personal_settings_and_singleplayer_unchanged'] is True
    counts = {'protocol_simulation': 16, 'adapter_mocked_api': 28, 'candidate_python': 15,
              'entry_mocked_research_lease': 11, 'host_fake_uobjects': 13,
              'enemy_fence_patched_upstream': 14, 'same_pc_pair_python': 8,
              'online_scope_simulation': 12, 'online_control_fake_uobjects': 14,
              'network_body_patched_upstream': 8, 'online_arena_lifecycle': 20,
              'online_spawn_native_bindings': 11, 'cold_startup_menu_loading': 17,
              'combat_runtime_composition': 5, 'visual_protocol_lifecycle': 16,
              'visual_native_bindings': 8, 'visual_session_integration': 5, 'deferred_launch_gate': 11,
              'pair_session_python': 18, 'online_workbench_lifecycle': 17, 'workbench_native_umg': 12,
              'control_contract_python': 14,'contract_bundle_python':8,'control_abi_python':18,'control_binding_python':13,
              'client_auth_python':14,
              'patched_lua_compile_only': 66}
    assert len(report['checks']) == len(counts)
    assert {row['name']: row['groups'] for row in report['checks']} == counts
    for row in report['checks']:
        assert row['passed'] is True and re.fullmatch(
            r'runtime/online-checks/[0-9a-f]{32}/' + re.escape(row['name']) + r'\.txt', row['output'])
        raw = safe_file(ROOT, row['output']).read_bytes()
        assert sha(raw) == row['output_sha256'], 'test log drift'
        output = raw.decode('utf-8')
        if row['name'].endswith('_python'):
            assert re.search(r'Ran '+str(row['groups'])+r' tests?', output) and re.search(r'\bOK\b', output)
        elif row['name'] == 'patched_lua_compile_only':
            assert 'PASS syntax only: 66 candidate Lua files' in output
        else:
            assert re.search(r'PASS ' + str(row['groups']) + r' (?:protocol|adapter|entry|host|enemy fence|online scope|online control|network body|online arena|spawn native|startup|combat runtime|visual|visual native|visual session|launch gate|online workbench|workbench native) groups', output)
    assert report['control_plane_test_groups'] == sum(list(counts.values())[:-1]) == 346
    assert report['syntax_checked_lua_files']==66
    return dict(passed=True, status='backend-milestone-only', groups=346, compiled_lua_files=66,
                candidate=manifest['candidate_id'], complete_mod=False,
                runtime_acceptance_current=False, game_started=False)


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
