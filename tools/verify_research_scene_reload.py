"""Replay scene-copy and closed-session checks around an explicit visual observation."""
import json
from pathlib import Path
import re

from mod_installation import ROOT, assert_closed, digest, read, unlinked_path
from research_scene_checkpoint import LABEL, save_snapshot, storage

REPORT = 'evidence/releases/research-scene-reload-20261117-170957.json'


def verify(report_path=None):
    assert_closed()
    path = Path(report_path) if report_path else ROOT / REPORT
    report = read(path)
    assert report['schema'] == 1 and report['label'] == LABEL
    session = report['session']
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    work = ROOT / 'evidence/official-validation' / session
    state_path = ROOT / 'runtime' / ('official-validation-' + session) / 'state.json'
    state = read(state_path)
    assert state['state_file'] == str(state_path) and state['work'] == str(work)
    assert state['restored'] and state['offline_validation'] and state['launch_requested_at']
    assert not state.get('network_active') and not state['remaining_box_pids']
    assert not state['formal_files_changed'] and not state['host_config_files_changed']
    post = read(work / 'postcheck.json')
    assert post['validation_state'] == str(state_path)
    for name in ('research_box_empty', 'research_loader_removed', 'validation_restored',
                 'host_registry_unchanged', 'all_temporary_network_removed'):
        assert post[name], name
    assert not any(post[name] for name in ('formal_files_changed', 'host_config_files_changed', 'remaining_games'))
    pointer = storage() / '当前研究场景.json'
    checkpoint = read(pointer)
    saved = unlinked_path(checkpoint['directory'])
    assert saved.parent == storage() and checkpoint['label'] == LABEL
    assert read(saved / 'checkpoint.json') == checkpoint
    assert save_snapshot(saved) == checkpoint['files']
    applied = read(work / 'research-checkpoint-applied.json')
    assert applied['checkpoint'] == checkpoint and applied['formal_files_modified'] is False
    assert report['checkpoint_manifest_sha256'] == digest(saved / 'checkpoint.json')
    assert report['checkpoint_file_count'] == len(checkpoint['files'])
    log = work / 'UE4SS.log'
    assert log.is_file() and 'SPAWN_ATTEMPT=' not in log.read_text(encoding='utf-8', errors='replace')
    observation = report['observation']
    assert observation['method'] == 'assistant_visual_observation_via_computer_use'
    assert observation['title_continue_observed'] is True
    assert observation['direct_open_area_spawn_observed'] is True
    assert observation['no_travel_or_teleport_performed'] is True
    assert observation['mod_not_armed'] is True
    assert observation['landmarks']
    required = {state_path, work / 'postcheck.json', work / 'research-checkpoint-applied.json', log,
                ROOT / 'tools/verify_research_scene_reload.py'}
    assert set(report['sources']) == {p.relative_to(ROOT).as_posix() for p in required}
    assert all(digest(ROOT / name) == expected for name, expected in report['sources'].items())
    return dict(reload_verified=True, session=session, label=LABEL,
                checkpoint_file_count=len(checkpoint['files']), copy_integrity_verified=True,
                direct_spawn_visually_observed=True, formal_postcheck_passed=True,
                observation_method=observation['method'], game_started=False)


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
