"""Publish checked native role assets additively through the shared workbench."""
import argparse
import json
import os
from pathlib import Path
import shutil

import creative_workspace as cw

PREFIX = 'Content/PBZCreative/BossLibrary20261119/'
MENU = Path(__file__).with_name('creative_boss_editor_menu.py')
RECEIPT = '资产接入检查/boss-library-published.json'
LEGACY_MENU_SHA256 = {'0be471e93a1f92db0b769eb01eab2d61a2cd6b7c727ab7cf515244bc96b16359',
                      'cb175bd5b1872ebda7206092a5f46ba3016ca28600077e10c1983eb421541094'}


def native(storage=cw.PROJECT_STORAGE):
    base = cw.paths(storage)['base']
    report = base / '资产接入检查/boss-library-native-result-v2.json'
    result = cw.read(report)
    assert result['completed'] and result['role_count'] == 6 and result['native_animation_count'] == 18
    assert all(c['evaluation']['finite_poses'] for r in result['roles'] for c in r['animations'])
    return base, report, result


def status(storage=cw.PROJECT_STORAGE):
    base, _, result = native(storage)
    published = base / RECEIPT
    return dict(roles=[dict(role=r['role'], name=r['display_name'], blueprint=r['blueprint'],
                           animations=len(r['animations'])) for r in result['roles']],
                role_count=6, animations=18, map=result['map'],
                published=published.exists() and cw.read(published).get('completed') is True)


def install_menu(workspace):
    workspace = cw.plain(workspace)
    target = cw.plain(workspace / 'Content/Python/pbz_boss_editor_menu.py')
    if target.exists():
        if target.read_bytes() != MENU.read_bytes():
            assert cw.file_digest(target) in LEGACY_MENU_SHA256, 'existing customized editor menu preserved'
            cw.atomic(target, MENU.read_bytes())
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(MENU.read_bytes())
    init = cw.plain(workspace / 'Content/Python/init_unreal.py')
    before = init.read_text(encoding='utf-8') if init.exists() else ''
    marker = '# PBZ native boss library menu v1\n'
    if marker not in before:
        block = '''
# PBZ native boss library menu v1
import unreal as _pbz_unreal
if '-run=' not in _pbz_unreal.SystemLibrary.get_command_line().lower():
    import pbz_boss_editor_menu
    pbz_boss_editor_menu.register()
'''
        cw.atomic(init, (before + block).encode('utf-8'))


def publish(storage=cw.PROJECT_STORAGE):
    base, report, result = native(storage)
    backend, author = (cw.paths(storage, lane)['workspace'] for lane in ('backend', 'ue'))
    incoming = {}
    for package in result['dependency_packages']:
        assert package.startswith('/Game/PBZCreative/') and '..' not in package and ':' not in package
        # Keep the failed, superseded first gallery only in the backend diagnostics.
        if package == result['library'] + '/L_PBZBossGallery':
            continue
        stem = 'Content/' + package.removeprefix('/Game/')
        choices = [cw.plain(backend / (stem + suffix)) for suffix in ('.uasset', '.umap')]
        existing = [p for p in choices if p.is_file()]
        assert len(existing) == 1, 'one saved native package required: ' + package
        path, = existing
        incoming[cw.relative(path.relative_to(backend).as_posix())] = path
        for suffix in ('.uexp', '.ubulk'):
            sidecar = path.with_suffix(suffix)
            if sidecar.exists():
                incoming[cw.relative(sidecar.relative_to(backend).as_posix())] = sidecar
    # Save author-owned files exactly as they are; additions never overwrite edits.
    before = cw.scan(author)
    baseline = cw.read(author / '.pbz-base.json')
    for name, source in incoming.items():
        destination = cw.plain(author / name)
        assert not destination.exists() or cw.file_digest(destination) == cw.file_digest(source), 'existing author asset preserved: ' + name
    files = dict(before)
    files.update(incoming)
    def unchanged(rows):
        assert cw.read(author / '.pbz-base.json') == baseline
        current = cw.scan(author)
        assert set(current) == set(before), 'author saved new assets during snapshot; retry'
        assert all(cw.file_digest(source) == rows[name]['sha256'] for name, source in current.items()), 'author saved during snapshot; retry'
    proposal = cw.freeze('proposal', files, dict(base=baseline['proposal'], lane='ue', origin='creative_authoring',
                          native_library_source_sha256=cw.file_digest(report)), storage, before_publish=unchanged)
    plan = cw.merge_plan(proposal, storage)
    assert not plan['conflicts'], 'saved author edits require normal workbench conflict review: ' + repr(plan['conflicts'])
    integration = cw.integrate(proposal, storage, expected_current=plan['current'])
    snapshot, manifest = cw.checked_snapshot('integration', integration, storage)
    added, preserved = [], []
    for name in sorted(incoming):
        destination = cw.plain(author / name)
        row = manifest['files'][name]
        if destination.exists():
            assert cw.file_digest(destination) == row['sha256'], 'concurrent author edit preserved: ' + name
            preserved.append(name)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with (snapshot / 'files' / name).open('rb') as source, destination.open('xb') as target:
            shutil.copyfileobj(source, target, 1024 * 1024)
        assert cw.file_digest(destination) == row['sha256']
        added.append(name)
    # Native editor helpers load on the next ordinary UE startup; never close PIE.
    install_menu(author)
    install_menu(backend)
    result = dict(schema=1, completed=True, proposal=proposal, integration=integration,
                  native_receipt_sha256=cw.file_digest(report), added=added, already_identical=preserved,
                  files={name:manifest['files'][name] for name in incoming},
                  author_project=str(author / 'PBZCreative.uproject'), map=result['map'],
                  existing_author_asset_overwritten=False, running_editor_restarted=False,
                  editor_menu_loads_on_next_start=True, runtime_game_compatibility_verified=False)
    cw.atomic(base / RECEIPT, cw.canonical(result))
    return dict(completed=True, assets=len(incoming), integration=integration,
                newly_added=len(added), author_assets_overwritten=0)


def open_selected(role=None, storage=cw.PROJECT_STORAGE):
    data = status(storage)
    assert data['published'], '请先接收已验证角色库'
    author = cw.paths(storage)['workspace']
    if role:
        assert role in {r['role'] for r in data['roles']}
    path = author / PREFIX / ('Characters' if role else '')
    os.startfile(path)
    return '角色蓝图已在工程内。UE 内容浏览器：/Game/PBZCreative/BossLibrary20261119/Characters；下次启动 UE 的“工具”菜单含角色工作台。'


def verify(storage=cw.PROJECT_STORAGE):
    base, report, _ = native(storage)
    receipt = cw.read(base / RECEIPT)
    assert receipt['completed'] and receipt['native_receipt_sha256'] == cw.file_digest(report)
    snapshot, manifest = cw.checked_snapshot('integration', receipt['integration'], storage)
    author = cw.paths(storage)['workspace']
    missing, modified = [], []
    for name, row in receipt['files'].items():
        cw.relative(name)
        assert row == manifest['files'][name]
        path = cw.plain(author / name)
        if not path.is_file():
            missing.append(name)
        elif cw.file_digest(path) != row['sha256']:
            modified.append(name)
    return dict(completed=not missing and not modified, checked_files=len(receipt['files']),
                missing=missing, locally_modified=modified, integration=receipt['integration'],
                editor_menu_current=(author / 'Content/Python/pbz_boss_editor_menu.py').read_bytes() == MENU.read_bytes(),
                original_game_skills_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'publish', 'verify'))
    args = parser.parse_args()
    print(json.dumps(globals()[args.action](), ensure_ascii=False, indent=2))
