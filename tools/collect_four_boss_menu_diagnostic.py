"""Archive a bounded incomplete World attempt without promoting it to acceptance."""
import argparse
import json
import re
from pathlib import Path
from boss_adaptation_workflow import ROOT, sha, write_json
from four_boss_ordinary_reuse import verify


def collect(session):
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    state_path = ROOT / 'runtime' / ('official-validation-' + session) / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    work = ROOT / 'evidence/official-validation' / session
    def read(name):
        return json.loads((work / name).read_text(encoding='utf-8'))
    assert state['restored'] and Path(state['work']).resolve() == work.resolve()
    post = read('postcheck.json')
    assert post['validation_state'] == str(state_path)
    assert all(post[k] for k in ('research_box_empty', 'research_loader_removed', 'host_registry_unchanged'))
    assert not any(post[k] for k in ('formal_files_changed', 'host_config_files_changed', 'remaining_games'))
    deployments = list(work.glob('control-lifecycle-deployment-*.json'))
    assert len(deployments) == 1
    deployment = read(deployments[0].name)
    _, sources = verify(deployment['module_source_sha256'])
    action = read('youlong-world-missing.json')
    raw = (work / 'UE4SS.log').read_text(encoding='utf-8', errors='replace')
    assert action['state_file'] == str(state_path) and action['ready'] and not action['passed']
    assert action['error'].startswith('AssertionError: Traceback')
    assert "state['control_probe_expires_at']-20" in action['error']
    assert action['lines'] == raw[action['log_offset']:action['log_end']].splitlines()
    scope = raw[action['world_scope_offset']:]
    assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)', scope) == ['056_youlong', '056_youlong']
    ready = scope.rfind('PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=056_youlong')
    assert '[PBZBossControl] enter success=true' not in scope[ready:]
    retired = scope.index('IDLE_WORLD_OBJECTS_RETIRED=')
    waiting = scope.index('WORLD_REASSEMBLY_WAIT=', retired)
    gameplay = scope.index('WORLD_REASSEMBLY_AWAITING_GAMEPLAY=', waiting)
    assert retired < waiting < gameplay < ready
    menus = read('settings-menu-actions.json')
    assert sum(r['purpose'] == 'control_menu_confirm' for r in menus) == 1
    assert sum(r['purpose'] == 'control_menu_continue' for r in menus) == 1
    held = read('native-menu-input-actions.json')
    assert len(held) == 3
    assert all(r['state_file'] == str(state_path) and r['seconds'] == .35
               and r['result']['only_research_game_targeted'] for r in held)
    paths = [state_path, work/'postcheck.json', work/'UE4SS.log', *deployments,
             *(work/n for n in ('youlong-world-missing.json', 'settings-menu-actions.json',
                               'native-menu-input-actions.json', 'player-extra-skill-actions.json',
                               'native-menu-baseline.png', 'native-menu-after-first-restore.png')),
             ROOT/'tools/collect_four_boss_menu_diagnostic.py', ROOT/'tools/native_menu_input.py',
             ROOT/'tools/test_four_boss_world_missing.py']
    sources.update({p.relative_to(ROOT).as_posix(): sha(p) for p in paths})
    result = dict(session=session, formal_postcheck_passed=True,
        native_menu_350ms_visually_observed=True,
        automatic_youlong_reassembly_logged=True,
        post_world_skill_dispatched=False, new_profile_world_cycle_verified=False,
        complete_mod=False, playable=False,
        reason='Fresh post-World action rejected by remaining-time gate before dispatch; no full acceptance.',
        module_source_sha256=deployment['module_source_sha256'], sources=sources)
    output = ROOT/'research/boss-adaptation/developer-attempt-receipts'/('four-boss-menu-diagnostic-'+session+'.json')
    assert not output.exists()
    write_json(output, result)
    return {'receipt': str(output), 'complete_mod': False, 'world_cycle_verified': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('session'); a = p.parse_args()
    print(json.dumps(collect(a.session), ensure_ascii=False))
