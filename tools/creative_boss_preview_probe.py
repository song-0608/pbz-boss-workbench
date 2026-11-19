"""Read native mesh and animation scales in the independent backend editor."""
import json
from pathlib import Path
import unreal as ue

base = Path(r'E:\项目\PBZ-Boss操控研究\创作协作')
assert Path(ue.Paths.project_dir()).resolve() == (base / '后台草稿/PBZCreative').resolve()
report = json.loads((base / '资产接入检查/boss-library-native-result.json').read_bytes())
rows = []
for role in report['roles']:
    mesh = ue.load_asset(role['mesh'])
    anim = ue.load_asset(role['idle'])
    bounds = mesh.get_bounds()
    options = ue.AnimPoseEvaluationOptions()
    options.set_editor_property('optional_skeletal_mesh', mesh)
    pose = ue.AnimPoseExtensions.get_anim_pose_at_time(anim, 0.0, options)
    bones = {}
    for name in ('root', 'pelvis', 'spine_01', 'head'):
        tr = ue.AnimPoseExtensions.get_bone_pose(pose, name, ue.AnimPoseSpaces.WORLD)
        bones[name] = str(tr)
    actors = ue.get_editor_subsystem(ue.EditorActorSubsystem).get_all_level_actors()
    actor = next((a for a in actors if a.get_actor_label() == role['display_name'] + ' | ' + role['role']), None)
    rows.append(dict(role=role['role'], mesh_bounds=str(bounds), bones=bones,
                     actor_bounds=str(actor.get_actor_bounds(False)) if actor else None))
path = base / '资产接入检查/boss-library-preview-scale-probe.json'
path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
help_path = base / '资产接入检查/boss-library-capture-api.txt'
help_path.write_text(str(ue.AutomationLibrary.take_high_res_screenshot.__doc__), encoding='utf-8')
ue.log('PBZ_PREVIEW_PROBE=' + str(path))
