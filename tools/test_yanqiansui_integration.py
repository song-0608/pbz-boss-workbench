"""Consolidated ordinary workbench roundtrip, then leave YanQianSui ready for a world cycle."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time

import ahua_practice as practice
import research_game_menu as menu
from test_player_skill_batch import wait_for
from control_action_evidence import restoration_result
from collect_multi_boss_switching import movement_camera_proof

IDENTIFIER = '073_yanqiansui'
OWNED = ('boss', 'boss_controller', 'target', 'target_controller', 'extra_target', 'extra_target_controller')


def main(finish_world=False):
    owner, state = practice.owned_session()
    assert owner['phase'] == 'armed' and owner.get('player_entry') and owner.get('workbench')
    assert not owner.get('boss_candidate') and not owner.get('scene_transition_trial')
    path = practice.log_path(state)
    work = Path(state['work'])
    deployment = practice.read(work / 'control-lifecycle-deployment.json')
    assert deployment['boss_id'] == 'ahua_guitoudao'
    assert 'profiles/yanqiansui.lua' in deployment['module_source_sha256']
    target = work / 'yanqiansui-integration-actions.json'
    if finish_world:
        report = practice.read(target)
        assert report['roundtrip_passed'] is True and not report.get('world_finished')
        assert report['state_file'] == state['state_file']
        raw = path.read_text(encoding='utf-8', errors='replace')
        assert report['lines'] == raw[report['log_offset']:report['log_end']].splitlines()
        later = raw[report['world_scope_offset']:]
        assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)', later) == [IDENTIFIER, IDENTIFIER]
        assert 'IDLE_WORLD_OBJECTS_RETIRED=' in later and 'WORLD_REASSEMBLY_AWAITING_GAMEPLAY=' in later
    else:
        assert not target.exists(), 'Preserve existing integration attempt'
        assert min(state['deadline_unix'], state['control_probe_expires_at']) - time.time() > 420
        report = {'state_file': state['state_file'], 'log_offset': len(path.read_text(encoding='utf-8', errors='replace')),
                  'checks': [], 'roundtrip_passed': False, 'world_finished': False}

    def raw():
        return path.read_text(encoding='utf-8', errors='replace')

    def save():
        current = raw()
        report.update(log_end=len(current), lines=current[report['log_offset']:].splitlines())
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def send(action, token):
        offset = len(raw())
        menu.click(0, 0, 2560, 1600, action)
        tail = wait_for(path, offset, lambda t: token in t, 95 if action == 'control_workbench_confirm' else 10, True)
        assert token in tail, 'Missing ' + token
        return offset, tail

    def skills(names, interrupt=False):
        result = subprocess.run([sys.executable, str(practice.ROOT / 'tools/test_player_skill_batch.py'),
            *names, *(['--interrupt'] if interrupt else [])], cwd=practice.ROOT, timeout=250,
            capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
        print(result.stdout, flush=True)
        assert result.returncode == 0, result.stderr or result.stdout

    def open_active():
        offset, _ = send('control_workbench_toggle', 'WORKBENCH_INPUT_LOCKED=')
        tail = wait_for(path, offset, lambda t: restoration_result(t, 'auto_exit')['passed'], 10)
        assert restoration_result(tail, 'auto_exit')['passed']

    def choose(identifier, steps):
        for _ in range(abs(steps)):
            send('control_workbench_down' if steps > 0 else 'control_workbench_up',
                 'workbench_down success=true' if steps > 0 else 'workbench_up success=true')
        offset, tail = send('control_workbench_confirm', 'PLAYER_ENTRY_READY=' + identifier)
        assert 'WORKBENCH_BOSS_SELECTED=' + identifier in tail
        assert all('OWNED_DESTROY_VERIFIED=' + name + '|engine_unusable=true' in tail for name in OWNED)
        assert 'WORKBENCH_INPUT_RESTORED=true' in tail
        time.sleep(2)
        return offset, tail

    try:
        save()
        if finish_world:
            skills(['skill_01'])
            from collect_auto_world_reassembly import witness
            witness()
            report['world_finished'] = True
            report['checks'].append('new_world_ordinary_skill_and_restoration')
            return 0
        send('control_enter', '[PBZBossControl] enter success=true state=ACTIVE')
        open_active()
        report['checks'].append('active_ahua_open_restores_player')
        choose(IDENTIFIER, 2)
        report['checks'].append('ahua_to_yanqiansui_cleanup')
        save()
        skills(['skill_01', 'heavy_01', 'skill_02', 'dash'])
        skills(['skill_01', 'heavy_01', 'skill_02', 'dash'], interrupt=True)
        report['checks'].append('four_ordinary_bindings_natural_cancel')
        start, _ = send('control_enter', '[PBZBossControl] enter success=true state=ACTIVE')
        baseline = wait_for(path, start, lambda t: 'CAMERA_ARM_YAW=' in t, 6)
        assert 'CAMERA_ARM_YAW=' in baseline
        menu.click(0, 0, 2560, 1600, 'control_forward')
        menu.click(0, 0, 2560, 1600, 'control_look')
        after_input = len(raw())
        turned = wait_for(path, after_input, lambda t: 'CAMERA_ARM_YAW=' in t, 9)
        assert 'CAMERA_ARM_YAW=' in turned
        open_active()
        motion = movement_camera_proof(raw()[start:])
        assert motion['passed'], 'ordinary YanQianSui movement/camera required'
        report['movement_camera'] = motion
        report['checks'].append('ordinary_movement_camera_and_auto_restore')
        choose('ahua_guitoudao', -2)
        skills(['skill_01'])
        skills(['skill_08'], interrupt=True)
        report['checks'].append('return_ahua_controls_restored')
        send('control_workbench_toggle', 'WORKBENCH_INPUT_LOCKED=')
        _, tail = choose(IDENTIFIER, 2)
        current = raw()
        report['world_scope_offset'] = current.rfind('PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=' + IDENTIFIER)
        assert report['world_scope_offset'] > report['log_offset']
        skills(['skill_01'])
        report['checks'].append('yanqiansui_ready_for_original_menu_world_cycle')
        assert not any(token in current[report['log_offset']:] for token in
            ('state=FAULTED', 'PBZ_CONTROL_LIFECYCLE:ISSUE_', 'HUD_UNAVAILABLE=', 'PBZ_CONTROL_RESTORE:FAILED='))
        report['roundtrip_passed'] = True
        return 0
    except Exception as error:
        report['error'] = str(error)
        return 1
    finally:
        save()
        print(json.dumps({k: v for k, v in report.items() if k != 'lines'}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finish-world', action='store_true')
    raise SystemExit(main(parser.parse_args().finish_world))
