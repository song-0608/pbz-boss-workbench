"""Gate the independent UE character lab on PIE proof, then publish additively."""
import argparse
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess

import creative_workspace as cw
from creative_starter_workspace import editor_processes, ENGINE

ROOT = '/Game/PBZCreative/CharacterLab20261119_v4'
MAP = ROOT + '/L_PBZCharacterLab'
NATIVE = '资产接入检查/character-lab-native-result-v4.json'
PUBLISHED = '资产接入检查/character-lab-published.json'
SOURCE = Path(__file__).with_name('creative_character_lab')
PLUGIN = 'Plugins/PBZCharacterLab'
ROLE_IDS = ('AHua', 'WanJun', 'YouLong', 'YanQianSui', 'XianZhe', 'MadDocter')
PLUGIN_SUFFIXES = {'.dll', '.modules', '.uplugin', '.cpp', '.h', '.cs'}


def safe_relative(name):
    p = PurePosixPath(name)
    assert str(p) == name and not p.is_absolute() and '\\' not in name and ':' not in name
    assert not any(x in ('.', '..') for x in p.parts)
    return name


def plugin_files(root):
    root = cw.plain(root)
    return {p.relative_to(root).as_posix():cw.file_digest(p) for p in root.rglob('*')
            if p.is_file() and p.suffix.lower() in PLUGIN_SUFFIXES}


def acceptance(result, storage=cw.PROJECT_STORAGE, require_review=True):
    base = cw.paths(storage)['base']
    backend = cw.paths(storage, 'backend')['workspace']
    result = cw.plain(result)
    assert result.is_relative_to(base / '资产接入检查') and result.name == 'result.json'
    data = cw.read(result)
    native_path = base / NATIVE
    native = cw.read(native_path)
    assert native['completed'] and native['role_count'] == 6 and native['map'] == MAP
    assert data.get('schema') == 2 and data.get('completed') is True, 'PIE acceptance has not passed'
    assert data['map'] == MAP and Path(data['project']).resolve() == backend.resolve()
    assert data['native_receipt_sha256'] == cw.file_digest(native_path), 'native generation receipt changed'
    assert data['desktop_input_sent'] is False and data['original_game_started'] is False
    assert data['original_game_damage_verified'] is False
    assert [r['id'] for r in data['rows']] == list(ROLE_IDS)
    expected = {r['role']:r['actions'] for r in native['actions_per_role']}
    for index, row in enumerate(data['rows']):
        assert row['role'] == index and row['loaded']
        assert len(row['actions']) == expected[row['id']]
        assert [a['slot'] for a in row['actions']] == list(range(expected[row['id']]))
        assert all(a['runtime_pose_difference'] > .001 for a in row['actions'])
        assert row['movement_cm'] > 120 and row['camera_yaw_change'] > 1 and row['camera_pitch_change'] > 1
        assert row['same_action_successful_plays'] >= 3
        assert all(row.get(key) is True for key in ('action_while_moving', 'buffer_consumed_once',
                   'locomotion_recovered', 'selector_opened', 'target_lock', 'manual_unlock',
                   'quiet_mouse_nudges_preserved_lock'))
    assert data['source_hashes'] == {name:cw.file_digest(Path(__file__).with_name(name))
                                   for name in ('creative_lab_assets.py', 'creative_lab_verify.py')}
    installed = plugin_files(backend / PLUGIN)
    assert {'PBZCharacterLab.uplugin', 'Binaries/Win64/UnrealEditor-PBZCharacterLab.dll',
            'Binaries/Win64/UnrealEditor.modules', 'Source/PBZCharacterLab/Public/PBZLab.h'} <= set(installed)
    assert data['plugin_files'] == installed, 'tested plugin changed'
    for name, digest in installed.items():
        if name.startswith('Source/'):
            assert cw.file_digest(SOURCE / name) == digest, 'plugin source changed since acceptance'
    incoming = {}
    for name, digest in data['tested_files'].items():
        cw.relative(name)
        assert name.startswith('Content/PBZCreative/')
        source = cw.plain(backend / name)
        assert cw.file_digest(source) == digest, 'tested asset changed: ' + name
        incoming[name] = source
    for package in native['dependencies']:
        stem = 'Content/' + package.removeprefix('/Game/')
        assert sum(stem+s in incoming for s in ('.uasset', '.umap')) == 1, 'dependency missing from PIE proof'
    assert 'Content/' + MAP.removeprefix('/Game/') + '.umap' in incoming
    images = [cw.plain(p) for p in data['screenshots']]
    assert len(images) == 7 and len(set(images)) == 7
    assert {p.name for p in images} == {'role-selector.png', *(f'role-{i}.png' for i in range(6))}
    assert all(p.parent == result.parent and p.is_file() and p.stat().st_size > 1000 for p in images)
    if require_review:
        review = cw.read(result.with_name('visual-review.json'))
        assert review['completed'] is True and review['result_sha256'] == cw.file_digest(result)
        assert review['screenshots'] == {p.name:cw.file_digest(p) for p in images}, 'visual review is stale'
        assert review['reviewed_roles'] == list(ROLE_IDS)
    return data, incoming


