"""Prepare the same isolated research lease, with separately observed Steam UI.

This module never focuses a window, captures pixels, clicks or sends keys.
The computer-use client supplies a fresh properties screenshot after review.
"""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import time

import ahua_practice as practice
import gameplay_save_probe
from mod_installation import active_mod_root, unlinked_path
import official_validation as validation
import research_scene_checkpoint as checkpoint


def source_sha():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def prepare(acceptance=False):
    active_mod_root()
    if validation.LATEST.exists():
        assert practice.read(validation.state_path()).get('restored') is True, 'preserve existing session'
    prepare_fn = validation.prepare
    minutes = 20
    if acceptance:
        from prepare_offline_acceptance import render
        source = render()
        scope = dict(vars(validation))
        exec(compile(source, __file__ + ':fresh_acceptance_lease', 'exec'), scope)
        prepare_fn, minutes = scope['prepare'], 40
    prepare_fn(launch_ready=True, local_saved=True, block_steam_overlay=True,
               block_nvidia_overlay=True, token_setting='UnstrippedToken',
               offline_validation=True, lease_minutes=minutes)
    owner = dict(state_file=str(validation.state_path()), phase='preparing',
                 created_at=validation.utc8(), observed_ui_preparation=True)
    practice.save_owner(owner)
    try:
        gameplay_save_probe.prepare()
        state = practice.read(validation.state_path())
        record = dict(state_file=state['state_file'], source_sha256=source_sha(),
                      phase='awaiting-properties-observation', session_minutes=minutes,
                      game_started=False, input_sent=False, network_active=False)
        validation.save(Path(state['work']) / 'observed-ui-preparation.json', record)
        return record
    except Exception as error:
        close_failed(owner, 'preparation_failed', error)
        raise


def close_failed(owner, phase, error):
    # Revoke launchability before cleanup, including when cleanup itself fails.
    owner['phase'] = phase
    practice.save_owner(owner)
    try:
        validation.finish()
    except Exception as cleanup_error:
        error.add_note('Research cleanup pending: ' + str(cleanup_error))
    else:
        owner['phase'] = phase + '_and_closed'
        practice.save_owner(owner)


def native_window(window_id):
    assert type(window_id) is int and window_id > 0, 'returned window ID required'
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.IsWindow.argtypes = [wintypes.HWND]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    assert user.IsWindow(window_id) and user.IsWindowVisible(window_id), 'observed window disappeared'
    pid, title = wintypes.DWORD(), ctypes.create_unicode_buffer(1024)
    user.GetWindowThreadProcessId(window_id, ctypes.byref(pid))
    user.GetWindowTextW(window_id, title, len(title))
    return dict(pid=pid.value, title=title.value)


def observed_screenshot(observation, screenshot):
    # Read the file and its timestamp before sampling the clock. Sampling first
    # can make a file flushed during the read appear to come from the future.
    raw = screenshot.read_bytes()
    modified_at = screenshot.stat().st_mtime
    now = time.time()
    assert type(observation['captured_at']) in (int, float) and 0 <= now-observation['captured_at'] <= 60, \
        'fresh computer-use observation required'
    assert raw.startswith(b'\x89PNG\r\n\x1a\n'), 'PNG encoded observation required'
    file_age = now-modified_at
    assert 0 <= file_age <= 60, f'fresh PNG file required; observed file age {file_age:.9f} seconds'
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == observation['screenshot_sha256'], 'observed screenshot changed'
    return digest


def complete(observation, *, cloud_off_reviewed=False):
    assert cloud_off_reviewed is True, 'review the current properties screenshot first'
    owner, state = practice.owned_session()
    assert owner['phase'] == 'preparing' and owner.get('observed_ui_preparation') is True
    work = Path(state['work'])
    receipt = practice.read(work / 'observed-ui-preparation.json')
    assert receipt['source_sha256'] == source_sha() and receipt['state_file'] == state['state_file']
    assert receipt['phase'] == 'awaiting-properties-observation'
    assert state.get('save_gameplay_allowed') is True and state.get('gameplay_save_probe') is True
    assert not state.get('ue4ss_deployed') and not validation.c.preflight.games_running()
    assert validation.c.baseline.formal_files() == state['formal_before']
    assert observation['state_file'] == state['state_file']
    validation.c.isolation.select_box('PBZSteamLab')
    dll = validation.c.isolation.api()
    validation.c.isolation.check_policy(dll, allow_offline_validation=True)
    assert not validation.c.host_steam_pids(dll), 'preserve host Steam'
    native = native_window(observation['window']['id'])
    pids = {p['ProcessId'] for p in validation.c.box_processes(dll)
            if p['Name'].lower() in ('steam.exe', 'steamwebhelper.exe')}
    assert native['pid'] in pids and native['title'] == observation['window']['title'], \
        'observation must belong to current research Steam properties'
    title = native['title'].casefold()
    assert ('phantom blade zero' in title or '影之刃零' in title) and not any(
        word in title for word in ('sign in', '登录', 'login')), 'exact game properties required'
    screenshot = unlinked_path(validation.ROOT / 'runtime/steam-menu-private.png')
    assert screenshot.is_relative_to(validation.ROOT / 'runtime')
    digest = observed_screenshot(observation, screenshot)
    record = dict(receipt, phase='properties-observed', observation=observation,
                  native_window=native, cloud_off_reviewed=True)
    validation.save(work / 'observed-ui-properties.json', record)
    owner.update(phase='prepared', cloud_screenshot_sha256=digest)
    practice.save_owner(owner)
    try:
        checkpoint.apply()
    except Exception as error:
        close_failed(owner, 'checkpoint_failed', error)
        raise
    return dict(prepared=True, checkpoint=checkpoint.LABEL, game_started=False,
                state_file=state['state_file'], deadline_at=state['deadline_at'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'complete'))
    parser.add_argument('--acceptance', action='store_true')
    parser.add_argument('--observation', type=Path)
    parser.add_argument('--cloud-off-reviewed', action='store_true')
    args = parser.parse_args()
    result = prepare(args.acceptance) if args.action == 'prepare' else complete(
        practice.read(args.observation), cloud_off_reviewed=args.cloud_off_reviewed)
    print(json.dumps(result, ensure_ascii=False, indent=2))
