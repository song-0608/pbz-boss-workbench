"""Route the v5 player launcher to its exact installed and accepted native payload."""
import hashlib
import json
from pathlib import Path

from boss_adaptation_workflow import ROOT, sha, write_json
from mod_installation import MANIFEST, installed_package, validate_package, unlinked_path
import expanded_boss_integration_workflow as integration

SOURCES = ('tools/published_boss_workflow.py', 'tools/boss_workbench_v5_window.py',
           'tests/test_published_boss_workflow.py')


def installed_mod_root(release):
    release = unlinked_path(release)
    assert release.parent == (ROOT / 'releases').resolve()
    manifest = validate_package(release)
    receipt, installed, directory = installed_package()
    assert receipt['enabled'] and installed == manifest
    assert manifest['status'] == 'release' and manifest['runtime_acceptance_current'] and manifest['complete_mod']
    assert manifest['release_id'].startswith('ahua-boss-workbench-v5-')
    path = ROOT / manifest['acceptance_report']; assert sha(path) == manifest['acceptance_report_sha256']
    proof = json.loads(path.read_bytes()); assert proof['passed'] and proof['release_id'] == manifest['release_id']
    assert proof['bosses'] == manifest['bosses']
    return directory / 'PBZBossControl'


def render(release, manifest):
    files = integration.render(release, ROOT, manifest['expansion_profiles'])
    name = 'run_control_lifecycle_probe.py'; source = files[name].decode('utf-8')
    old = 'from expanded_boss_integration_workflow import candidate_mod_root'
    assert source.count(old) == 1
    source = source.replace(old, 'from published_boss_workflow import installed_mod_root as candidate_mod_root')
    files[name] = source.encode('utf-8')
    return {name: files[name] for name in ('ahua_practice.py', 'run_control_lifecycle_probe.py',
                                         'player_settings.py', 'player_keymap.py')}


def build(release):
    installed_mod_root(release); manifest = validate_package(release); files = render(release, manifest)
    receipt = dict(schema=1, release=str(release), release_manifest_sha256=sha(release / MANIFEST),
        files={name:hashlib.sha256(data).hexdigest() for name,data in files.items()},
        sources={name:sha(ROOT / name) for name in SOURCES})
    key = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()[:16]
    target = ROOT / 'runtime/player-workflows' / ('v5-' + key)
    if not target.exists():
        target.mkdir(parents=True)
        for name,data in files.items(): (target / name).write_bytes(data)
        write_json(target / 'manifest.json', receipt)
    assert json.loads((target / 'manifest.json').read_bytes()) == receipt
    assert {p.name for p in target.iterdir()} == set(files) | {'manifest.json'}
    assert all((target / name).read_bytes() == data for name,data in files.items())
    return target