def plugin_preflight(author, backend, expected):
    source = backend / PLUGIN
    assert plugin_files(source) == expected
    for name, digest in expected.items():
        safe_relative(name)
        target = cw.plain(author / PLUGIN / name)
        assert not target.exists() or cw.file_digest(target) == digest, 'existing author plugin preserved: ' + name
    project = cw.plain(author / 'PBZCreative.uproject')
    before = project.read_bytes()
    config = json.loads(before)
    plugins = config.setdefault('Plugins', [])
    for name in ('PBZCharacterLab', 'PythonScriptPlugin', 'EditorScriptingUtilities', 'USDImporter'):
        entries = [p for p in plugins if p['Name'] == name]
        assert len(entries) <= 1
        if entries: assert entries[0].get('Enabled') is True, 'explicitly disabled author plugin preserved: ' + name
        else: plugins.append(dict(Name=name, Enabled=True))
    return project, before, config


def publish(result, storage=cw.PROJECT_STORAGE):
    data, incoming = acceptance(result, storage)
    p = cw.paths(storage)
    author = p['workspace']
    backend = cw.paths(storage, 'backend')['workspace']
    project, project_before, project_config = plugin_preflight(author, backend, data['plugin_files'])
    before = cw.scan(author)
    baseline = cw.read(author / '.pbz-base.json')
    for name, source in incoming.items():
        destination = cw.plain(author / name)
        assert not destination.exists() or cw.file_digest(destination) == cw.file_digest(source), 'existing author asset preserved: ' + name
    files = {**before, **incoming}
    assert len(files) <= cw.MAX_FILES and sum(path.stat().st_size for path in files.values()) <= cw.MAX_BYTES, \
        'proposal exceeds existing size bound; reduce redundant dependencies before publishing'
    def unchanged(rows):
        assert cw.read(author / '.pbz-base.json') == baseline
        current = cw.scan(author)
        assert set(current) == set(before), 'author saved new files while submitting; retry'
        assert all(cw.file_digest(path) == rows[name]['sha256'] for name, path in current.items()), 'author saved while submitting; retry'
        assert project.read_bytes() == project_before, 'author project settings changed; retry'
    proposal = cw.freeze('proposal', files, dict(base=baseline['proposal'], lane='ue', origin='creative_authoring',
        character_lab_pie_sha256=cw.file_digest(Path(result)), character_lab_source_integration=cw.read(p['base']/NATIVE)['source_integration']),
        storage, before_publish=unchanged)
    plan = cw.merge_plan(proposal, storage)
    assert not plan['conflicts'], 'use workbench conflict review: ' + repr(plan['conflicts'])
    integration = cw.integrate(proposal, storage, expected_current=plan['current'])
    snapshot, manifest = cw.checked_snapshot('integration', integration, storage)
    added = []
    for name in sorted(incoming):
        target = cw.plain(author / name)
        row = manifest['files'][name]
        if target.exists():
            assert cw.file_digest(target) == row['sha256'], 'concurrent author asset edit preserved: ' + name
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with (snapshot/'files'/name).open('rb') as src, target.open('xb') as dst:
            shutil.copyfileobj(src, dst, 1024*1024)
        assert cw.file_digest(target) == row['sha256']
        added.append(name)
    # Only new or identical plugin files are allowed, even if the editor is
    # running. No reload command, focus change, DLL replacement or restart.
    installed = []
    for name, digest in data['plugin_files'].items():
        target = cw.plain(author / PLUGIN / name)
        if target.exists():
            assert cw.file_digest(target) == digest, 'concurrent plugin edit preserved'
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with (backend/PLUGIN/name).open('rb') as src, target.open('xb') as dst:
            shutil.copyfileobj(src, dst, 1024*1024)
        assert cw.file_digest(target) == digest
        installed.append(name)
    assert project.read_bytes() == project_before, 'author project settings changed; retry'
    if json.loads(project_before) != project_config: cw.atomic(project, cw.canonical(project_config))
    import creative_boss_library as library
    menu = author/'Content/Python/pbz_boss_editor_menu.py'
    menu_preserved = menu.exists() and menu.read_bytes() != library.MENU.read_bytes() and cw.file_digest(menu) not in library.LEGACY_MENU_SHA256
    if not menu_preserved: library.install_menu(author)
    receipt = dict(schema=1, completed=True, map=MAP, proposal=proposal, integration=integration,
        result=str(Path(result)), result_sha256=cw.file_digest(Path(result)), plugin_files=data['plugin_files'],
        files={name:manifest['files'][name] for name in incoming}, added=added, new_plugin_files=installed,
        author_assets_overwritten=0, running_editor_restarted=False, desktop_input_sent=False,
        plugin_loads_on_next_normal_start=True, original_game_damage_verified=False)
    receipt['customized_author_menu_preserved'] = menu_preserved
    cw.atomic(p['base']/PUBLISHED, cw.canonical(receipt))
    return dict(completed=True, integration=integration, newly_added=len(added), plugin_loads_on_next_normal_start=True)


