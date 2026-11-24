"""Copy the verified expanded 3C lab into the closed UE authoring workspace."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

from boss_disk_declarations import digest, write_new
from creative_character_lab import plugin_files
from creative_starter_workspace import editor_processes
from creative_workspace import paths, plain, PROJECT_STORAGE


CONTENT = Path('Content/PBZCreative/AllBoss3C20261124')
PLUGIN = Path('Plugins/PBZCharacterLab')
MAP = '/Game/PBZCreative/AllBoss3C20261124/L_PBZAllBoss3C'


def assets(directory):
    return {p.relative_to(directory).as_posix(): digest(p) for p in sorted(directory.rglob('*')) if p.is_file()}


def checked_report(work):
    imported = json.loads((work / 'ue-imported-final.json').read_bytes())
    result = json.loads((work / 'ue-pie-final.json').read_bytes())
    if result['completed'] is not True or result['map'] != MAP or imported['map'] != MAP or result['global_error']:
        raise ValueError('Complete PIE evaluation required')
    rows = result['rows']
    if [r['id'] for r in rows] != [r['id'] for r in imported['roles']]:
        raise ValueError('PIE did not test the exact imported roster')
    failed = [r for r in rows if not all(r.get(key) is True for key in ('camera_pass', 'control_pass', 'character_pass'))]
    if failed:
        raise ValueError(f'{len(failed)} imported roles did not pass 3C')
    return imported, result


def publish(work, storage=PROJECT_STORAGE):
    imported, result = checked_report(work)
    author, backend = (paths(storage, lane)['workspace'] for lane in ('ue', 'backend'))
    roots = author, backend
    if any(editor_processes(root / 'PBZCreative.uproject') for root in roots):
        raise ValueError('Close the author and backend editors before publishing')
    source, target = plain(backend / CONTENT), plain(author / CONTENT)
    live_plugin = plain(author / PLUGIN)
    baseline = plugin_files(work / 'backend-plugin-before')
    updated = plugin_files(backend / PLUGIN)
    if plugin_files(live_plugin) != baseline:
        raise ValueError('Existing author plugin differs from the verified baseline')
    if target.exists():
        raise ValueError('Expanded lab target already exists')
    expected = assets(source)
    if not expected or 'L_PBZAllBoss3C.umap' not in expected:
        raise ValueError('Saved expanded lab map is absent')
    for row in imported['roles']:
        ref = row['mesh'].split('.', 1)[0].removeprefix('/Game/')
        relative = Path('Content', ref).with_suffix('.uasset')
        if relative.is_relative_to(CONTENT):
            if relative.relative_to(CONTENT).as_posix() not in expected:
                raise ValueError(f'Missing new character mesh {relative}')
        elif digest(author / relative) != digest(backend / relative):
            raise ValueError(f'Author body differs from tested body {relative}')
    backup = work / 'author-plugin-before'
    if backup.exists() or (work / 'published.json').exists():
        raise ValueError('Preserve previous publication attempt')
    staging = Path(tempfile.mkdtemp(prefix='publish-', dir=work))
    shutil.copytree(source, staging / 'Content')
    shutil.copytree(backend / PLUGIN, staging / 'Plugin')
    if assets(staging / 'Content') != expected or plugin_files(staging / 'Plugin') != updated:
        raise ValueError('Staged authoring files differ from tested files')
    if (any(editor_processes(root / 'PBZCreative.uproject') for root in roots)
            or target.exists() or plugin_files(live_plugin) != baseline):
        raise ValueError('Authoring workspace changed during publication')
    os.rename(live_plugin, backup)
    try:
        os.rename(staging / 'Plugin', live_plugin)
        os.rename(staging / 'Content', target)
    except OSError:
        if live_plugin.exists():
            os.rename(live_plugin, staging / 'Plugin')
        os.rename(backup, live_plugin)
        raise
    if assets(target) != expected or plugin_files(live_plugin) != updated:
        raise ValueError('Published files differ from verified staging')
    report = dict(map=MAP, project=str(author / 'PBZCreative.uproject'), verified_roles=len(result['rows']),
                  groups_covered=len({r['folder'] for r in imported['roles']}),
                  imported_meshes=imported['imported_meshes'], existing_asset_files_overwritten=0,
                  previous_plugin_backup=str(backup), files=expected, plugin_files=updated,
                  pie_result_sha256=digest(work / 'ue-pie-final.json'))
    write_new(work / 'published.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path)
    args = parser.parse_args()
    result = publish(args.work.resolve())
    print(json.dumps({k: v for k, v in result.items() if k not in ('files', 'plugin_files')}, ensure_ascii=False))
