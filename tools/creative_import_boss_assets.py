"""Native UE commandlet import into the independent backend lane only."""
import json
import os
from pathlib import Path
import unreal as ue


def main():
    project = Path(ue.Paths.project_dir()).resolve()
    expected = Path(r'E:\项目\PBZ-Boss操控研究\创作协作\后台草稿\PBZCreative').resolve()
    assert project == expected, 'only the independent backend lane may be imported'
    job_file = Path(os.environ['PBZ_CREATIVE_IMPORT_JOB']).resolve()
    job = json.loads(job_file.read_bytes())
    destination = job['destination']
    assert (destination.startswith('/Game/PBZCreative/ImportedBosses/')
            or destination in ('/Game/PBZCreative/BossLibrary20261119/Meshes',
                               '/Game/PBZCreative/BossLibrary20261119/Meshes/Revision2'))
    assert '..' not in destination and ':' not in destination and '\\' not in destination
    library = ue.EditorAssetLibrary
    assert not library.does_directory_exist(destination), 'existing author assets preserved'
    files = [Path(p).resolve() for p in job['files']]
    assert 1 <= len(files) <= 64 and len(set(files)) == len(files)
    root = Path(r'E:\项目\PBZ-Boss操控研究\创作协作\角色源资产').resolve()
    assert all(p.is_relative_to(root) and p.is_file() and p.suffix.lower() in ('.glb', '.gltf', '.fbx') for p in files)
    tasks = []
    for source in files:
        task = ue.AssetImportTask()
        task.set_editor_property('filename', str(source))
        task.set_editor_property('destination_path', destination)
        task.set_editor_property('automated', True)
        task.set_editor_property('replace_existing', False)
        task.set_editor_property('save', True)
        task.set_editor_property('async_', False)
        tasks.append(task)
    ue.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
    paths = library.list_assets(destination, recursive=True, include_folder=False)
    rows = []
    for path in paths:
        asset = ue.load_asset(path)
        assert asset is not None, 'imported asset failed native load: ' + path
        row = dict(path=path, type=asset.get_class().get_name())
        if isinstance(asset, ue.SkeletalMesh):
            skeleton = asset.get_editor_property('skeleton')
            row['skeleton'] = skeleton.get_path_name() if skeleton else None
            row['lods'] = ue.get_editor_subsystem(ue.SkeletalMeshEditorSubsystem).get_lod_count(asset)
            row['materials'] = len(asset.get_editor_property('materials'))
            assert skeleton is not None and row['lods'] > 0
        assert library.save_loaded_asset(asset, only_if_is_dirty=False), 'native save failed: ' + path
        rows.append(row)
    meshes = [r for r in rows if r['type'] == 'SkeletalMesh']
    assert len(meshes) >= job.get('minimum_skeletal_meshes', len(files)), 'skeletal mesh import incomplete'
    result = dict(schema=1, completed=True, project=str(project), source_job=str(job_file),
                  destination=destination, assets=rows, skeletal_mesh_count=len(meshes),
                  imported_to_backend_editor=True, copied_to_author_lane=False,
                  runtime_skills_reconstructed=False, original_materials_reconstructed=False)
    report = Path(job['report'])
    assert report.is_relative_to(root.parent / '资产接入检查') and not report.exists()
    with report.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    ue.log('PBZ_CREATIVE_IMPORT_COMPLETE=' + str(report))


main()
