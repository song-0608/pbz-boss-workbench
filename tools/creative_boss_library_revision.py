"""Add the four missing XianZhe skin parts without replacing author assets."""
import json
from pathlib import Path
import sys
import unreal as ue

BASE = Path(r'E:\项目\PBZ-Boss操控研究\创作协作')
LIBRARY = '/Game/PBZCreative/BossLibrary20261119'
MAP = LIBRARY + '/L_PBZBossGallery_v3'
EAL = ue.EditorAssetLibrary


def main():
    assert Path(ue.Paths.project_dir()).resolve() == (BASE / '后台草稿/PBZCreative').resolve()
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    if '-run=' not in ue.SystemLibrary.get_command_line().lower():
        assert not levels.is_in_play_in_editor()
        assert not ue.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'preserve unsaved backend map'
    report = BASE / '资产接入检查/boss-library-native-result-v2.json'
    assert not report.exists() and not EAL.does_asset_exist(MAP)
    result = json.loads((BASE / '资产接入检查/boss-library-native-result.json').read_bytes())
    imports = json.loads((BASE / '资产接入检查/xianzhe-complete-native-import-result.json').read_bytes())
    assert imports['completed'] and imports['skeletal_mesh_count'] == 1
    mesh_path, = [r['path'] for r in imports['assets'] if r['type'] == 'SkeletalMesh']
    mesh = ue.load_asset(mesh_path)
    skeleton = mesh.get_editor_property('skeleton')
    role, = [r for r in result['roles'] if r['role'] == 'XianZhe']
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import creative_boss_library_assets as build
    for clip in role['animations']:
        animation = ue.load_asset(clip['asset'])
        other = animation.get_editor_property('skeleton')
        skeleton.add_compatible_skeleton_soft(other)
        other.add_compatible_skeleton_soft(skeleton)
        # Existing published animation packages are deliberately not resaved.
        clip['evaluation'] = build.pose_check(animation, mesh)
    ue.AnimationLibrary.set_skeleton_preview_mesh(skeleton, mesh)
    assert EAL.save_loaded_asset(skeleton, only_if_is_dirty=False)
    bp_path = LIBRARY + '/Characters/BP_Boss_XianZhe_Clothed'
    if EAL.does_asset_exist(bp_path):
        bp = ue.load_asset(bp_path)
        assert EAL.get_metadata_tag(bp, 'PBZCreativeRecipe') == build.RECIPE
    else:
        bp = EAL.duplicate_asset(role['blueprint'], bp_path)
        assert bp
        EAL.set_metadata_tag(bp, 'PBZCreativeRecipe', build.RECIPE)
    assert bp
    cls = EAL.load_blueprint_class(bp_path)
    component = ue.get_default_object(cls).get_editor_property('skeletal_mesh_component')
    component.set_skeletal_mesh(mesh)
    component.override_animation_data(ue.load_asset(role['idle']), True, True, 0.0, 1.0)
    component.set_update_animation_in_editor(True)
    ue.BlueprintEditorLibrary.compile_blueprint(bp)
    assert bp.get_editor_property('status') != ue.BlueprintStatus.BS_ERROR
    assert EAL.save_loaded_asset(bp, only_if_is_dirty=False)
    role.update(mesh=mesh_path, skeleton=skeleton.get_path_name(), blueprint=bp_path,
                skin_parts=6, vertices=167012, separate_chaos_cloth_solver_reconstructed=False)
    # Add a compact gallery rather than editing the already-published map.
    # Do not duplicate a loaded UWorld: a Python reference during LoadLevel
    # keeps it alive and UE correctly aborts on the resulting world leak.
    assert levels.new_level(MAP)
    actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
    def spawn(cls, label, location, rotation=ue.Rotator()):
        actor = actors.spawn_actor_from_class(cls, location, rotation)
        assert actor
        actor.set_actor_label(label)
        actor.set_folder_path('PBZCreative/BossLibrary')
        return actor
    for index, item in enumerate(result['roles']):
        position = ue.Vector((index % 3 - 1) * 780, (index // 3) * 900, 0)
        spawn(EAL.load_blueprint_class(item['blueprint']), item['display_name'] + ' | ' + item['role'], position)
        label = spawn(ue.TextRenderActor, item['role'] + ' label', position + ue.Vector(0, -280, 8), ue.Rotator(0, -90, 0))
        label.text_render.set_text(item['role'] + ' | ' + str(len(item['animations'])) + ' animations')
        label.text_render.set_world_size(35)
    floor = spawn(ue.StaticMeshActor, 'Boss library floor', ue.Vector(0, 400, -30))
    floor.static_mesh_component.set_static_mesh(ue.load_asset('/Engine/BasicShapes/Cube'))
    floor.set_actor_scale3d(ue.Vector(42, 34, .5))
    sun = spawn(ue.DirectionalLight, 'Gallery sunlight', ue.Vector(0, 0, 2000), ue.Rotator(-45, -40, 0))
    sun.light_component.set_editor_property('mobility', ue.ComponentMobility.MOVABLE)
    sun.light_component.set_editor_property('intensity', 6.0)
    sky = spawn(ue.SkyLight, 'Gallery skylight', ue.Vector(0, 0, 1000))
    sky.light_component.set_editor_property('mobility', ue.ComponentMobility.MOVABLE)
    spawn(ue.SkyAtmosphere, 'Gallery sky atmosphere', ue.Vector(0, 0, 0))
    assert levels.save_current_level()
    registry = ue.AssetRegistryHelpers.get_asset_registry()
    registry.scan_paths_synchronous([LIBRARY], True)
    options = ue.AssetRegistryDependencyOptions(include_soft_package_references=True,
        include_hard_package_references=True, include_searchable_names=False,
        include_soft_management_references=False, include_hard_management_references=False)
    packages = set(result['dependency_packages'])
    packages.add(MAP)
    packages.add(bp_path)
    packages.update(r['path'].split('.')[0] for r in imports['assets'])
    pending = list(packages)
    while pending:
        package = pending.pop()
        assert ue.load_asset(package)
        for dependency in registry.get_dependencies(package, options) or []:
            dependency = str(dependency)
            if not dependency.startswith('/Game/') or dependency in packages:
                continue
            assert dependency.startswith('/Game/PBZCreative/')
            assert ue.load_asset(dependency)
            packages.add(dependency)
            pending.append(dependency)
    result.update(schema=2, map=MAP, dependency_packages=sorted(packages), preview_revision=2,
                  previous_native_report='boss-library-native-result.json',
                  corrected_missing_parts=['XianZhe: three clothing meshes and brow/lash card'],
                  rendered_preview_verified=False)
    with report.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    ue.log('PBZ_BOSS_LIBRARY_REVISION_COMPLETE=' + str(report))


if __name__ == '__main__':
    main()
