"""Read-only replay of the installed v5 delivery, launcher and fixed scene checkpoint."""
import json
from pathlib import Path

from boss_adaptation_workflow import ROOT, sha
from collect_expanded_boss_player import collect
from four_boss_integration_workflow import modules
from mod_installation import MANIFEST, assert_closed, installed_package, read, validate_package
from published_boss_workflow import installed_mod_root, build as player_workflow
from research_scene_checkpoint import LABEL, storage, save_snapshot
from verify_research_scene_reload import verify as verify_reload


def check():
    assert_closed()
    receipt, manifest, directory = installed_package()
    identifier = manifest['release_id']; release = ROOT / 'releases' / identifier
    assert identifier.startswith('ahua-boss-workbench-v5-') and receipt['enabled']
    assert manifest == validate_package(release)
    assert sha(directory / MANIFEST) == sha(release / MANIFEST)
    assert installed_mod_root(release) == directory / 'PBZBossControl'
    assert manifest['ability_count'] == sum(row['abilities'] for row in manifest['bosses'])
    assert manifest['skill_binding_count'] == sum(row['bindings'] for row in manifest['bosses'])
    assert manifest['pending'] == []
    report_path = ROOT / manifest['acceptance_report']; report = read(report_path)
    assert sha(report_path) == manifest['acceptance_report_sha256'] and report['passed']
    assert report['module_source_sha256'] == modules(manifest)
    assert report['publication_source_sha256'] == sha(ROOT / 'tools/release_expanded_boss_workbench.py')
    offline_path = ROOT / report['offline']; offline = read(offline_path)
    assert sha(offline_path) == report['offline_sha256'] and offline['passed']
    assert all(row['passed'] for row in offline['checks'])
    assert all(sha(ROOT / name) == digest for name, digest in offline['source_files'].items())
    accepted_path, accepted = collect(report['ordinary_session'], Path(offline['workflow']), report['world_sessions'])
    assert accepted_path == ROOT / report['ordinary_acceptance']
    assert sha(accepted_path) == report['ordinary_acceptance_sha256']
    assert len(accepted['roles']) == len(manifest['expansion_profiles'])
    launcher = (ROOT / '开始Boss工作台.cmd').read_text(encoding='utf-8-sig')
    assert 'tools\\boss_workbench_v5_window.py' in launcher
    assert '74-Boss工作台v5操作说明.md' in launcher and '-B -X utf8' in launcher
    checkpoint = read(storage() / '当前研究场景.json'); checkpoint_path = Path(checkpoint['directory'])
    assert checkpoint_path.parent == storage() and checkpoint['label'] == LABEL
    assert read(checkpoint_path / 'checkpoint.json') == checkpoint
    assert save_snapshot(checkpoint_path) == checkpoint['files']
    reload = verify_reload(); flow = player_workflow(release)
    return dict(passed=True, release_id=identifier, installed_and_enabled=True,
        bosses=len(manifest['bosses']), abilities=manifest['ability_count'], bindings=manifest['skill_binding_count'],
        ordinary_session=report['ordinary_session'], world_sessions=report['world_sessions'],
        acceptance_replayed=True, player_workflow=str(flow), default_entry_verified=True,
        checkpoint_label=LABEL, checkpoint_integrity_verified=True,
        checkpoint_reload_verified=reload['reload_verified'], game_started=False)


if __name__ == '__main__': print(json.dumps(check(), ensure_ascii=False, indent=2))
