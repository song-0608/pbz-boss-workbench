"""Single backend milestone: source gates, Lua simulations and candidate syntax; never launch."""
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid
from build_phantom_boss_candidate import ROOT, SOURCES, build, sha, verify_candidate, verify_release

TESTS = ('tests/test_phantom_boss_protocol.lua', 'tests/test_phantom_boss_adapter.lua',
         'tests/test_phantom_boss_candidate.py', 'tests/compile_phantom_boss_candidate.lua',
         'tests/test_phantom_boss_entry.lua', 'tests/test_phantom_boss_host.lua',
         'tests/test_phantom_boss_enemy_fence.lua', 'tests/test_phantom_boss_pair.py',
         'tests/test_phantom_boss_online_scope.lua', 'tests/test_phantom_boss_online_control.lua',
         'tests/test_native_bridge.lua', 'tests/test_phantom_boss_network_body.lua',
         'tests/test_phantom_boss_online_arena.lua', 'tests/test_phantom_boss_spawn_native.lua',
         'tests/test_phantom_boss_startup.lua', 'tests/test_phantom_boss_combat_runtime.lua',
         'tests/test_phantom_boss_visual.lua', 'tests/test_phantom_boss_visual_native.lua',
         'tests/test_phantom_boss_visual_session.lua', 'tests/test_phantom_boss_launch_gate.lua',
         'tests/test_phantom_boss_pair_session.py', 'tests/test_phantom_boss_online_workbench.lua',
         'tests/test_phantom_boss_workbench_native.lua','tests/test_phantom_boss_control_contract.py',
         'tests/test_phantom_boss_contract_bundle.py','tests/test_phantom_boss_control_abi.py',
         'tests/test_phantom_boss_control_binding.py','tests/test_phantom_boss_client_auth.py',
         'tests/test_phantom_boss_online_session.lua','tests/test_phantom_boss_optional_contracts.py',
         'tests/test_phantom_boss_profile_policy.lua','tests/test_boss_adapter_registry.py',
         'tests/test_boss_adaptation_batch.py','tests/test_boss_identity_probe.lua',
         'tests/test_boss_metadata_jobs.py','tests/test_boss_metadata_jobs.lua',
         'tests/test_boss_adapter_review.py')
LAUNCH_SOURCES=('tools/phantom_boss_pair_session.py','tools/phantom_boss_online_readonly.py',
    'tools/collect_phantom_boss_visual_contract.py','tools/prepare_phantom_boss_clients.py',
    'tools/check_phantom_boss_isolation.py','tools/phantom_boss_pair_bootstrap.cpp',
    'tools/check_phantom_boss_pair_bootstrap.py','tools/collect_phantom_boss_workbench_contract.py',
    'tools/stage_phantom_boss_pair.py','tools/phantom_boss_pair_compatibility.py',
    'tools/phantom_boss_isolation_probe.cpp','tools/collect_phantom_boss_control_contract.py',
    'tools/inspect_camera_contract.py','tools/inspect_remote_contract.py','tools/inspect_arena_contract.py',
    'tools/inspect_pbz_ai_metadata.py','tools/collect_phantom_boss_contract_bundle.py',
    'tools/phantom_boss_control_abi.py','tools/issue_phantom_boss_control_binding.py',
    'research/contracts/phantom-control-abi.json','tools/phantom_boss_native_bootstrap.cpp',
    'tools/phantom_boss_native_probe.cpp','tools/build_phantom_boss_native.py','tools/check_phantom_boss_native.py',
    'tools/inspect_phantom_boss_client_auth.py','tools/boss_adapter_registry.py',
    'tools/boss_adaptation_workflow.py','tools/build_boss_adaptation_batch.py','tools/build_boss_identity_probe.py',
    'research/boss-adaptation/expansion-queue.json','tools/boss_metadata_jobs.py',
    'tools/collect_boss_metadata_jobs.py','tools/run_boss_identity_batch.py',
    'tools/boss_adapter_review.py')


def protected_files():
    names = ['玩家设置.json', '玩家键位.json', '项目状态.json', '开始Boss工作台.cmd']
    files = {n: sha((ROOT / n).read_bytes()) if (ROOT / n).exists() else None for n in names}
    directory, manifest = verify_release(ROOT)
    files['accepted-release'] = sha((directory / 'pbz-release.json').read_bytes())
    files['accepted-payload'] = manifest['files']
    return files


