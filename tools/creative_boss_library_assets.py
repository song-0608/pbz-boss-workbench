"""Build six editable preview Blueprints, native animations and a separate gallery."""
import json
import math
from pathlib import Path
import unreal as ue

ROOT = Path(r'E:\项目\PBZ-Boss操控研究\创作协作')
PROJECT = ROOT / '后台草稿/PBZCreative'
LIBRARY = '/Game/PBZCreative/BossLibrary20261119'
MAP = LIBRARY + '/L_PBZBossGallery_v2'
EAL = ue.EditorAssetLibrary
TOOLS = ue.AssetToolsHelpers.get_asset_tools()
ROLES = {'AHua': ('阿花', 'AHua_'), 'WanJun': ('巨贼克万钧', 'WanJun_'),
         'YouLong': ('游龙', 'YouLong_'), 'YanQianSui': ('烟千岁', 'YanQianSui_'),
         'XianZhe': ('弦儿', 'XianZhe_'), 'MadDocter': ('谢秋冬', 'MadDoctors_')}
RECIPE = 'native-boss-library-v1'


def owned_duplicate(source, destination):
    if EAL.does_asset_exist(destination):
        asset = ue.load_asset(destination)
        assert EAL.get_metadata_tag(asset, 'PBZCreativeRecipe') == RECIPE
        assert EAL.get_metadata_tag(asset, 'PBZSourceAsset') == source
        return asset
    asset = EAL.duplicate_asset(source, destination)
    assert asset
    EAL.set_metadata_tag(asset, 'PBZCreativeRecipe', RECIPE)
    EAL.set_metadata_tag(asset, 'PBZSourceAsset', source)
    return asset


def pose_check(animation, mesh):
    options = ue.AnimPoseEvaluationOptions()
    options.set_editor_property('optional_skeletal_mesh', mesh)
    options.set_editor_property('evaluation_type', ue.AnimDataEvalType.COMPRESSED)
    duration = animation.get_play_length()
    samples = []
    for time in (0.0, duration * .37, duration * .73):
        pose = ue.AnimPoseExtensions.get_anim_pose_at_time(animation, time, options)
        assert ue.AnimPoseExtensions.is_valid(pose), 'native pose evaluation failed'
        names = {str(n) for n in ue.AnimPoseExtensions.get_bone_names(pose)}
        assert 'pelvis' in names and len(names) > 10
        transforms = []
        for name in ('pelvis', 'spine_01', 'head'):
            assert name in names
            transform = ue.AnimPoseExtensions.get_bone_pose(pose, name, ue.AnimPoseSpaces.WORLD)
            location, rotation = transform.translation, transform.rotation
            values = [location.x, location.y, location.z, rotation.x, rotation.y, rotation.z, rotation.w]
            assert all(math.isfinite(v) and abs(v) < 100000 for v in values)
            transforms.extend(values)
        samples.append(transforms)
    difference = max(abs(a-b) for a,b in zip(samples[0], samples[1]))
    assert difference > .00001, 'animation sampled as a static pose'
    return dict(duration_seconds=duration, frames=ue.AnimationLibrary.get_num_frames(animation),
                native_compressed_pose_samples=3, sampled_bones=['pelvis', 'spine_01', 'head'],
                first_to_middle_pose_difference=difference, finite_poses=True)


