"""用途：一次核对交付源码语法、窗口和已有实机证据；不启动Steam或游戏。"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    changed = ['tools/ahua_practice.py', 'tools/ahua_practice_window.py',
               'tools/record_interactive_milestone.py', 'tools/check_ahua_delivery.py',
               'tools/finalize_ahua_delivery.py', 'tools/workbench.py', 'tools/run_control_lifecycle_probe.py',
               'tools/research_game_menu.py', 'tools/retire_restored_ahua.py', 'tools/test_ahua_expanded_runtime.py',
               'tools/finalize_ahua_v02.py', 'tools/inspect_owned_training_positions.py', 'tools/test_ahua_skill_lab.py',
               'tools/collect_ahua_skill_lab.py', 'tools/finalize_ahua_v03.py',
               'tools/inspect_ahua_attack_lifecycle.py', 'tools/load_ahua_lifecycle_classes.py',
               'tools/inspect_ahua_combo_tree.py', 'tools/inspect_camera_contract.py',
               'tools/finalize_ahua_attack_research.py',
               'tests/test_attack_call_candidates.py', 'tests/test_combo_tree_contract.py',
               'tools/player_keymap.py','tests/test_player_keymap.py','tools/probe_camera_cleanup.py',
               'tools/collect_ahua_controls.py','tools/control_action_evidence.py','tests/test_control_action_evidence.py',
               'tools/inspect_boss_lifecycle_contract.py','tests/test_retire_preconditions.py',
               'tools/postcheck_native_diagnostic.py','tools/collect_ahua_scene_reload.py','tools/player_settings.py',
               'tools/inspect_player_ui_contract.py','tools/player_ui_contract.py','tools/player_overlay.py',
               'tools/capture_player_overlay.py','tests/test_player_overlay.py','tools/inspect_arena_contract.py','tools/pbz_readonly.py',
               'tools/arena_contract.py','tools/rearm_after_world.py','tests/test_arena_contract.py',
               'tools/record_player_entry_milestone.py','tests/test_player_settings.py','tools/inspect_offline_window.py',
               'tools/collect_combo_scheduler.py','tools/test_native_combo_player.py',
               'tools/collect_native_combo_player.py','tools/inspect_game_flow_contract.py',
               'tools/inspect_ability_damage_contract.py','tools/collect_auto_world_reassembly.py',
               'tests/test_auto_world_reassembly.py','tools/test_incoming_combat.py',
               'tools/collect_incoming_combat.py','tests/test_incoming_combat_evidence.py',
               'tools/test_ahua_skill_batch.py','tools/inspect_owned_residuals.py',
               'tools/collect_skill_acceptance.py','tools/capture_owned_gc.py','tests/test_skill_acceptance_evidence.py',
               'tools/test_player_skill_batch.py','tests/test_research_input_dispatch.py','tests/test_player_skill_wait.py',
               'tools/pbz_ue4ss_baseline.py','tests/test_loader_build_record.py',
               'tools/practice_lease.py','tests/test_practice_lease.py',
               'tools/collect_practice_stability.py','tests/test_practice_stability.py',
               'tools/collect_active_disposal.py','tools/test_active_disposal.py','tests/test_active_disposal_evidence.py',
               'tools/test_active_world_transition.py','tests/test_map_travel_loader.py',
               'tools/mod_installation.py','tools/mod_manager_window.py','tools/build_ahua_candidate.py',
               'tools/build_ahua_acceptance_matrix.py','tools/collect_navigation_layouts.py',
               'tools/collect_map_travel_guard.py','tests/test_mod_installation.py',
               'tests/test_map_travel_evidence.py','tests/test_navigation_evidence.py',
               'tools/run_ahua_milestone_acceptance.py','tests/test_milestone_batch_gate.py',
               'tools/player_target_readiness.py','tests/test_player_target_readiness.py',
               'tools/collect_release_readiness.py','tests/test_release_readiness.py','tools/release_ahua.py',
               'tools/run_ahua_catalog_acceptance.py','tools/ahua_catalog_plan.py','tests/test_ahua_catalog_plan.py',
               'tools/collect_performance_comparison.py','tools/collect_performance_hotfix.py',
               'tools/package_performance_hotfix.py',
               'tools/probe_cache_after_world.py',
               'tests/test_performance_comparison.py',
               'tools/player_status_stream.py','tests/test_player_status_stream.py',
               'tools/workbench_support.py','tests/test_workbench_support.py',
               'tools/boss_adaptation_workflow.py','tools/build_boss_identity_probe.py',
               'tools/build_boss_adaptation_batch.py','tools/run_boss_identity_batch.py',
               'tools/collect_boss_resource_names.py','tools/run_boss_offline_milestone.py',
               'tools/collect_boss_identity.py','tools/boss_candidate_gate.py','tests/test_boss_identity_collection.py',
               'tools/official_validation.py','tools/validation_cleanup_lock.py','tests/test_validation_cleanup_lock.py',
               'tools/test_boss_workbench_runtime.py','tools/collect_boss_candidate_acceptance.py',
               'tools/run_boss_candidate_milestone.py','tools/collect_boss_workbench_acceptance.py',
               'tests/test_boss_workbench_acceptance.py',
               'tools/build_boss_profile_candidate.py','tools/test_multi_boss_switching.py',
               'tools/collect_multi_boss_switching.py','tests/test_boss_candidate_acceptance.py',
               'tools/release_boss_workbench.py','tools/test_player_stability_tail.py',
               'tests/test_multi_boss_switching_evidence.py','tools/collect_workbench_recovery.py',
               'tests/test_workbench_recovery_evidence.py','tests/test_workbench_release_runtime.py',
               'tools/test_dead_target_recovery_runtime.py','tests/test_dead_target_runtime.py']
    for name in changed:
        ast.parse((ROOT / name).read_text(encoding='utf-8'), filename=name)
    scripts = sorted((ROOT / 'mod/PBZBossControl').rglob('*.lua'))
    # 用途：仅编译检查Lua语法，不执行游戏脚本。
    syntax = ROOT / 'runtime/check-delivery-syntax.lua'
    syntax.write_text('local root=assert(arg[1])\n' + '\n'.join(
        'assert(loadfile(root.."/' + path.relative_to(ROOT).as_posix() + '"))' for path in scripts)
        + '\nprint("All delivery Lua files parse")\n', encoding='utf-8')
    lua = ROOT.parent / 'build/lua-harness/Release/lua-lab.exe'
    checks = [('lua_syntax', [str(lua), str(syntax), str(ROOT)]),
              ('player_overlay',[sys.executable,str(ROOT/'tests/test_player_overlay.py')]),
              ('overlay_smoke',[sys.executable,str(ROOT/'tools/player_overlay.py'),'--smoke']),
              ('window_smoke', [sys.executable, str(ROOT / 'tools/ahua_practice_window.py'), '--smoke']),
              ('attack_call_candidates', [sys.executable, str(ROOT / 'tests/test_attack_call_candidates.py')]),
              ('combo_tree_contract', [sys.executable, str(ROOT / 'tests/test_combo_tree_contract.py')]),
              ('player_keymap', [sys.executable, str(ROOT / 'tests/test_player_keymap.py')]),
              ('control_action_evidence', [sys.executable, str(ROOT / 'tests/test_control_action_evidence.py')]),
              ('retire_preconditions', [sys.executable, str(ROOT / 'tests/test_retire_preconditions.py')])]
    checks.append(('arena_contract',[sys.executable,str(ROOT/'tests/test_arena_contract.py')]))
    checks.append(('player_settings',[sys.executable,str(ROOT/'tests/test_player_settings.py')]))
    checks.append(('auto_world_evidence',[sys.executable,str(ROOT/'tests/test_auto_world_reassembly.py')]))
    checks.append(('incoming_combat_evidence',[sys.executable,str(ROOT/'tests/test_incoming_combat_evidence.py')]))
    checks.append(('skill_acceptance_evidence',[sys.executable,str(ROOT/'tests/test_skill_acceptance_evidence.py')]))
    checks.append(('research_input_dispatch',[sys.executable,str(ROOT/'tests/test_research_input_dispatch.py')]))
    checks.append(('player_skill_wait',[sys.executable,str(ROOT/'tests/test_player_skill_wait.py')]))
    checks.append(('loader_build_record',[sys.executable,str(ROOT/'tests/test_loader_build_record.py')]))
    checks.append(('practice_lease',[sys.executable,str(ROOT/'tests/test_practice_lease.py')]))
    checks.append(('practice_stability',[sys.executable,str(ROOT/'tests/test_practice_stability.py')]))
    checks.append(('active_disposal_evidence',[sys.executable,str(ROOT/'tests/test_active_disposal_evidence.py')]))
    checks.append(('map_travel_loader',[sys.executable,str(ROOT/'tests/test_map_travel_loader.py')]))
    checks.append(('mod_installation',[sys.executable,str(ROOT/'tests/test_mod_installation.py')]))
    checks.append(('mod_manager_smoke',[sys.executable,str(ROOT/'tools/mod_manager_window.py'),'--smoke']))
    checks.append(('map_travel_evidence',[sys.executable,str(ROOT/'tests/test_map_travel_evidence.py')]))
    checks.append(('navigation_evidence',[sys.executable,str(ROOT/'tests/test_navigation_evidence.py')]))
    checks.append(('catalog_export',[str(lua),str(ROOT/'tools/export_ahua_capabilities.lua'),str(ROOT)]))
    checks.append(('milestone_batch_gate',[sys.executable,str(ROOT/'tests/test_milestone_batch_gate.py')]))
    checks.append(('player_target_readiness',[sys.executable,str(ROOT/'tests/test_player_target_readiness.py')]))
    checks.append(('release_readiness',[sys.executable,str(ROOT/'tests/test_release_readiness.py')]))
    checks.append(('catalog_missing_plan',[sys.executable,str(ROOT/'tests/test_ahua_catalog_plan.py')]))
    checks.append(('performance_evidence',[sys.executable,str(ROOT/'tests/test_performance_comparison.py')]))
    checks.append(('status_stream',[sys.executable,str(ROOT/'tests/test_player_status_stream.py')]))
    checks.append(('workbench_capability',[sys.executable,str(ROOT/'tests/test_workbench_support.py')]))
    checks.append(('workbench_acceptance',[sys.executable,str(ROOT/'tests/test_boss_workbench_acceptance.py')]))
    checks.append(('boss_candidate_acceptance',[sys.executable,str(ROOT/'tests/test_boss_candidate_acceptance.py')]))
    checks.append(('multi_boss_role_evidence',[sys.executable,str(ROOT/'tests/test_multi_boss_switching_evidence.py')]))
    checks.append(('dead_target_recovery_evidence',[sys.executable,str(ROOT/'tests/test_workbench_recovery_evidence.py')]))
    checks.append(('dead_target_runtime',[sys.executable,str(ROOT/'tests/test_dead_target_runtime.py')]))
    checks.append(('workbench_runtime_release_gate',[sys.executable,str(ROOT/'tests/test_workbench_release_runtime.py')]))
    checks.append(('boss_identity_collection',[sys.executable,str(ROOT/'tests/test_boss_identity_collection.py')]))
    checks.append(('validation_cleanup_lock',[sys.executable,str(ROOT/'tests/test_validation_cleanup_lock.py')]))
    # 用途：只重测有直接关系的输入、主角保护和运行调度；复用未改动的其他历史通过记录。
    for name in ('test_player_protection.lua', 'test_input_barrier.lua', 'test_runtime.lua', 'test_practice_readiness.lua',
                 'test_boss_workbench.lua','test_workbench_input.lua','test_ue_host.lua','test_boss_candidate.lua','test_ue_input_cache.lua',
                 'test_session.lua', 'test_native_bridge.lua', 'test_combo_scheduler.lua', 'test_idle_world_watch.lua', 'test_incoming_combat_trial.lua', 'test_target_selector.lua', 'test_target_transition.lua',
                 'test_practice_initialization.lua', 'test_owned_readiness.lua', 'test_owned_initialization.lua', 'test_skill_lab.lua', 'test_remote_control.lua', 'test_input_driver.lua',
                 'test_ue_calls.lua', 'test_observation_scope.lua','test_keymap.lua','test_object_lifecycle.lua','test_map_travel_guard.lua',
                 'test_combat_identity.lua','test_ue_combat.lua','test_death_trial_guard.lua','test_owned_disposal_trial.lua','test_boss_catalog.lua','test_world_boundary.lua','test_player_hud.lua','test_ue_player_ui.lua','test_arena_layout.lua','test_ue_arena_layout.lua','test_player_entry.lua'):
        checks.append((name, [str(lua), str(ROOT / 'tests' / name), str(ROOT)]))
    results = []
    for label, command in checks:
        run = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=40,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        results.append({'name': label, 'exit_code': run.returncode,
                        'stdout': run.stdout.decode('utf-8', errors='replace'),
                        'stderr': run.stderr.decode('utf-8', errors='replace')})
        print(label + ': ' + ('PASS' if run.returncode == 0 else 'FAIL'))
    source_names=sorted(set(changed+[p.relative_to(ROOT).as_posix()for p in scripts]
        +[p.relative_to(ROOT).as_posix()for p in (ROOT/'tests').glob('test_*.lua')]))
    result = {'at': datetime.now().astimezone().isoformat(), 'passed': all(r['exit_code'] == 0 for r in results),
              'python_syntax_files': len(changed), 'lua_syntax_files': len(scripts), 'checks': results,
              'game_started': False, 'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                  for name in source_names}}
    target = ROOT / 'evidence/adaptation/ahua-delivery-local-checks.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
