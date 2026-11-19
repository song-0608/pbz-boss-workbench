"""Import native decoded USD animations in the backend lane; retain failures."""
import json
import os
from pathlib import Path
import unreal as ue

project = Path(ue.Paths.project_dir()).resolve()
root = Path(r'E:\项目\PBZ-Boss操控研究\创作协作')
assert project == (root / '后台草稿/PBZCreative').resolve()
job = json.loads(Path(os.environ['PBZ_CREATIVE_ANIMATION_JOB']).read_bytes())
destination = job['destination']
assert destination.startswith('/Game/PBZCreative/ImportedBosses/') and '..' not in destination
library = ue.EditorAssetLibrary
assert not library.does_directory_exist(destination), 'existing animation assets preserved'
assert 1 <= len(job['files']) <= 64
tasks = []
for filename in job['files']:
    source = Path(filename).resolve()
    assert source.is_relative_to(root / '角色源资产') and source.suffix == '.usda' and source.is_file()
    options = ue.UsdStageImportOptions()
    for name, value in dict(import_actors=False, import_geometry=True, import_skeletal_animations=True,
                            import_level_sequences=False, import_materials=False,
                            import_groom_assets=False, import_sparse_volume_textures=False,
                            import_sounds=False).items():
        options.set_editor_property(name, value)
    task = ue.AssetImportTask()
    for name, value in dict(filename=str(source), destination_path=destination,
                            automated=True, replace_existing=False, save=True,
                            options=options, factory=ue.UsdStageAssetImportFactory()).items():
        task.set_editor_property(name, value)
    tasks.append(task)
ue.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
rows = []
for path in library.list_assets(destination, recursive=True, include_folder=False):
    asset = ue.load_asset(path)
    assert asset
    row = dict(path=path, type=asset.get_class().get_name())
    if isinstance(asset, ue.AnimSequence):
        row['duration'] = asset.get_play_length()
        row['skeleton'] = asset.get_editor_property('skeleton').get_path_name()
        assert row['duration'] > 0
    assert library.save_loaded_asset(asset, only_if_is_dirty=False)
    rows.append(row)
animations = [r for r in rows if r['type'] == 'AnimSequence']
result = dict(schema=1, completed=len(animations) >= len(tasks), assets=rows,
              native_animation_count=len(animations), destination=destination,
              gameplay_events_reconstructed=False, pose_preview_verified=False)
report = Path(job['report'])
assert report.is_relative_to(root / '资产接入检查')
with report.open('x', encoding='utf-8') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
assert result['completed'], 'USD import did not create all requested native animation sequences'
ue.log('PBZ_CREATIVE_ANIMATION_IMPORT_COMPLETE=' + str(report))
