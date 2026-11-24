"""Build and exercise the expanded Boss catalog in the backend UE authoring project."""
import json
import math
import os
from pathlib import Path
import time

import unreal as ue


ROOT = os.environ.get('PBZ_ROSTER_ROOT', '/Game/PBZCreative/AllBoss3C20261124')
MAP = os.environ.get('PBZ_ROSTER_MAP', ROOT + '/L_PBZAllBoss3C')
PREVIOUS = '/Game/PBZCreative/CharacterLab20261119_v4'
LIBRARY = ue.EditorAssetLibrary
WORK = Path(os.environ['PBZ_ROSTER_WORK'])
PROJECT = Path(os.environ['PBZ_ROSTER_PROJECT']).resolve()


def write(name, value):
    with (WORK / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def load_mesh(path):
    asset = ue.load_asset(path)
    if not isinstance(asset, ue.SkeletalMesh) or not asset.get_editor_property('skeleton'):
        raise ValueError('Missing skeletal mesh or skeleton: ' + path)
    return asset


def import_mesh(source, number, namespace='Meshes'):
    destination = f'{ROOT}/{namespace}/M{number:03d}'
    task = ue.AssetImportTask()
    for key, value in dict(filename=source, destination_path=destination, automated=True, save=True,
                           replace_existing=False, async_=False).items():
        task.set_editor_property(key, value)
    ue.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    options = [asset for asset in task.get_objects() if isinstance(asset, ue.SkeletalMesh)]
    if len(options) != 1:
        raise ValueError(f'Expected one imported skeletal mesh, got {len(options)}')
    mesh = load_mesh(options[0].get_path_name())
    if ue.get_editor_subsystem(ue.SkeletalMeshEditorSubsystem).get_lod_count(mesh) < 1:
        raise ValueError('Imported skeletal mesh has no LOD')
    return mesh


def build():
    manifest = json.loads((WORK / 'ue-input.json').read_bytes())
    assert not LIBRARY.does_directory_exist(ROOT), 'preserve existing authoring assets'
    old = ue.load_asset(PREVIOUS + '/DA_BossRoles')
    old_roles = {str(role.get_editor_property('id')): role for role in old.get_editor_property('roles')}
    meshes, failures = {}, {}
    for number, (package, path) in enumerate(manifest['imports'].items()):
        try:
            meshes[package] = import_mesh(path, number)
        except Exception as error:
            failures[package] = str(error)
            ue.log_warning(f'PBZ_ROSTER_IMPORT_FAILED={package}: {error}')
        if number % 10 == 0:
            ue.log(f'PBZ_ROSTER_IMPORT={number+1}/{len(manifest["imports"])}')
    factory = ue.DataAssetFactory()
    factory.set_editor_property('data_asset_class', ue.PBZLabCatalog)
    tools = ue.AssetToolsHelpers.get_asset_tools()
    catalog = tools.create_asset('DA_BossRoles', ROOT, ue.PBZLabCatalog, factory)
    assert catalog
    roles, included, excluded = [], [], []
    for row in manifest['roles']:
        try:
            if row['source'] == 'character_lab':
                role = old_roles[row['id'].split('_', 1)[1]]
                mesh = load_mesh(row['mesh'])
                assert role.get_editor_property('idle') and role.get_editor_property('walk')
            else:
                if 'body_package' in row:
                    package = row['body_package']
                    if package not in meshes:
                        raise ValueError(failures.get(package, 'Native skeletal mesh was not exported'))
                    mesh = meshes[package]
                else:
                    mesh = load_mesh(row['mesh'])
                role = ue.PBZLabRole()
                for key, value in dict(name=row['label'], mesh=mesh, mesh_preview_only=True).items():
                    role.set_editor_property(key, value)
            role.set_editor_property('id', row['id'])
        except (ValueError, KeyError, AssertionError) as error:
            excluded.append(dict(row, reason=str(error)))
            continue
        roles.append(role)
        included.append(dict(row, mesh=mesh.get_path_name(), mesh_preview_only=row['source'] != 'character_lab'))
    assert roles
    catalog.set_editor_property('roles', roles)
    assert LIBRARY.save_loaded_asset(catalog, only_if_is_dirty=False)

    def blueprint(name, parent, key, value):
        factory = ue.BlueprintFactory()
        factory.set_editor_property('parent_class', parent)
        asset = tools.create_asset(name, ROOT, ue.Blueprint, factory)
        assert asset
        ue.BlueprintEditorLibrary.compile_blueprint(asset)
        klass = LIBRARY.load_blueprint_class(ROOT + '/' + name)
        ue.get_default_object(klass).set_editor_property(key, value)
        ue.BlueprintEditorLibrary.compile_blueprint(asset)
        assert LIBRARY.save_loaded_asset(asset, only_if_is_dirty=False)
        return klass

    character = blueprint('BP_Boss3CCharacter', ue.PBZLabCharacter, 'catalog', catalog)
    mode = blueprint('BP_Boss3CMode', ue.PBZLabGameMode, 'default_pawn_class', character)
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    assert levels.new_level(MAP)
    actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
    floor = actors.spawn_actor_from_class(ue.StaticMeshActor, ue.Vector(0, 0, -30))
    floor.static_mesh_component.set_static_mesh(ue.load_asset('/Engine/BasicShapes/Cube'))
    floor.set_actor_scale3d(ue.Vector(80, 80, .5))
    actors.spawn_actor_from_class(ue.PlayerStart, ue.Vector(0, 0, 260))
    target = actors.spawn_actor_from_class(ue.StaticMeshActor, ue.Vector(1200, 0, 100))
    target.static_mesh_component.set_static_mesh(ue.load_asset('/Engine/BasicShapes/Cylinder'))
    target.set_actor_scale3d(ue.Vector(1, 1, 2))
    target.set_editor_property('tags', [ue.Name('PBZLabTarget')])
    sun = actors.spawn_actor_from_class(ue.DirectionalLight, ue.Vector(0, 0, 1800), ue.Rotator(-40, -40, 0))
    sun.light_component.set_editor_property('mobility', ue.ComponentMobility.MOVABLE)
    sky = actors.spawn_actor_from_class(ue.SkyLight, ue.Vector(0, 0, 1000))
    sky.light_component.set_editor_property('mobility', ue.ComponentMobility.MOVABLE)
    actors.spawn_actor_from_class(ue.SkyAtmosphere, ue.Vector())
    world = ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world()
    world.get_world_settings().set_editor_property('default_game_mode', mode)
    assert levels.save_current_level()
    write('ue-imported.json', dict(map=MAP, roles=included, excluded=excluded, import_failures=failures,
                                  imported_meshes=len(meshes)))
    ue.log(f'PBZ_ROSTER_BUILD_DONE={len(roles)}')


def verify():
    manifest_name = os.environ.get('PBZ_ROSTER_PIE_INPUT', 'ue-imported.json')
    manifest = json.loads((WORK / manifest_name).read_bytes())
    expected = manifest['roles']
    editor = ue.get_editor_subsystem(ue.UnrealEditorSubsystem)
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    assert not levels.is_in_play_in_editor()
    if not editor.get_editor_world().get_path_name().startswith(MAP + '.'):
        assert levels.load_level(MAP), f'Unable to load 3C test level {MAP}'
    assert editor.get_editor_world().get_path_name().startswith(MAP + '.')
    ue.EditorPythonScripting.set_keep_python_script_alive(True)
    deadline = time.monotonic() + 2400
    first_index = int(os.environ.get('PBZ_ROSTER_PIE_START', '0'))
    result_name = os.environ.get('PBZ_ROSTER_PIE_RESULT', 'ue-pie-result.json')
    smoke_count = int(os.environ.get('PBZ_ROSTER_SMOKE_COUNT', '0'))
    requested_ids = set(filter(None, os.environ.get('PBZ_ROSTER_PIE_IDS', '').split(',')))
    capture_ids = set(filter(None, os.environ.get('PBZ_ROSTER_CAPTURE_IDS', '').split(',')))
    assert requested_ids | capture_ids <= {row['id'] for row in expected}
    indices = [i for i in range(first_index, smoke_count or len(expected))
               if not requested_ids or expected[i]['id'] in requested_ids]
    assert indices
    pending = iter(indices)
    phase, entered, index = 'select', 0, next(pending)
    results, keys, screenshots = [], set(), []
    measurement = {}
    levels.editor_request_begin_play()

    def press(pc, key, down):
        pc.inject_lab_input(key, 1 if down else 0, False, not down)
        if down:
            keys.add(key)
        else:
            keys.discard(key)

    def tap(pc, key):
        press(pc, key, True)
        press(pc, key, False)

    def phase_to(next_phase, now):
        nonlocal phase, entered
        phase, entered = next_phase, now

    def angle(a, b):
        return abs((a - b + 180) % 360 - 180)

    def vector(value):
        return [value.x, value.y, value.z]

    def finish(pc, error=None, complete=False):
        for key in list(keys):
            press(pc, key, False)
        ue.unregister_slate_post_tick_callback(handle)
        levels.editor_request_end_play()
        write(result_name, dict(completed=complete, global_error=error, map=MAP, rows=results,
                               screenshots=screenshots, viewport_input='engine_input_key', original_game_started=False))
        ue.log(f'PBZ_ROSTER_PIE_DONE={len(results)}/{len(expected)}')
        holder = {}

        def shutdown(_dt):
            if not levels.is_in_play_in_editor() and not editor.get_game_world():
                ue.unregister_slate_post_tick_callback(holder['handle'])
                ue.EditorPythonScripting.set_keep_python_script_alive(False)
        holder['handle'] = ue.register_slate_post_tick_callback(shutdown)

    def tick(_dt):
        nonlocal index, measurement
        world = editor.get_game_world()
        if not world:
            if time.monotonic() >= deadline:
                finish(None, 'PIE world did not initialize')
            return
        pc = ue.GameplayStatics.get_player_controller(world, 0)
        pawn = pc.get_controlled_pawn() if pc else None
        if not pawn:
            if time.monotonic() >= deadline:
                finish(pc, 'PIE player pawn did not initialize')
            return
        if time.monotonic() >= deadline:
            finish(pc, 'PIE exceeded bounded test time')
            return
        now = ue.GameplayStatics.get_time_seconds(world)
        elapsed = now - entered
        role = expected[index]
        try:
            if phase == 'select':
                measurement = dict(id=role['id'], actor=role.get('actor'), folder=role['folder'])
                assert pawn.select_role(index), 'role selection refused'
                phase_to('load', now)
            elif phase == 'load':
                if pawn.get_editor_property('loading') and elapsed < 10:
                    return
                assert not pawn.get_editor_property('loading') and pawn.get_editor_property('role_index') == index, 'wrong loaded role'
                mesh = pawn.get_component_by_class(ue.SkeletalMeshComponent)
                assert mesh.get_skeletal_mesh_asset().get_path_name() == role['mesh'], 'wrong character mesh'
                assert mesh.is_visible(), 'character mesh is hidden'
                assert mesh.get_num_bones() > 0, 'skeletal mesh has no bones'
                capsule = pawn.get_component_by_class(ue.CapsuleComponent)
                height = capsule.get_unscaled_capsule_half_height()
                assert math.isfinite(height) and height > 0
                measurement.update(character_pass=True, skeletal_bones=mesh.get_num_bones(), capsule_half_height_cm=height,
                                   animation_status='reference_pose' if role['mesh_preview_only'] else 'original_lab_clips_loaded')
                if 'visual_revision' in role:
                    materials = [material.get_path_name() if material else None for material in mesh.get_materials()]
                    assert materials and all(material and not material.startswith('/Engine/') for material in materials)
                    measurement.update(mesh=role['mesh'], materials=materials)
                if not role['mesh_preview_only']:
                    assert pawn.get_editor_property('idle_clip') and pawn.get_editor_property('walk_clip')
                    assert isinstance(mesh.get_anim_instance(), ue.PBZLabAnimInstance)
                pawn.set_actor_location(ue.Vector(0, 0, height + 2), False, False)
                pawn.set_actor_rotation(ue.Rotator(0, 0, 0), False)
                pc.set_control_rotation(ue.Rotator(pitch=-10, yaw=0, roll=0))
                phase_to('settle', now)
            elif phase == 'settle' and elapsed > .12:
                view = pawn.get_editor_property('camera')
                measurement['origin'] = vector(pawn.get_actor_location())
                measurement['camera_before'] = vector(view.get_world_location())
                pc.inject_lab_input('MouseX', 80, True, False)
                pc.inject_lab_input('MouseY', -45, True, False)
                press(pc, 'W', True)
                phase_to('move', now)
            elif phase == 'move' and elapsed > .55:
                press(pc, 'W', False)
                position = pawn.get_actor_location()
                x, y, _ = measurement['origin']
                distance = math.hypot(position.x - x, position.y - y)
                view = pawn.get_editor_property('camera')
                rotation = view.get_world_rotation()
                cx, cy, cz = measurement['camera_before']
                after = view.get_world_location()
                camera_distance = math.dist((cx, cy, cz), (after.x, after.y, after.z))
                turn = angle(pawn.get_actor_rotation().yaw, 0)
                measurement.update(movement_cm=distance, turn_degrees=turn, camera_yaw_degrees=angle(rotation.yaw, 0),
                                   camera_pitch_degrees=angle(rotation.pitch, -10), camera_translation_cm=camera_distance)
                assert distance > 60 and turn > 2, 'movement or character orientation did not respond'
                measurement['control_pass'] = True
                assert measurement['camera_yaw_degrees'] > 2 and measurement['camera_pitch_degrees'] > 2 and camera_distance > 20
                assert abs(rotation.roll) < .1
                pc.set_control_rotation(ue.Rotator())
                tap(pc, 'MiddleMouseButton')
                phase_to('lock', now)
            elif phase == 'lock' and elapsed > .15:
                assert pawn.has_target(), 'camera target lock did not engage'
                pc.inject_lab_input('MouseX', 80, True, False)
                phase_to('unlock', now)
            elif phase == 'unlock' and elapsed > .15:
                assert not pawn.has_target(), 'camera did not unlock after mouse movement'
                measurement.update(camera_pass=True, target_lock=True, manual_unlock=True)
                capture = (role['id'] in capture_ids if capture_ids else
                           not smoke_count and not requested_ids and index in {first_index, 6, 70, len(expected) - 1})
                if capture:
                    pc.set_control_rotation(ue.Rotator(pitch=-12, yaw=0, roll=0))
                    screenshot = WORK / f'ue-pie-role-{index:03d}.png'
                    ue.SystemLibrary.execute_console_command(pc,
                        f'HighResShot 960x600 filename="{screenshot.as_posix()}"', pc)
                    screenshots.append(str(screenshot))
                    phase_to('capture', now)
                else:
                    phase_to('record', now)
            elif phase in ('record', 'capture') and (phase != 'capture' or elapsed > .8):
                results.append(measurement)
                index = next(pending, None)
                if index is None:
                    finish(pc, complete=True)
                else:
                    if index % 25 == 0:
                        ue.log(f'PBZ_ROSTER_PIE={index}/{len(expected)}')
                    phase_to('select', now)
        except Exception as error:
            for key in list(keys):
                press(pc, key, False)
            results.append(dict(measurement, error=str(error), phase=phase))
            ue.log_warning(f'PBZ_ROSTER_PIE_FAILED={role["id"]}:{phase}:{error}')
            index = next(pending, None)
            if index is None:
                finish(pc, complete=True)
            else:
                phase_to('select', now)

    holder = {}
    handle = ue.register_slate_post_tick_callback(tick)


def revise_visuals():
    plan = json.loads((WORK / 'visual-plan.json').read_bytes())
    original = json.loads(Path(plan['baseline']).read_bytes())
    changes = plan['changes']
    catalog = ue.load_asset(ROOT + '/DA_BossRoles')
    roles = list(catalog.get_editor_property('roles'))
    assert [str(role.get_editor_property('id')) for role in roles] == [row['id'] for row in original['roles']]
    assert set(changes) <= {row['id'] for row in original['roles']}
    namespace = 'VisualRevision20261124'
    assert not LIBRARY.does_directory_exist(f'{ROOT}/{namespace}')
    sources = {change['glb'] for change in changes.values() if 'glb' in change}
    imported = {source: import_mesh(source, i, namespace) for i, source in enumerate(sorted(sources))}
    revised = []
    for role, previous in zip(roles, original['roles'], strict=True):
        assert role.get_editor_property('mesh').get_path_name() == previous['mesh']
        change = changes.get(previous['id'])
        if change is None:
            revised.append(previous)
            continue
        assert previous['actor'] == change['actor'] and previous['mesh_preview_only']
        mesh = imported[change['glb']] if 'glb' in change else load_mesh(change['mesh'])
        assert ue.get_editor_subsystem(ue.SkeletalMeshEditorSubsystem).get_lod_count(mesh) > 0
        role.set_editor_property('mesh', mesh)
        revised.append(dict(previous, mesh=mesh.get_path_name(), visual_revision=change))
    catalog.set_editor_property('roles', roles)
    meshes = [load_mesh(row['mesh']) for row in revised if 'visual_revision' in row]
    registry = ue.AssetRegistryHelpers.get_asset_registry()
    options = ue.AssetRegistryDependencyOptions()
    options.set_editor_property('include_hard_package_references', True)
    dependencies = {}
    for mesh in meshes:
        queue = [mesh.get_path_name().split('.', 1)[0]]
        while queue:
            package = queue.pop()
            if not package.startswith('/Game/') or package in dependencies:
                continue
            assert LIBRARY.does_asset_exist(package), f'Missing local dependency {package}'
            children = registry.get_dependencies(package, options) or []
            dependencies[package] = sorted(map(str, children))
            queue.extend(dependencies[package])
    assert LIBRARY.save_loaded_asset(catalog, only_if_is_dirty=False)
    write('ue-visual-revised.json', dict(original, roles=revised, dependencies=dependencies,
          imported_meshes=original['imported_meshes'] + len(imported)))


def create_visual_review():
    plan = json.loads((WORK / 'visual-plan.json').read_bytes())
    original = json.loads(Path(plan['baseline']).read_bytes())
    changes = plan['changes']
    review_root = ROOT + 'VisualReview20261124'
    review_map = review_root + '/L_PBZAllBoss3CVisualReview'
    catalog_name = 'DA_BossRolesVisualReview20261124'
    character_name = 'BP_Boss3CCharacterVisualReview20261124'
    mode_name = 'BP_Boss3CModeVisualReview20261124'
    def existing_or_duplicate(path, source):
        return LIBRARY.load_asset(path) if LIBRARY.does_asset_exist(path) else LIBRARY.duplicate_asset(source, path)

    catalog = existing_or_duplicate(review_root + '/' + catalog_name, ROOT + '/DA_BossRoles')
    assert catalog
    roles = list(catalog.get_editor_property('roles'))
    assert len(roles) == len(original['roles'])
    revised = []
    for role, previous in zip(roles, original['roles'], strict=True):
        assert str(role.get_editor_property('id')) == previous['id']
        change = changes.get(previous['id'])
        if change is None:
            revised.append(previous)
            continue
        assert previous['actor'] == change['actor'] and previous['mesh_preview_only']
        mesh = load_mesh(change['mesh'])
        role.set_editor_property('mesh', mesh)
        revised.append(dict(previous, mesh=mesh.get_path_name(), visual_revision=change))
    catalog.set_editor_property('roles', roles)
    assert LIBRARY.save_loaded_asset(catalog, only_if_is_dirty=False)

    character = existing_or_duplicate(review_root + '/' + character_name, ROOT + '/BP_Boss3CCharacter')
    assert character
    ue.BlueprintEditorLibrary.compile_blueprint(character)
    character_class = LIBRARY.load_blueprint_class(review_root + '/' + character_name)
    ue.get_default_object(character_class).set_editor_property('catalog', catalog)
    ue.BlueprintEditorLibrary.compile_blueprint(character)
    assert LIBRARY.save_loaded_asset(character, only_if_is_dirty=False)

    mode = existing_or_duplicate(review_root + '/' + mode_name, ROOT + '/BP_Boss3CMode')
    assert mode
    mode_class = LIBRARY.load_blueprint_class(review_root + '/' + mode_name)
    ue.get_default_object(mode_class).set_editor_property('default_pawn_class', character_class)
    ue.BlueprintEditorLibrary.compile_blueprint(mode)
    assert LIBRARY.save_loaded_asset(mode, only_if_is_dirty=False)
    level = existing_or_duplicate(review_map, MAP)
    assert level
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    assert levels.load_level(review_map)
    world = ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world()
    world.get_world_settings().set_editor_property('default_game_mode', mode_class)
    assert levels.save_current_level()
    write('ue-visual-review-map.json', dict(map=review_map, root=review_root, catalog=catalog.get_path_name(),
          character=character.get_path_name(), mode=mode.get_path_name(), roles=revised,
          changed_roles=sorted(changes)))


def verify_author_visual_review():
    plan = json.loads((WORK / 'visual-plan.json').read_bytes())
    review = json.loads((WORK / 'ue-visual-review-map.json').read_bytes())
    expected = json.loads((WORK / 'ue-visual-review-pie-result.json').read_bytes())
    assert expected['completed'] and review['map'] == MAP
    assert Path(ue.Paths.project_dir()).resolve() == PROJECT
    catalog = ue.load_asset(review['catalog'])
    assert isinstance(catalog, ue.PBZLabCatalog)
    roles = list(catalog.get_editor_property('roles'))
    revised = {str(row.get_editor_property('id')): row for row in roles}
    expected_ids = set(review['changed_roles'])
    assert len(roles) == 386 and expected_ids <= set(revised)
    passed = {}
    for row in expected['rows']:
        role = revised[row['id']]
        mesh = role.get_editor_property('mesh')
        assert mesh and mesh.get_path_name() == row['mesh']
        assert mesh.get_editor_property('skeleton')
        materials = [material.get_editor_property('material_interface').get_path_name()
                     if material.get_editor_property('material_interface') else None
                     for material in mesh.get_editor_property('materials')]
        assert materials == row['materials'] and all(material and not material.startswith('/Engine/') for material in materials)
        assert LIBRARY.does_asset_exist(row['mesh'].split('.', 1)[0])
        passed[row['id']] = dict(mesh=mesh.get_path_name(), bones=row['skeletal_bones'], materials=materials)
    character = LIBRARY.load_blueprint_class(review['character'])
    mode = LIBRARY.load_blueprint_class(review['mode'])
    assert character and mode
    assert ue.get_default_object(character).get_editor_property('catalog') == catalog
    assert ue.get_default_object(mode).get_editor_property('default_pawn_class') == character
    assert LIBRARY.does_asset_exist(review['map'])
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    if not ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world().get_path_name().startswith(review['map'] + '.'):
        assert levels.load_level(review['map'])
    world = ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world()
    map_game_mode = world.get_world_settings().get_editor_property('default_game_mode')
    result = dict(map=review['map'], catalog=review['catalog'], total_roles=len(roles),
                  revised_roles=passed, map_default_game_mode=str(map_game_mode),
                  original_game_started=False, cooked_for_target_game=False)
    write('author-cold-load.json', result)


def recover_visible_bodies():
    original = json.loads((WORK / 'ue-imported.json').read_bytes())
    extra = json.loads((WORK / 'visible-components/ue-input.json').read_bytes())
    recovered = {row['id'] for row in extra['roles']}
    assert recovered <= {row['id'] for row in original['excluded']}
    catalog = ue.load_asset(ROOT + '/DA_BossRoles')
    roles = list(catalog.get_editor_property('roles'))
    assert len(roles) == len(original['roles'])
    models = {package: import_mesh(path, number, 'VisibleBodies')
              for number, (package, path) in enumerate(extra['imports'].items())}
    additions = []
    for row in extra['roles']:
        mesh = models[row['body_package']]
        role = ue.PBZLabRole()
        for key, value in dict(id=row['id'], name=row['label'], mesh=mesh, mesh_preview_only=True).items():
            role.set_editor_property(key, value)
        roles.append(role)
        additions.append(dict(row, mesh=mesh.get_path_name(), mesh_preview_only=True))
    catalog.set_editor_property('roles', roles)
    assert LIBRARY.save_loaded_asset(catalog, only_if_is_dirty=False)
    write('ue-imported-final.json', dict(original, roles=original['roles'] + additions,
        excluded=[row for row in original['excluded'] if row['id'] not in recovered],
        imported_meshes=original['imported_meshes'] + len(models)))
    ue.log(f'PBZ_ROSTER_RECOVERY_DONE={len(additions)}')


if __name__ == '__main__':
    assert Path(ue.Paths.project_dir()).resolve() == PROJECT
    {'build': build, 'verify': verify, 'recover': recover_visible_bodies,
     'revise_visuals': revise_visuals, 'create_visual_review': create_visual_review,
     'verify_author_visual_review': verify_author_visual_review}[
         os.environ['PBZ_ROSTER_MODE']]()