def main():
    assert Path(ue.Paths.project_dir()).resolve() == PROJECT.resolve()
    assert not EAL.does_asset_exist(MAP), 'existing user gallery preserved'
    report = ROOT / '资产接入检查/boss-library-native-result.json'
    assert not report.exists()
    imported = json.loads((ROOT / '资产接入检查/six-final-native-import-result.json').read_bytes())
    animations = json.loads((ROOT / '资产接入检查/six-boss-animations-native-import-result.json').read_bytes())
    assert imported['completed'] and imported['skeletal_mesh_count'] == 6 and animations['completed']
    roles = []
    supporting_skeletons = set()
    for role, (display, prefix) in ROLES.items():
        mesh_path, = [r['path'] for r in imported['assets'] if r['type'] == 'SkeletalMesh' and '/SK_'+role+'_Editable/' in r['path']]
        mesh = ue.load_asset(mesh_path)
        assert isinstance(mesh, ue.SkeletalMesh)
        skeleton = mesh.get_editor_property('skeleton')
        clips = []
        for row in animations['assets']:
            if row['type'] != 'AnimSequence' or not row['path'].split('.')[-1].startswith('AS_' + prefix):
                continue
            name = row['path'].split('.')[-1]
            animation = owned_duplicate(row['path'], LIBRARY + '/Animations/' + role + '/' + name)
            animation_skeleton = animation.get_editor_property('skeleton')
            # The Skeleton pointer is intentionally read-only in UE Python.
            # Use UE's public compatibility API after exact joint/bind checks.
            skeleton.add_compatible_skeleton_soft(animation_skeleton)
            animation_skeleton.add_compatible_skeleton_soft(skeleton)
            ue.AnimationLibrary.set_skeleton_preview_mesh(animation_skeleton, mesh)
            animation.set_preview_skeletal_mesh(mesh)
            assert EAL.save_loaded_asset(animation_skeleton, only_if_is_dirty=False)
            supporting_skeletons.add(animation_skeleton.get_path_name())
            evaluation = pose_check(animation, mesh)
            assert EAL.save_loaded_asset(animation, only_if_is_dirty=False)
            clips.append(dict(asset=animation.get_path_name(), name=name, evaluation=evaluation,
                              animation_skeleton=animation_skeleton.get_path_name()))
        assert len(clips) >= 2
        ue.AnimationLibrary.set_skeleton_preview_mesh(skeleton, mesh)
        assert EAL.save_loaded_asset(skeleton, only_if_is_dirty=False)
        idle, = [r for r in clips if r['name'].endswith('_Battle_Idle')]
        bp_name = 'BP_Boss_' + role
        bp_path = LIBRARY + '/Characters/' + bp_name
        if EAL.does_asset_exist(bp_path):
            bp = ue.load_asset(bp_path)
            assert EAL.get_metadata_tag(bp, 'PBZCreativeRecipe') == RECIPE
        else:
            factory = ue.BlueprintFactory()
            factory.set_editor_property('parent_class', ue.SkeletalMeshActor)
            bp = TOOLS.create_asset(bp_name, LIBRARY + '/Characters', ue.Blueprint, factory)
            assert bp
            EAL.set_metadata_tag(bp, 'PBZCreativeRecipe', RECIPE)
        ue.BlueprintEditorLibrary.compile_blueprint(bp)
        cls = EAL.load_blueprint_class(bp_path)
        cdo = ue.get_default_object(cls)
        component = cdo.get_editor_property('skeletal_mesh_component')
        component.set_skeletal_mesh(mesh)
        component.override_animation_data(ue.load_asset(idle['asset']), True, True, 0.0, 1.0)
        component.set_update_animation_in_editor(True)
        ue.BlueprintEditorLibrary.compile_blueprint(bp)
        assert bp.get_editor_property('status') != ue.BlueprintStatus.BS_ERROR
        assert EAL.save_loaded_asset(bp, only_if_is_dirty=False)
        roles.append(dict(role=role, display_name=display, mesh=mesh_path, skeleton=skeleton.get_path_name(),
                          blueprint=bp_path, idle=idle['asset'], animations=clips,
                          editor_preview_only=True, original_game_skill_events_reconstructed=False))
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
    assert levels.new_level(MAP)
    def spawn(cls, label, location, rotation=ue.Rotator()):
        actor = actors.spawn_actor_from_class(cls, ue.Vector(*location), rotation)
        assert actor
        actor.set_actor_label(label); actor.set_folder_path('PBZCreative/BossLibrary')
        return actor
    floor = spawn(ue.StaticMeshActor, 'Boss library floor', (0, 500, -30))
    floor.static_mesh_component.set_static_mesh(ue.load_asset('/Engine/BasicShapes/Cube'))
    floor.set_actor_scale3d(ue.Vector(90, 75, .5))
    for index, role in enumerate(roles):
        x, y = (index % 3 - 1) * 2200, (index // 3) * 2000
        actor = spawn(EAL.load_blueprint_class(role['blueprint']), role['display_name'] + ' | ' + role['role'], (x, y, 0))
        component = actor.get_editor_property('skeletal_mesh_component')
        assert component.get_editor_property('skeletal_mesh') is not None
        text = spawn(ue.TextRenderActor, role['role'] + ' label', (x, y - 350, 30), ue.Rotator(0, -90, 0))
        text.text_render.set_text(role['role'] + ' | ' + str(len(role['animations'])) + ' animations')
        text.text_render.set_world_size(60)
    sun = spawn(ue.DirectionalLight, 'Gallery sunlight', (0, 0, 2000), ue.Rotator(-45, -40, 0))
    sun.light_component.set_editor_property('intensity', 6.0)
    sky = spawn(ue.SkyLight, 'Gallery skylight', (0, 0, 1000))
    sky.light_component.set_editor_property('mobility', ue.ComponentMobility.MOVABLE)
    sky.light_component.set_editor_property('intensity', 1.0)
    spawn(ue.SkyAtmosphere, 'Gallery sky atmosphere', (0, 0, 0))
    editor = ue.get_editor_subsystem(ue.UnrealEditorSubsystem)
    camera, target = ue.Vector(3800, -6000, 2300), ue.Vector(0, 650, 180)
    editor.set_level_viewport_camera_info(camera, ue.MathLibrary.find_look_at_rotation(camera, target))
    assert levels.save_current_level()
    EAL.save_directory(LIBRARY, only_if_is_dirty=False, recursive=True)
    registry = ue.AssetRegistryHelpers.get_asset_registry()
    registry.scan_paths_synchronous([LIBRARY, '/Game/PBZCreative/ImportedBosses/EditableAnimations20261119'], True)
    dependency_options = ue.AssetRegistryDependencyOptions(
        include_soft_package_references=True, include_hard_package_references=True,
        include_searchable_names=False, include_soft_management_references=False,
        include_hard_management_references=False)
    packages = {p.split('.')[0] for p in EAL.list_assets(LIBRARY, recursive=True, include_folder=False)}
    pending = list(packages)
    while pending:
        package = pending.pop()
        assert ue.load_asset(package), 'dependency package does not load: ' + package
        for dependency in registry.get_dependencies(package, dependency_options) or []:
            dependency = str(dependency)
            if not dependency.startswith('/Game/') or dependency in packages:
                continue
            assert dependency.startswith('/Game/PBZCreative/ImportedBosses/EditableAnimations20261119/'), dependency
            assert isinstance(ue.load_asset(dependency), ue.Skeleton), 'unexpected diagnostic mesh dependency'
            packages.add(dependency); pending.append(dependency)
    result = dict(schema=1, completed=True, library=LIBRARY, map=MAP, roles=roles,
                  supporting_skeletons=sorted(supporting_skeletons),
                  dependency_packages=sorted(packages),
                  role_count=len(roles), native_animation_count=sum(len(r['animations']) for r in roles),
                  game_launches_for_mapping=1, gameplay_tested=False, rendered_preview_verified=False,
                  original_game_shaders_reconstructed=False)
    with report.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    ue.log('PBZ_BOSS_LIBRARY_COMPLETE=' + str(report))


if __name__ == '__main__':
    main()
