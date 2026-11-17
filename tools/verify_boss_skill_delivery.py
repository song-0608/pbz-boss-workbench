"""Read-only v4 delivery and fixed research checkpoint verification; no game launch."""
import json
from pathlib import Path

from boss_skill_player_acceptance import NAME, collect
from boss_workbench_v4_window import check_installed
from four_boss_integration_workflow import modules
from mod_installation import ROOT, MANIFEST, assert_closed, digest, installed_package, read, validate_package
from research_scene_checkpoint import LABEL, storage, save_snapshot
from verify_research_scene_reload import verify as verify_reload


def check():
    assert_closed()
    receipt, manifest, directory = installed_package()
    identifier = manifest['release_id']
    assert identifier.startswith('ahua-boss-workbench-v4-')
    published = ROOT / 'releases' / identifier
    assert manifest == validate_package(published) == check_installed()
    assert digest(directory / MANIFEST) == digest(published / MANIFEST)
    assert manifest['pending'] == manifest['locked_previews'] == []
    assert [(r['abilities'], r['bindings']) for r in manifest['bosses']] == [(28, 29), (8, 8), (8, 8), (8, 8)]
    report_path = ROOT / manifest['acceptance_report']
    assert digest(report_path) == manifest['acceptance_report_sha256']
    report = read(report_path)
    assert report['passed'] and report['release_id'] == identifier
    assert report['module_source_sha256'] == modules(manifest)
    assert all(digest(ROOT / name) == value for name, value in report['sources'].items())
    offline_path = ROOT / report['local_checks']
    assert digest(offline_path) == report['local_checks_sha256'] == manifest['local_checks_sha256']
    offline = read(offline_path)
    assert offline['passed'] and len(offline['checks']) == 13
    assert all(row['passed'] for row in offline['checks'])
    assert all(digest(ROOT / name) == value for name, value in offline['sources'].items())
    ordinary_path = ROOT / report['ordinary_acceptance']
    assert digest(ordinary_path) == report['ordinary_acceptance_sha256']
    ordinary = read(ordinary_path)
    session_report = read(ROOT / 'evidence/official-validation' / ordinary['session'] / NAME)
    replayed = collect(ordinary['session'], Path(session_report['workflow']), ordinary['world_session'])
    assert ordinary == replayed and len(ordinary['ordinary_extra_actions']) == 24
    launcher = (ROOT / '开始Boss工作台.cmd').read_text(encoding='utf-8-sig')
    assert 'tools\\boss_workbench_v4_window.py' in launcher
    assert '72-四Boss技能扩展v4操作说明.md' in launcher
    pointer = storage() / '当前研究场景.json'
    checkpoint = read(pointer)
    checkpoint_path = Path(checkpoint['directory'])
    assert checkpoint_path.parent == storage() and checkpoint['label'] == LABEL
    assert read(checkpoint_path / 'checkpoint.json') == checkpoint
    assert save_snapshot(checkpoint_path) == checkpoint['files']
    reload = verify_reload()
    return dict(passed=True, release_id=identifier, installed_manifest_sha256=digest(directory / MANIFEST),
                installed_and_enabled=receipt['enabled'], bosses=4, abilities=52, bindings=53,
                offline_groups=13, ordinary_extra_actions=24, ordinary_session=ordinary['session'],
                world_session=ordinary['world_session'], publisher_evidence_replayed=True,
                checkpoint_label=LABEL, checkpoint_file_count=len(checkpoint['files']),
                checkpoint_integrity_verified=True, checkpoint_reload_verified=reload['reload_verified'],
                checkpoint_reload_session=reload['session'],
                default_entry_verified=True, game_started=False)


if __name__ == '__main__':
    print(json.dumps(check(), ensure_ascii=False, indent=2))
