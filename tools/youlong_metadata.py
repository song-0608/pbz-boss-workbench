"""One frozen YouLong ability metadata batch; no actors, possession or skill activation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from build_boss_followup_batch import render
from collect_boss_followup import analyze

IDENTIFIER = '056_youlong'
IDENTITY = 'research/boss-adaptation/identity-receipts/20261116-051216.json'
DOSSIER = 'research/boss-adaptation/dossiers/056_youlong.json'
SOURCES = ('tools/youlong_metadata.py', 'tools/build_boss_followup_batch.py',
           'tools/collect_boss_followup.py', 'tests/test_youlong_metadata.py')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def verify_sources(root, sources):
    for name, digest in sources.items():
        path = (root / name).resolve()
        assert path.is_relative_to(root.resolve()) and sha(path) == digest, 'Source changed: ' + name


def definition(root=ROOT):
    identity_path = root / IDENTITY
    identity = read(identity_path)
    assert identity['target_build_sha256'] == BUILD and identity['metadata_only'] and not identity['playable']
    verify_sources(root, identity['sources'])
    rows = [r for r in identity['candidates'] if r['id'] == IDENTIFIER]
    assert len(rows) == 1 and rows[0]['identity_verified']
    assert rows[0]['class_path'].endswith('.BP_Monster_YouLong_Harpoon_C')
    assert rows[0]['config_path'].endswith('.ActorC_YouLong_Harpoon')
    dossier = read(root / DOSSIER)
    assets = sorted(set(dossier['resources'].get('ability_clue', [])
                        + dossier['resources'].get('ability_dependency_clue', [])))
    assert 1 <= len(assets) <= 64
    requests = []
    for asset in assets:
        assert asset.startswith('/PBZCombatAsset/ActorData/Mobs/056_YouLong/')
        assert re.fullmatch(r'/[A-Za-z0-9_/]+', asset)
        leaf = asset.rsplit('/', 1)[-1]
        assert leaf.startswith('GA_')
        requests.append({'id': IDENTIFIER, 'role': 'ability', 'package': asset,
            'lookup_path': asset + '.' + leaf + '_C', 'playable': False, 'granted_to_actor': False})
    evidence = {name: sha(root / name) for name in (IDENTITY, DOSSIER)}
    return requests, evidence


def build(root=ROOT):
    requests, evidence = definition(root)
    manifest = {'schema_version': 1, 'id': IDENTIFIER, 'target_build_sha256': BUILD,
        'metadata_only': True, 'playable': False, 'auto_deploy': False,
        'ability_requests': requests, 'requests': [], 'evidence': evidence,
        'source_files': {name: sha(root / name) for name in SOURCES},
        'repeat_name_scan': False, 'repeat_verified_identity': False,
        'ability_activation_allowed': False, 'max_seconds': 90}
    fingerprint = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:16]
    target = root / 'research/boss-adaptation/followup-batches' / ('youlong-abilities-' + fingerprint)
    if not target.exists():
        target.mkdir(parents=True)
        write_json(target / 'manifest.json', manifest)
        (target / 'identity-probe.lua').write_bytes(render([], requests, fingerprint).encode('utf-8'))
        write_json(target / 'identity-probe-manifest.json', {'target_build_sha256': BUILD,
            'batch_fingerprint': fingerprint, 'batch_manifest_sha256': sha(target / 'manifest.json'),
            'script_sha256': sha(target / 'identity-probe.lua'), 'requests': [], 'ability_requests': requests})
    verify(target, root)
    return target


def verify(batch, root=ROOT):
    batch = Path(batch).resolve()
    assert batch.parent == (root / 'research/boss-adaptation/followup-batches').resolve()
    manifest = read(batch / 'manifest.json')
    probe = read(batch / 'identity-probe-manifest.json')
    requests, evidence = definition(root)
    assert manifest['ability_requests'] == requests and manifest['requests'] == []
    assert manifest['evidence'] == evidence
    assert manifest['metadata_only'] is True and manifest['playable'] is False
    assert manifest['auto_deploy'] is False and manifest['ability_activation_allowed'] is False
    assert manifest['target_build_sha256'] == probe['target_build_sha256'] == BUILD
    assert manifest['source_files'] == {name: sha(root / name) for name in SOURCES}
    verify_sources(root, manifest['evidence'])
    fingerprint = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:16]
    assert batch.name == 'youlong-abilities-' + fingerprint and probe['batch_fingerprint'] == fingerprint
    assert probe['batch_manifest_sha256'] == sha(batch / 'manifest.json')
    assert probe['script_sha256'] == sha(batch / 'identity-probe.lua')
    assert probe['requests'] == [] and probe['ability_requests'] == requests
    assert (batch / 'identity-probe.lua').read_bytes() == render([], requests, fingerprint).encode('utf-8')
    assert {p.name for p in batch.iterdir()} == {'manifest.json', 'identity-probe.lua', 'identity-probe-manifest.json'}
    return probe


def run(batch):
    import ahua_practice as practice
    import official_validation as v
    import research_game_menu as menu
    probe = verify(batch)
    owner, state = practice.owned_session()
    assert owner.get('phase') == 'game_launched' and not state.get('boss_lifecycle_experiment')
    assert state.get('readonly_ai_experiment') and not state.get('restored')
    assert not state.get('network_active') and time.time() < state['deadline_unix'] - 120
    v.c.isolation.select_box('PBZSteamLab')
    v.c.isolation.check_policy(v.c.isolation.api(), allow_offline_validation=True)
    v.verify_build(state['ue4ss_loader_manifest'])
    assert v.c.baseline.formal_files() == state['formal_before']
    rows = [r for r in state['ue4ss_loader_manifest'] if r['physical_path'].replace('\\', '/').endswith('/PBZObserveAI/Scripts/main.lua')]
    assert len(rows) == 1
    row = rows[0]
    target = Path(row['physical_path'])
    work = Path(state['work'])
    assert not (work / 'youlong-metadata-action.json').exists(), 'One batch per launch; preserve previous evidence'
    raw = (batch / 'identity-probe.lua').read_bytes()
    (work / 'before-youlong-metadata.lua').write_bytes(target.read_bytes())
    (work / 'youlong-metadata.lua').write_bytes(raw)
    log = practice.log_path(state)
    offset = len(log.read_text(encoding='utf-8', errors='replace'))
    row['sha256'] = probe['script_sha256']
    v.save(v.state_path(), state)
    target.write_bytes(raw)
    v.verify_build(state['ue4ss_loader_manifest'])
    menu.click(0, 0, 2560, 1600, 'observe_reload')
    tail = practice.wait_tokens(log, ['PBZ_BOSS_META:END=' + probe['batch_fingerprint']], timeout=100, offset=offset)
    lines = [line for line in tail.splitlines() if 'PBZ_BOSS_META:' in line]
    outcomes = analyze(lines, probe)
    v.save(work / 'youlong-metadata-action.json', {'state_file': str(v.state_path()),
        'batch': str(batch.resolve()), 'probe_manifest_sha256': sha(batch / 'identity-probe-manifest.json'),
        'log_offset': offset, 'lines': lines, 'metadata_only': True, 'outcomes': outcomes})
    return {'requests': len(outcomes), 'verified': sum(r['metadata_verified'] for r in outcomes), 'playable': False}


def collect(session, batch):
    probe = verify(batch)
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    state_path = ROOT / 'runtime' / ('official-validation-' + session) / 'state.json'
    state = read(state_path)
    work = ROOT / 'evidence/official-validation' / session
    assert state['restored'] and Path(state['work']).resolve() == work.resolve()
    post_path = work / 'postcheck.json'
    post = read(post_path)
    assert post['validation_state'] == str(state_path)
    assert post['research_box_empty'] and post['research_loader_removed'] and post['host_registry_unchanged']
    assert not post['formal_files_changed'] and not post['host_config_files_changed']
    action_path = work / 'youlong-metadata-action.json'
    action = read(action_path)
    assert action['state_file'] == str(state_path) and action['metadata_only'] is True
    assert action['batch'] == str(batch.resolve())
    assert action['probe_manifest_sha256'] == sha(batch / 'identity-probe-manifest.json')
    raw_path = work / 'UE4SS.log'
    tail = raw_path.read_text(encoding='utf-8', errors='replace')[action['log_offset']:]
    assert action['lines'] == [line for line in tail.splitlines() if 'PBZ_BOSS_META:' in line]
    outcomes = analyze(action['lines'], probe)
    assert outcomes == action['outcomes']
    result = {'schema_version': 1, 'id': IDENTIFIER, 'session': session, 'target_build_sha256': BUILD,
        'metadata_only': True, 'playable': False, 'live_grants_verified': False, 'activation_verified': False,
        'ability_metadata': outcomes, 'sources': {p.relative_to(ROOT).as_posix(): sha(p) for p in
            (state_path, post_path, action_path, raw_path, batch / 'manifest.json',
             batch / 'identity-probe.lua', batch / 'identity-probe-manifest.json')}}
    output = ROOT / 'research/boss-adaptation/ability-metadata-receipts' / ('youlong-' + session + '.json')
    assert not output.exists(), 'Preserve collected receipt'
    write_json(output, result)
    return {'receipt': str(output), 'verified': sum(r['metadata_verified'] for r in outcomes), 'playable': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'verify', 'run', 'collect'))
    parser.add_argument('--batch', type=Path)
    parser.add_argument('--session')
    args = parser.parse_args()
    if args.action == 'build':
        result = {'batch': str(build()), 'game_started': False, 'playable': False}
    else:
        assert args.batch
        result = verify(args.batch) if args.action == 'verify' else run(args.batch) if args.action == 'run' else collect(args.session, args.batch)
    print(json.dumps(result, ensure_ascii=False))
