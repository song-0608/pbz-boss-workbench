"""Replay closed ordinary selection, exact native actions and every added World cycle."""
import argparse
from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, sha, write_json
from collect_skill_acceptance import analyze
from control_action_evidence import restoration_result
from four_boss_integration_workflow import modules
from player_target_readiness import target_cycle_verified
from candidate_effect_scope import local_effect
from expanded_boss_world import proof as world_proof, definition
import expanded_boss_integration_workflow as workflow
import build_expanded_boss_candidate as candidate
import build_player_experience_candidate as experience_candidate
import expanded_boss_developer_bundle as developer_bundle
from mod_installation import MANIFEST, unlinked_path, validate_package

BAD = ('state=FAULTED', 'PBZ_CONTROL_LIFECYCLE:ISSUE_', 'PBZ_CONTROL_RESTORE:FAILED=',
       '[Lua::execute_file]', 'HUD_UNAVAILABLE=')
OWNED = ('boss', 'boss_controller', 'target', 'target_controller', 'extra_target', 'extra_target_controller')
SOURCES = ('tools/collect_expanded_boss_player.py', 'tools/run_expanded_boss_player_batch.py',
           'tools/expanded_boss_world.py', 'tests/test_expanded_boss_world.py', 'tests/test_expanded_boss_player.py')


def closed_session(session, flow, package, manifest):
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    state_path = ROOT / 'runtime' / ('official-validation-' + session) / 'state.json'
    read = lambda p: json.loads(p.read_bytes())
    state = read(state_path); work = ROOT / 'evidence/official-validation' / session
    assert state['restored'] is True and Path(state['work']) == work
    post_path = work / 'postcheck.json'; post = read(post_path)
    assert post['validation_state'] == str(state_path)
    assert all(post[k] is True for k in ('validation_restored', 'research_box_empty',
                                       'research_loader_removed', 'host_registry_unchanged'))
    assert not any(post[k] for k in ('formal_files_changed', 'host_config_files_changed', 'remaining_games'))
    deployments = list(work.glob('control-lifecycle-deployment-*.json')); assert len(deployments) == 1
    deployed = read(deployments[0])
    assert deployed['player_entry'] and not deployed.get('boss_candidate')
    assert Path(deployed['mod_source_directory']) == package / 'PBZBossControl'
    assert deployed['module_source_sha256'] == modules(manifest)
    raw_path = work / 'UE4SS.log'; raw = raw_path.read_text(encoding='utf-8', errors='replace')
    return state_path, work, raw, [state_path, post_path, raw_path, *deployments]


def verified_dispatches(work, state_path, flow, package):
    read = lambda p: json.loads(p.read_bytes())
    sources = []; dispatches = []
    gates = [(p, read(p)) for p in work.glob('experience-input-*.json')]
    for path in work.glob('experience-dispatch-*.json'):
        row = read(path)
        assert row['state_file'] == str(state_path) and Path(row['workflow']) == flow
        assert row['candidate_manifest_sha256'] == sha(package / 'pbz-release.json')
        assert row['input_sent'] is True and not row.get('error') and row['gameplay_verified'] is False
        assert datetime.fromisoformat(row['dispatch_at']).timestamp() < row['gate_expires_at']
        original = dict(row)
        for key in ('dispatch_at', 'native_dispatch'): original.pop(key, None)
        original['input_sent'] = False
        matches = [p for p, value in gates if value == original]; assert len(matches) == 1
        dispatches.append(row); sources.extend([path, matches[0]])
    dispatches.sort(key=lambda r: r['log_offset'])
    offsets = [row['log_offset'] for row in dispatches]; assert offsets == sorted(set(offsets))
    return dispatches, sources


@contextmanager
def historical_profile_base(package, root=ROOT):
    """Replay development evidence against its hashed v4 base after an upgrade.

    Only the developer-bundle dependency is pinned. Installed payload validation,
    native evidence, dispatch gates and every source/hash check remain in force.
    No installation receipt or historical file is changed.
    """
    package = unlinked_path(package)
    recorded = json.loads((package / MANIFEST).read_bytes())
    identifier = recorded['experience_base_release']
    assert identifier == experience_candidate.BASE
    base = unlinked_path(root / 'releases' / identifier)
    assert sha(base / MANIFEST) == recorded['experience_base_manifest_sha256']
    manifest = validate_package(base)
    assert manifest['release_id'] == identifier and manifest['status'] == 'release'
    assert manifest['runtime_acceptance_current']
    original = developer_bundle.active_mod_root
    def pinned(requested_root=root):
        assert Path(requested_root).resolve() == Path(root).resolve()
        return base / 'PBZBossControl'
    developer_bundle.active_mod_root = pinned
    try:
        yield base
    finally:
        developer_bundle.active_mod_root = original


