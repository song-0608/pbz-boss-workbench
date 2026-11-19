"""One bounded, editor-only six-role render pass; never opens the game."""
import datetime
import json
from pathlib import Path
import time
import unreal as ue

BASE = Path(r'E:\项目\PBZ-Boss操控研究\创作协作')
_handle = None
_task = None


def start(close_editor=False):
    global _handle
    assert _handle is None, 'capture already running'
    assert Path(ue.Paths.project_dir()).resolve() == (BASE / '后台草稿/PBZCreative').resolve()
    editor = ue.get_editor_subsystem(ue.UnrealEditorSubsystem)
    assert not editor.get_game_world(), 'end backend PIE before capture'
    assert editor.get_editor_world().get_path_name().startswith('/Game/PBZCreative/BossLibrary20261119/L_PBZBossGallery_v3.')
    native = json.loads((BASE / '资产接入检查/boss-library-native-result-v2.json').read_bytes())
    output = BASE / '资产接入检查' / ('native-preview-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    output.mkdir()
    rows, index, deadline, capture_at = [], 0, time.monotonic() + 150, 0.0
    camera_before = editor.get_level_viewport_camera_info()
    actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
    selected_before = actors.get_selected_level_actors()
    actors.set_selected_level_actors([])
    if close_editor:
        ue.EditorPythonScripting.set_keep_python_script_alive(True)
    def finish(completed, error=None):
        global _handle
        ue.unregister_slate_post_tick_callback(_handle)
        _handle = None
        editor.set_level_viewport_camera_info(*camera_before)
        actors.set_selected_level_actors(selected_before)
        result = dict(schema=1, capture_completed=completed, rendered_preview_verified=False,
                      manual_visual_review_required=True, rows=rows, error=error,
                      project=str(ue.Paths.project_dir()), game_started=False)
        (output / 'capture-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        ue.log('PBZ_PREVIEW_CAPTURE=' + str(output))
        if close_editor:
            ue.EditorPythonScripting.set_keep_python_script_alive(False)
    def tick(_delta):
        nonlocal index, capture_at
        global _task
        try:
            now = time.monotonic()
            assert now < deadline, 'bounded capture timed out'
            if capture_at == 0:
                role = native['roles'][index]
                actor = next(a for a in actors.get_all_level_actors()
                             if a.get_actor_label() == role['display_name'] + ' | ' + role['role'])
                target, extent = actor.get_actor_bounds(False)
                distance = max(extent.x, extent.y, extent.z, 70) * 3.0
                camera = target + ue.Vector(-distance * .35, distance, distance * .25)
                editor.set_level_viewport_camera_info(camera, ue.MathLibrary.find_look_at_rotation(camera, target))
                rows.append(dict(role=role['role'], file=str(output / (role['role'] + '.png')),
                                 bounds_center=[target.x,target.y,target.z], bounds_extent=[extent.x,extent.y,extent.z]))
                capture_at = now + 1.5
            elif capture_at > 0 and now >= capture_at:
                _task = ue.AutomationLibrary.take_high_res_screenshot(1000, 1000, rows[-1]['file'], force_game_view=True)
                capture_at = -now
            elif capture_at < 0 and now + capture_at > 2.0 and Path(rows[-1]['file']).is_file():
                assert Path(rows[-1]['file']).stat().st_size > 1000
                index += 1
                if index == len(native['roles']):
                    finish(True)
                else:
                    capture_at = 0
        except Exception as error:
            finish(False, str(error))
    _handle = ue.register_slate_post_tick_callback(tick)
    return str(output)