def run():
    before = protected_files()
    target = build()
    from boss_adapter_registry import build as build_expansion
    expansion=json.loads(build_expansion().read_bytes())
    from boss_adapter_review import build as build_review
    build_review()
    identity_probe=ROOT/expansion['batches'][0]['directory']/'identity-probe.lua'
    metadata_probe=ROOT/expansion['metadata_batches'][0]['directory']/'metadata-probe.lua'
    lab = ROOT.parent / 'build/lua-harness/Release/lua-lab.exe'
    commands = [
        ('protocol_simulation', [str(lab), str(ROOT / TESTS[0]), str(ROOT)], 16),
        ('adapter_mocked_api', [str(lab), str(ROOT / TESTS[1]), str(ROOT)], 52),
        ('candidate_python', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_phantom_boss_candidate.py', '-v'], 15),
        ('entry_mocked_research_lease', [str(lab), str(ROOT / TESTS[4]), str(target)], 15),
        ('host_fake_uobjects', [str(lab), str(ROOT / TESTS[5]), str(ROOT)], 17),
        ('enemy_fence_patched_upstream', [str(lab), str(ROOT / TESTS[6]), str(ROOT), str(target)], 14),
        ('same_pc_pair_python', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_phantom_boss_pair.py', '-v'], 8),
        ('online_scope_simulation', [str(lab), str(ROOT / TESTS[8]), str(ROOT)], 12),
        ('online_control_fake_uobjects', [str(lab), str(ROOT / TESTS[9]), str(ROOT), str(target)], 23),
        ('network_body_patched_upstream', [str(lab), str(ROOT / TESTS[11]), str(target)], 8),
        ('online_arena_lifecycle', [str(lab), str(ROOT / TESTS[12]), str(ROOT)], 27),
        ('online_spawn_native_bindings', [str(lab), str(ROOT / TESTS[13]), str(ROOT), str(target)], 28),
        ('cold_startup_menu_loading', [str(lab), str(ROOT / TESTS[14]), str(ROOT), str(target)], 25),
        ('combat_runtime_composition', [str(lab), str(ROOT / TESTS[15]), str(ROOT), str(target)], 5),
        ('visual_protocol_lifecycle', [str(lab), str(ROOT / TESTS[16]), str(ROOT)], 32),
        ('visual_native_bindings', [str(lab), str(ROOT / TESTS[17]), str(ROOT)], 17),
        ('visual_session_integration', [str(lab), str(ROOT / TESTS[18]), str(ROOT)], 9),
        ('deferred_launch_gate', [str(lab), str(ROOT / TESTS[19]), str(ROOT)], 15),
        ('pair_session_python', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_phantom_boss_pair_session.py', '-v'], 18),
        ('online_workbench_lifecycle', [str(lab), str(ROOT / TESTS[21]), str(ROOT), str(target)], 28),
        ('workbench_native_umg', [str(lab), str(ROOT / TESTS[22]), str(ROOT)], 16),
        ('control_contract_python', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_phantom_boss_control_contract.py', '-v'], 14),
        ('contract_bundle_python', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_phantom_boss_contract_bundle.py', '-v'], 8),
        ('control_abi_python', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_phantom_boss_control_abi.py', '-v'], 18),
        ('control_binding_python', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_phantom_boss_control_binding.py', '-v'], 13),
        ('client_auth_python', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_phantom_boss_client_auth.py', '-v'], 14),
        ('optional_contracts_python', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_phantom_boss_optional_contracts.py', '-v'], 14),
        ('online_session_composition', [str(lab), str(ROOT / TESTS[28]), str(ROOT), str(target)], 17),
        ('profile_policy_lifecycle', [str(lab), str(ROOT / TESTS[30]), str(target)], 8),
        ('boss_adapter_registry_python', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_boss_adapter_registry.py', '-v'], 12),
        ('boss_adaptation_batch_python', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_boss_adaptation_batch.py', '-v'], 9),
        *[('next_boss_identity_'+mode, [str(lab),str(ROOT/TESTS[33]),str(identity_probe),mode],1)
            for mode in ('ok','wrong_identity','wrong_config')],
        ('boss_metadata_jobs_python', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_boss_metadata_jobs.py', '-v'], 22),
        ('boss_adapter_review_python', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_boss_adapter_review.py', '-v'], 16),
        *[('boss_metadata_queue_'+mode,[str(lab),str(ROOT/TESTS[35]),str(metadata_probe),mode],1)
            for mode in ('ok','subtree','foreign_config','unavailable','wrong_identity',
                'lineage_cycle','expired','busy_timeout','frozen_clock_budget')],
        ('patched_lua_compile_only', [str(lab), str(ROOT / TESTS[3]), str(target)], 67),
    ]
    log_directory = ROOT / 'runtime/online-checks' / uuid.uuid4().hex
    log_directory.mkdir(parents=True)
    results = []
    for name, command, expected in commands:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=90)
        raw = completed.stdout + completed.stderr
        output = raw.decode('utf-8', errors='replace')
        print(output, flush=True)
        if completed.returncode:
            raise RuntimeError(name + ' failed')
        pattern = r'Ran (\d+) tests?' if name.endswith('_python') else (
            r'PASS syntax only: (\d+)' if name == 'patched_lua_compile_only' else r'PASS (\d+) (?:protocol|adapter|entry|host|enemy fence|online scope|online control|network body|online arena|spawn native|startup|combat runtime|visual|visual native|visual session|launch gate|online workbench|workbench native|online session|profile policy|identity queue|metadata jobs) groups')
        found = re.search(pattern, output)
        if not found or int(found[1]) != expected:
            raise RuntimeError(name + ' did not report its complete expected test count')
        log = log_directory / (name + '.txt')
        log.write_bytes(raw)
        results.append(dict(name=name, passed=True, groups=expected,
                            output=log.relative_to(ROOT).as_posix(), output_sha256=sha(raw)))
    if protected_files() != before:
        raise RuntimeError('Protected single-player package, entry or settings changed')
    manifest = verify_candidate(target)
    report = dict(schema=1, status='backend-milestone-only', passed=True,
        complete_mod=False, runtime_acceptance_current=False, game_started=False,
        native_relay_executed=False, installed=False, candidate=target.relative_to(ROOT).as_posix(),
        candidate_manifest_sha256=sha((target / 'candidate.json').read_bytes()),
        singleplayer_payload_files_verified=len(before['accepted-payload']),
        personal_settings_and_singleplayer_unchanged=True, upstream_commit=manifest['upstream_commit'],
        upstream_reviewed_sources=19, catalog_bosses=4, catalog_abilities=40,
        control_plane_test_groups=sum(row['groups'] for row in results[:-1]),
        syntax_checked_lua_files=67, checks=results, pending=manifest['pending'],
        source_sha256={n: sha((ROOT / n).read_bytes()) for n in (*SOURCES, *TESTS, *LAUNCH_SOURCES, 'tools/check_phantom_boss_backend.py',
            'tools/verify_phantom_boss_backend.py')})
    path = ROOT / 'evidence/adaptation/phantom-pact-backend.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.pending')
    pending.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    pending.replace(path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    run()