def verify(storage=cw.PROJECT_STORAGE):
    p = cw.paths(storage)
    path = p['base']/PUBLISHED
    if not path.is_file(): return dict(completed=False, reason='尚未完成 PIE 验收和发布')
    receipt = cw.read(path)
    assert receipt['completed'] and receipt['map'] == MAP
    assert cw.file_digest(Path(receipt['result'])) == receipt['result_sha256']
    acceptance(receipt['result'], storage)
    _, manifest = cw.checked_snapshot('integration', receipt['integration'], storage)
    missing, modified = [], []
    for name, row in receipt['files'].items():
        cw.relative(name); assert row == manifest['files'][name]
        target = cw.plain(p['workspace']/name)
        if not target.is_file(): missing.append(name)
        elif cw.file_digest(target) != row['sha256']: modified.append(name)
    assert plugin_files(p['workspace']/PLUGIN) == receipt['plugin_files'], 'author plugin differs from accepted plugin'
    return dict(completed=not missing and not modified, checked_files=len(receipt['files']),
                missing=missing, locally_modified=modified, integration=receipt['integration'],
                map=MAP, original_game_damage_verified=False)


def open_editor(storage=cw.PROJECT_STORAGE):
    p = cw.paths(storage)
    project = p['workspace']/'PBZCreative.uproject'
    running = editor_processes(project)
    if running:
        return '作者编辑器已在运行，保留当前场景和未保存创作。六角色插件将在下次正常启动加载；届时从此入口进入实验场。'
    checked = verify(storage)
    assert checked.get('checked_files') and not checked['missing'], '先完成后台 PIE 验收并接收完整实验场'
    exe = ENGINE/'Engine/Binaries/Win64/UnrealEditor.exe'
    assert exe.is_file()
    return subprocess.Popen([str(exe), str(project), MAP], cwd=project.parent,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).pid


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('publish').add_argument('result')
    sub.add_parser('check').add_argument('result')
    sub.add_parser('verify'); sub.add_parser('open')
    args = parser.parse_args()
    if args.action == 'publish': output = publish(args.result)
    elif args.action == 'check':
        data, files = acceptance(args.result); output = dict(completed=True, roles=len(data['rows']), files=len(files))
    else: output = open_editor() if args.action == 'open' else verify()
    print(json.dumps(output, ensure_ascii=False, indent=2))
