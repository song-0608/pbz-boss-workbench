"""Stage our own control plane and exact local-source patches; never install or start a game."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '91099b849e474f0326834135ace52dfbab26e520'
REPOSITORY = 'https://github.com/yhsharaf/PhantomPact'
RECEIPT_SHA = '393273de9b9ee3fe9464d4844232b7080543f71d6787d43cd376a596003b779b'
RELEASE = 'ahua-boss-workbench-v3-f7034432a74d819b'
RELEASE_SHA = '5cb110f21013baea5ae714ad334c54dcd7fb0215e35b697e6559004cd8235d0d'
SCRIPTS = 'mod/PBZCoop/Scripts/'
SOURCES = ('tools/build_phantom_boss_candidate.py', 'tools/export_phantom_boss_catalog.lua',
           'tools/phantom_boss_protocol.lua', 'tools/phantom_boss_adapter.lua',
           'tools/phantom_boss_entry.lua', 'tools/phantom_boss_host.lua')
PENDING = [
    'dedicated online research launcher, lease issuer and local possession restoration',
    'Boss-specific ghost assembly, harmless effects and same-world parking contract',
    'owned Boss removal from already-built enemy synchronization maps',
    'whitelisted visual action playback and measured host damage attribution',
    'two independent clients: real relay, different Bosses, world switch and reconnect',
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def safe_file(root, name):
    rel = PurePosixPath(name)
    if (rel.is_absolute() or str(rel) != name or '\\' in name or ':' in name
            or any(p in ('', '.', '..') for p in rel.parts)):
        raise ValueError('Invalid relative source path: ' + name)
    path = root.joinpath(*rel.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Source escaped fixed directory: ' + name)
    for item in (path, *path.parents):
        if item == root:
            break
        if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
            raise ValueError('Linked source entry: ' + name)
    return path


def verify_upstream(source):
    raw = (source / 'source-receipt.json').read_bytes()
    if sha(raw) != RECEIPT_SHA:
        raise ValueError('Upstream receipt changed; re-review a new pinned revision')
    receipt = json.loads(raw)
    if receipt['commit'] != COMMIT or receipt['repository'] != REPOSITORY or receipt['executed'] is not False:
        raise ValueError('Unexpected upstream source receipt')
    files = {}
    for row in receipt['files']:
        if row['path'] in files:
            raise ValueError('Duplicate upstream source')
        data = safe_file(source, row['path']).read_bytes()
        if sha(data) != row['sha256'] or len(data) != row['bytes']:
            raise ValueError('Upstream source drift: ' + row['path'])
        files[row['path']] = row['sha256']
    if len(files) != 19:
        raise ValueError('The fixed source review requires all 19 files')
    return files


def verify_release(root):
    directory = root / 'releases' / RELEASE
    raw = (directory / 'pbz-release.json').read_bytes()
    if sha(raw) != RELEASE_SHA:
        raise ValueError('Accepted single-player release manifest changed')
    manifest = json.loads(raw)
    for name, expected in manifest['files'].items():
        if sha(safe_file(directory, name).read_bytes()) != expected:
            raise ValueError('Accepted single-player payload changed: ' + name)
    return directory, manifest


def export_catalog(release, lua_lab, root=ROOT):
    result = subprocess.run([str(lua_lab), str(root / SOURCES[1]), str(release)],
                            capture_output=True, text=True, encoding='utf-8', timeout=25, check=True)
    rows = [line.removeprefix('BWB_CATALOG_JSON=') for line in result.stdout.splitlines()
            if line.startswith('BWB_CATALOG_JSON=')]
    if len(rows) != 1:
        raise ValueError('Catalog exporter did not produce exactly one result')
    bosses = json.loads(rows[0])
    if {k: len(v['actions']) for k, v in bosses.items()} != {
            'ahua_guitoudao': 28, '057_wanjun': 4, '073_yanqiansui': 4, '056_youlong': 4}:
        raise ValueError('Catalog differs from the accepted four-Boss whitelist')
    for row in bosses.values():
        for path in (row['class_path'], *row['actions'].values()):
            if not re.fullmatch(r'/PBZCombatAsset/ActorData/Mobs/[A-Za-z0-9_/.]+_C', path):
                raise ValueError('Unexpected class or ability path')
    return bosses


def lua(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, dict):
        return '{' + ','.join('[' + lua(k) + ']=' + lua(v) for k, v in sorted(value.items())) + '}'
    raise TypeError(type(value))


def patches():
    return {
        'main.lua': [
            ('local VERSION = "1.7.3"',
             'if type(rawget(_G, "PBZBossOnlineResearchLaunch")) ~= "table" then\n'
             '    print("[BWB] DISABLED: dedicated online research launcher required")\n'
             '    return\n'
             'end\n\nlocal VERSION = "1.7.3"'),
            ('local DEV_KEYS = os.getenv("PBZCOOP_DEBUG") == "1"',
             'local DEV_KEYS = false -- BWB: F7-F11 belong to the Boss workbench'),
            ('-- Command file: lets a developer drive tests from outside the game.',
             'api.bossWorkbench = dofile(SCRIPT_DIR .. "bwb_entry.lua")(api, SCRIPT_DIR)\n'
             'PBZ.bossWorkbench = api.bossWorkbench\n\n'
             '-- Command file: lets a developer drive tests from outside the game.'),
            ('. F6 PvP', '. HOME online panel | END follow partner | BWB research'),
        ],
        'coop.lua': [
            ('    local function spawnGhost(p)\n',
             '    local function spawnGhost(p)\n'
             '        -- BWB: never clone the receiving player for a different remote Boss.\n'
             '        if api.bossWorkbench and not api.bossWorkbench:allow_legacy_ghost() then return end\n'),
            ('    local function tick()\n',
             '    local function tick()\n'
             '        if api.bossWorkbench and api.bossWorkbench.disabled then return end\n'),
            ('        handlers = handlers,       -- event type -> function(rest); other modules add their own types',
             '        retireWorkbenchGhosts = function() destroyGhosts() end, -- BWB: preserve native clone parking\n'
             '        handlers = handlers,       -- event type -> function(rest); other modules add their own types'),
        ],
        'onlinepanel.lua': [
            ('controller:IsInputKeyDown(kit.key("F5"))', 'controller:IsInputKeyDown(kit.key("Home"))'),
        ],
        'partner.lua': [
            ('controller:IsInputKeyDown(api.panel.kit.key("F3"))',
             'controller:IsInputKeyDown(api.panel.kit.key("End"))'),
        ],
        'pvppanel.lua': [
            ('local key = controller:IsInputKeyDown(kit.key("F6"))',
             'local key = false -- BWB: PvP is outside the two-player co-op candidate'),
        ],
        'panel.lua': [
            ('local f4, f5 = pc:IsInputKeyDown(key("F4")), pc:IsInputKeyDown(key("F5"))',
             'local f4, f5 = false, false -- BWB: online co-op only; local split-screen unaccepted'),
        ],
    }


def patch_source(name, source):
    for old, new in patches()[name]:
        if source.count(old) != 1:
            raise ValueError('Exact patch anchor missing or repeated: ' + name + ': ' + old[:70])
        source = source.replace(old, new, 1)
    return source


def verify_candidate(directory):
    manifest = json.loads((directory / 'candidate.json').read_bytes())
    if (manifest.get('schema') != 1 or manifest.get('upstream_commit') != COMMIT
            or manifest.get('complete_mod') is not False or manifest.get('source_only') is not True
            or manifest.get('runtime_acceptance_current') is not False
            or any(manifest.get(k) is not False for k in ('installed', 'game_started', 'native_relay_executed', 'runtime_tests_inherited'))
            or manifest.get('accepted_manifest_sha256') != RELEASE_SHA
            or manifest.get('accepted_singleplayer_release') != RELEASE
            or manifest.get('upstream_receipt_sha256') != RECEIPT_SHA):
        raise ValueError('Not a source-only unaccepted online candidate')
    identity = dict(files=manifest['files'], own_sources=manifest['own_sources'], upstream=manifest['upstream_files'],
                    accepted_manifest_sha256=RELEASE_SHA, upstream_commit=COMMIT)
    if manifest.get('candidate_id') != 'bwb-phantompact-' + sha(canonical(identity))[:20]:
        raise ValueError('Candidate fingerprint mismatch')
    expected = {'candidate.json', *manifest['files']}
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    if actual != expected:
        raise ValueError('Unexpected/missing candidate payloads')
    for name, digest in manifest['files'].items():
        if sha(safe_file(directory, name).read_bytes()) != digest:
            raise ValueError('Candidate payload drift: ' + name)
    return manifest


def build(source=None, lua_lab=None, root=ROOT):
    source = Path(source) if source else root / 'runtime/integration-research/PhantomPact' / COMMIT
    lua_lab = Path(lua_lab) if lua_lab else root.parent / 'build/lua-harness/Release/lua-lab.exe'
    upstream = verify_upstream(source)
    release, accepted = verify_release(root)
    bosses = export_catalog(release, lua_lab, root)
    catalog_sha = sha(canonical(bosses))
    config = dict(bosses=bosses, catalog_sha256=catalog_sha, exe_sha256=accepted['exe_sha256'],
                  upstream_commit=COMMIT, runtime_acceptance_current=False)
    contents = {'PBZCoop/Scripts/bwb_config.lua': ('return ' + lua(config) + '\n').encode()}
    for local, target in (('protocol', 'protocol'), ('adapter', 'adapter'), ('entry', 'entry'), ('host', 'host')):
        contents[f'PBZCoop/Scripts/bwb_{target}.lua'] = (root / f'tools/phantom_boss_{local}.lua').read_bytes()
    for name in patches():
        contents['upstream-local-patches/' + name] = patch_source(
            name, (source / SCRIPTS / name).read_text(encoding='utf-8')).encode()
    contents['catalog.json'] = canonical(bosses) + b'\n'
    contents['README.txt'] = (
        'SOURCE-ONLY BACKEND CANDIDATE. NOT AN INSTALLER OR MULTIPLAYER RELEASE.\n'
        'Requires a separately acquired Phantom Pact 1.7.3; no upstream DLL or complete mod is bundled.\n'
        'Home: online panel; End: follow partner; F6/F10: reserved for Boss workbench.\n'
        'Boss ghost assembly and live damage are blocked pending their native contracts.\n'
        'No launch entry, enabled.txt, network policy, saved game or single-player release is changed.\n'
    ).encode()
    own_sources = {name: sha((root / name).read_bytes()) for name in SOURCES}
    files = {name: sha(data) for name, data in sorted(contents.items())}
    identity = dict(files=files, own_sources=own_sources, upstream=upstream,
                    accepted_manifest_sha256=RELEASE_SHA, upstream_commit=COMMIT)
    fingerprint = sha(canonical(identity))[:20]
    manifest = dict(schema=1, candidate_id='bwb-phantompact-' + fingerprint,
                    source_only=True, complete_mod=False, runtime_acceptance_current=False,
                    installed=False, game_started=False, native_relay_executed=False,
                    upstream_commit=COMMIT, upstream_version='1.7.3',
                    upstream_receipt_sha256=RECEIPT_SHA, upstream_files=upstream,
                    accepted_singleplayer_release=RELEASE, accepted_manifest_sha256=RELEASE_SHA,
                    catalog_sha256=catalog_sha, bosses=4, abilities=40, files=files,
                    own_sources=own_sources, pending=PENDING,
                    input_policy={'online_panel': 'Home', 'follow_partner': 'End',
                                  'pvp_panel': 'disabled', 'local_panel': 'disabled',
                                  'upstream_developer_keys': 'disabled'},
                    runtime_tests_inherited=False)
    parent = root / 'runtime/online-candidates'
    target = parent / manifest['candidate_id']
    if target.exists():
        if verify_candidate(target) != manifest:
            raise ValueError('Existing candidate identity mismatch')
        return target
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / ('.staging-' + uuid.uuid4().hex)
    staging.mkdir()
    for name, data in contents.items():
        path = staging / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (staging / 'candidate.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    verify_candidate(staging)
    staging.rename(target)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--lua-lab', type=Path)
    args = parser.parse_args()
    candidate = build(args.source, args.lua_lab)
    print(json.dumps({'candidate': str(candidate), 'complete_mod': False,
                      'runtime_acceptance_current': False, 'installed': False}, ensure_ascii=False))