def collect(session, flow, world_sessions=()):
    recorded = json.loads((flow / 'manifest.json').read_bytes())
    with historical_profile_base(Path(recorded['candidate'])):
        return _collect(session, flow, world_sessions)


def _collect(session, flow, world_sessions=()):
    frozen = workflow.verify(flow); package = Path(frozen['candidate']); manifest = candidate.verify(package)
    read = lambda p: json.loads(p.read_bytes())
    state_path, work, raw, sources = closed_session(session, flow, package, manifest)
    batch_path = work / 'expanded-boss-player-batch.json'; batch = read(batch_path)
    assert batch['passed'] and batch['returned_to_ahua'] and not batch.get('error')
    assert batch['state_file'] == str(state_path) and batch['workflow'] == str(flow)
    assert batch['candidate_manifest_sha256'] == sha(package / 'pbz-release.json')
    start, end = batch['log_offset'], batch['log_end']
    assert 0 <= start < end <= len(raw) and batch['lines'] == raw[start:end].splitlines()
    segment = raw[start:end]; assert not any(token in segment for token in BAD)
    additions = manifest['expansion_profiles']; ids = [row['id'] for row in additions]
    assert [r['id'] for r in batch['roles']] == ids
    assert re.findall(r'WORKBENCH_BOSS_SELECTED=([^\r\n]+)', segment) == ids + ['ahua_guitoudao']
    assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)', segment) == ids + ['ahua_guitoudao']
    sources.extend([batch_path, package / 'pbz-release.json', flow / 'manifest.json'])
    dispatches, dispatch_sources = verified_dispatches(work, state_path, flow, package)
    sources.extend(dispatch_sources); offsets = [row['log_offset'] for row in dispatches]
    actions_path = work / 'player-extra-skill-actions.json'; actions = read(actions_path); sources.append(actions_path)
    roles = []
    for addition, checkpoint in zip(additions, batch['roles']):
        identifier = addition['id']; a, b = checkpoint['log_offset'], checkpoint['log_end']
        assert start <= a < b <= end and checkpoint['passed']
        assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)', raw[:a])[-1] == identifier
        native = read(ROOT / addition['evidence'])['accepted_skills']
        selected = [(index, row) for index, row in enumerate(dispatches) if a <= row['log_offset'] < b]
        assert [r['action'] for _, r in selected] == ['enter', 'shift_cast', 'lock', 'lock', 'cycle_target', 'exit']
        for index, row in selected:
            x = row['log_offset']; y = min(b, offsets[index + 1] if index + 1 < len(offsets) else b)
            text = raw[x:y]; action = row['action']
            if action == 'enter':
                assert 'enter success=true state=ACTIVE' in text and 'TARGET_CAMERA_LOCK=true|initial' in text
            elif action == 'shift_cast':
                result = analyze(text, 'skill_01'); completion = result['natural_completion']
                assert result['ability_class_short'] == native['skill_01']['class_path'].rsplit('.', 1)[-1]
                assert completion and (completion['damage_observed'] or completion['movement_observed'])
                assert completion['distance'] <= 3000 and '[PBZBossControl] slot1 success=true state=ACTIVE' in text
            elif action == 'lock':
                expected = 'false' if row is selected[2][1] else 'true'
                assert 'TARGET_CAMERA_LOCK=' + expected + '|manual' in text and 'lock_target success=true state=ACTIVE' in text
            elif action == 'cycle_target': assert target_cycle_verified(text)
            else:
                boundary = text.find('[PBZBossControl] enter success=')
                assert restoration_result(text[:boundary] if boundary >= 0 else text, 'exit')['passed']
        seen = {('skill_01', False)}
        for action in actions:
            x, y = action['log_offset'], action['log_end']
            if y <= a or x >= b: continue
            assert a <= x < y <= b and action['state_file'] == str(state_path)
            text = raw[x:y]; assert action['lines'] == text.splitlines() and action['passed']
            skill = action['skill']; key = (skill, action['interrupt'])
            assert skill in native and key not in seen; seen.add(key)
            result = local_effect(analyze(text, skill), text, 3000)
            assert result['ability_class_short'] == native[skill]['class_path'].rsplit('.', 1)[-1]
            assert result['local_displacement_verified'] and result['restoration']['passed']
            assert result['active_cancel_and_restoration'] if action['interrupt'] else result['natural_completion']
        assert seen == {(skill, interrupt) for skill in addition['skills'] for interrupt in (False, True)}
        roles.append(dict(id=identifier, skills=addition['skills'], ordinary_native_actions_verified=True,
            shifted_movement_cast_verified=True, lock_and_target_cycle_verified=True, restoration_verified=True))
    world_sessions = tuple(world_sessions) or (session,)
    assert len(set(world_sessions)) == len(world_sessions), 'Duplicate World session'
    contexts = {}
    for identifier_session in world_sessions:
        sp, wp, text, paths = closed_session(identifier_session, flow, package, manifest)
        inputs, paths_inputs = verified_dispatches(wp, sp, flow, package)
        contexts[identifier_session] = (sp, wp, text, inputs)
        sources.extend(paths + paths_inputs)
    worlds = []; world_counts = dict.fromkeys(world_sessions, 0)
    for identifier in ids:
        matches = [(s, c) for s, c in contexts.items() if (c[1] / ('expanded-world-' + identifier + '.json')).exists()]
        assert len(matches) == 1, 'One exact closed World proof per added role required'
        world_session, (world_state, world_work, world_raw, world_inputs) = matches[0]
        path = world_work / ('expanded-world-' + identifier + '.json'); row = read(path)
        assert row['passed'] and row['pre_world_passed'] and not row.get('error')
        assert row['state_file'] == str(world_state) and row['workflow'] == str(flow)
        assert row['candidate_manifest_sha256'] == sha(package / 'pbz-release.json')
        a, b = row['log_offset'], row['log_end']
        assert 0 <= row['world_scope_offset'] <= a < b <= len(world_raw)
        assert row['lines'] == world_raw[a:b].splitlines()
        assert not any(token in world_raw[a:b] for token in BAD)
        selected = [r for r in world_inputs if a <= r['log_offset'] < b]
        assert [r['action'] for r in selected] == ['enter', 'shift_cast', 'exit'] * 2
        cls, ability = definition(manifest, identifier)
        result = world_proof(world_raw[row['world_scope_offset']:b], identifier, cls, ability)
        assert result['passed'] and result == row['world_cycle']
        worlds.append(dict(id=identifier, session=world_session, passed=True,
            primary_damage_observed=result['skill_natural_damage']))
        world_counts[world_session] += 1; sources.append(path)
    for identifier_session, count in world_counts.items():
        assert count > 0, 'Unused World session'
        menus_path = contexts[identifier_session][1] / 'settings-menu-actions.json'; menus = read(menus_path)
        confirms = [r for r in menus if r['purpose'] == 'control_menu_confirm']
        continues = [r for r in menus if r['purpose'] == 'control_menu_continue']
        assert len(confirms) == len(continues) == count
        assert all(a['at'] < b['at'] for a, b in zip(confirms, continues))
        sources.append(menus_path)
    result = dict(schema=1, passed=True, session=session, candidate=str(package),
        candidate_manifest_sha256=sha(package / 'pbz-release.json'), workflow=str(flow), roles=roles,
        world_sessions=list(world_sessions), world_cycles=worlds,
        module_source_sha256=modules(manifest), installed=False, complete_mod=False,
        sources={p.relative_to(ROOT).as_posix():sha(p) for p in sources},
        collector_sources={name:sha(ROOT / name) for name in SOURCES})
    output = work / ('expanded-boss-player-acceptance-' + sha(ROOT / SOURCES[0])[:16] + '.json')
    if output.exists(): assert read(output) == result
    else: write_json(output, result)
    return output, result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('session')
    parser.add_argument('--world-session', action='append', default=[])
    parser.add_argument('workflow', type=Path); args = parser.parse_args()
    path, report = collect(args.session, args.workflow.resolve(), args.world_session)
    print(json.dumps(dict(report=str(path), passed=report['passed'], roles=report['roles']), ensure_ascii=False))
