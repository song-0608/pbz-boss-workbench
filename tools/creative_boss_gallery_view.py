"""Frame the native library in the independent backend preview only."""
from pathlib import Path
import unreal as ue

assert Path(ue.Paths.project_dir()).resolve() == Path(r'E:\项目\PBZ-Boss操控研究\创作协作\后台草稿\PBZCreative').resolve()
editor = ue.get_editor_subsystem(ue.UnrealEditorSubsystem)
assert editor.get_editor_world().get_path_name().startswith('/Game/PBZCreative/BossLibrary20261119/L_PBZBossGallery_v3.')
camera, target = ue.Vector(1600, -2300, 1400), ue.Vector(0, 400, 170)
editor.set_level_viewport_camera_info(camera, ue.MathLibrary.find_look_at_rotation(camera, target))
ue.log('PBZ_GALLERY_VIEW_FRAMED')
