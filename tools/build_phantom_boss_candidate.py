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
           'tools/phantom_boss_entry.lua', 'tools/phantom_boss_host.lua',
           'tools/phantom_boss_enemy_fence.lua', 'tools/prepare_phantom_boss_pair.py',
           'tools/phantom_boss_online_scope.lua', 'tools/phantom_boss_online_control.lua',
           'tools/phantom_boss_local_dependencies.lua', 'tools/phantom_boss_online_arena.lua',
           'tools/phantom_boss_spawn_native.lua', 'tools/phantom_boss_online_session.lua',
           'tools/phantom_boss_startup.lua', 'tools/phantom_boss_combat_runtime.lua',
           'tools/phantom_boss_visual.lua', 'tools/phantom_boss_visual_native.lua', 'tools/phantom_boss_visual_session.lua',
           'tools/phantom_boss_launch_gate.lua', 'tools/phantom_boss_online_workbench.lua',
           'tools/phantom_boss_workbench_native.lua', 'tools/build_phantom_boss_workbench_art.py',
           'assets/online-workbench/art.json')
LOCAL_MODULES = ('control_bridge', 'ue_calls', 'session', 'runtime', 'input_driver', 'world_boundary',
    'boss_catalog', 'keymap', 'profiles/ahua', 'profiles/wanjun', 'profiles/yanqiansui', 'profiles/youlong',
    'profiles/wanjun_bindings', 'profiles/yanqiansui_bindings', 'profiles/youlong_bindings',
    'object_lifecycle', 'ue_combat', 'owned_initialization', 'player_protection', 'ue_arena_layout',
    'arena_layout', 'yanqiansui_clearance_core', 'combat_identity', 'remote_control', 'ue_remote',
    'ue_camera', 'camera_rig', 'ue_input_barrier', 'input_barrier', 'ue_host', 'ue_input',
    'combo_scheduler', 'subtree_contracts', 'target_selector',
    'boss_workbench', 'workbench_input', 'workbench_catalog')
PENDING = [
    'dedicated online launcher, lease issuer, isolated same-PC deployment and live assembly/recovery acceptance',
    'Boss-specific ghost assembly, harmless effects and same-world parking contract',
    'whitelisted visual action playback and measured host damage attribution',
    'two independent clients: real relay, different Bosses, world switch and reconnect',
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def workbench_art(root):
    directory=root/'assets/online-workbench'
    manifest=json.loads((directory/'art.json').read_bytes())
    expected={f'menu-{c}-{s}.png' for c in range(1,5) for s in range(1,5)}
    assert manifest['schema']==1 and manifest['width']==1000 and manifest['height']==620
    assert manifest['boss_order']==['ahua_guitoudao','057_wanjun','073_yanqiansui','056_youlong']
    assert manifest['source_sha256']==sha((root/'tools/build_phantom_boss_workbench_art.py').read_bytes())
    assert set(manifest['files'])==expected
    result={'art.json':(directory/'art.json').read_bytes()}
    for name in expected:
        data=safe_file(directory,name).read_bytes()
        assert sha(data)==manifest['files'][name] and data[:8]==b'\x89PNG\r\n\x1a\n'
        assert int.from_bytes(data[16:20],'big')==1000 and int.from_bytes(data[20:24],'big')==620
        result[name]=data
    return result


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
            ('api.lang = dofile(SCRIPT_DIR .. "lang.lua")(SCRIPT_DIR)',
             'do\n'
             '    return dofile(SCRIPT_DIR .. "bwb_combat_runtime.lua")(api, SCRIPT_DIR)\n'
             'end\n\n'
             'api.lang = dofile(SCRIPT_DIR .. "lang.lua")(SCRIPT_DIR)'),
            ('local VERSION = "1.7.3"',
             'if type(rawget(_G, "PBZBossOnlineResearchLaunch")) ~= "table" then\n'
             '    local source = debug.getinfo(1, "S").source:gsub("^@", "")\n'
             '    local directory = assert(source:match("^(.*[/\\\\])"))\n'
             '    return dofile(directory .. "bwb_launch_gate.lua").wait(directory, function(launch)\n'
             '        _G.PBZBossOnlineResearchLaunch = launch\n'
             '        return dofile(source)\n'
             '    end)\n'
             'end\n\nlocal VERSION = "1.7.3"'),
            ('local DEV_KEYS = os.getenv("PBZCOOP_DEBUG") == "1"',
             'local DEV_KEYS = false -- BWB: F7-F11 belong to the Boss workbench'),
            ('-- Command file: lets a developer drive tests from outside the game.',
             'api.bossWorkbench = dofile(SCRIPT_DIR .. "bwb_startup.lua")(api, SCRIPT_DIR)\n'
             'PBZ.bossWorkbench = api.bossWorkbench\n\n'
             '-- Command file: lets a developer drive tests from outside the game.'),
            ('. F6 PvP', '. HOME online panel | END follow partner | BWB research'),
        ],
        'coop.lua': [
            ('    local QUICK = { U = true, M = true, A = true, H = true, Z = true, SHOT = true, NQ = true, HEAL = true, HX = true }',
             '    local QUICK = { BWV1 = true, U = true, M = true, A = true, H = true, Z = true, SHOT = true, NQ = true, HEAL = true, HX = true }'),
            ('        local cine = game.inCutscene and game.inCutscene() and 1 or 0\n',
             '        if api.bossWorkbench then return end -- BWB: no inventory/loot/story watchers\n'
             '        local cine = game.inCutscene and game.inCutscene() and 1 or 0\n'),
            ('    local function watchOwnDeath()\n',
             '    local function watchOwnDeath()\n'
             '        if api.bossWorkbench then return end -- BWB owns its Boss restoration; no owed loot\n'),
            ('    local function start(role)\n',
             '    local function start(role)\n'
             '        if api.bossWorkbench and not api.bossWorkbench:transport_allowed() then return false end\n'),
            ('        local pawn = slow.body\n',
             '        local pawn\n'
             '        if api.bossWorkbench then\n'
             '            local address\n'
             '            pawn, address = api.bossWorkbench:network_body()\n'
             '            if not pawn then return end\n'
             '            slow.body, slow.pawn, slow.pc, slow.pawnAt = pawn, address, nil, nil\n'
             '        else\n'
             '        pawn = slow.body\n'),
            ('        slow.seenAt = net.frameNow\n',
             '        end -- BWB observed body or ordinary native Pawn cache\n'
             '        slow.seenAt = net.frameNow\n'),
            ('        local _, pawn = getPlayer1()\n        return pawn\n',
             '        if api.bossWorkbench then return api.bossWorkbench:network_body() end\n'
             '        local _, pawn = getPlayer1()\n        return pawn\n'),
            ('    local function sendEvent(kind, ...)\n',
             '    local function sendEvent(kind, ...)\n'
             '        if api.bossWorkbench and (kind == "M" or (kind == "U" and not api.bossWorkbench:allow_legacy_ghost())) then return end\n'
             '        if api.bossWorkbench and not api.bossWorkbench:allow_enemy_event(kind, ...) then return end\n'),
            ('    handlers.M = function(rest, from)\n',
             '    handlers.M = function(rest, from)\n'
             '        if api.bossWorkbench then return end -- BWB: no legacy remote ability activation/grant\n'),
            ('            if h then\n',
             '            if h and (not api.bossWorkbench or api.bossWorkbench:allow_enemy_event(kind, rest)) then\n'),
            ('    local function spawnGhost(p)\n',
             '    local function spawnGhost(p)\n'
             '        -- BWB: never clone the receiving player for a different remote Boss.\n'
             '        if api.bossWorkbench and not api.bossWorkbench:allow_legacy_ghost() then return end\n'),
            ('    local function tick()\n',
             '    local function tick()\n'
             '        if api.bossWorkbench and api.bossWorkbench.disabled then return end\n'),
            ('            if addr ~= net.ghostAddr and not net.ghostSlots[addr] then',
             '            if (not api.bossWorkbench or api.bossWorkbench:allow_enemy_actor(e, addr))\n'
             '                and addr ~= net.ghostAddr and not net.ghostSlots[addr] then'),
            ('    local function shareEnemy(actor, addr, aggro)\n',
             '    local function shareEnemy(actor, addr, aggro)\n'
             '        if api.bossWorkbench and not api.bossWorkbench:allow_enemy_actor(actor, addr) then return end\n'),
            ('    local function syncEnemy(name, actor, nextSeen, held)\n',
             '    local function syncEnemy(name, actor, nextSeen, held)\n'
             '        if api.bossWorkbench and (not api.bossWorkbench:allow_enemy_name(name)\n'
             '            or not api.bossWorkbench:allow_enemy_actor(actor)) then return end\n'),
            ('    local function reportHit(id, enemy, hpDamage, postureDamage, lethal)\n',
             '    local function reportHit(id, enemy, hpDamage, postureDamage, lethal)\n'
             '        if api.bossWorkbench and (not api.bossWorkbench:allow_enemy_name(id)\n'
             '            or not api.bossWorkbench:allow_enemy_actor(enemy)) then return end\n'),
            ('            if who and not justKilled and (isHost()',
             '            if who and (not api.bossWorkbench or api.bossWorkbench:allow_enemy_name(who.name))\n'
             '                and not justKilled and (isHost()'),
            ('        enemyActor = function(name)\n            return enemyByName[name]\n',
             '        enemyActor = function(name)\n'
             '            if api.bossWorkbench and (not api.bossWorkbench:allow_enemy_name(name)\n'
             '                or not api.bossWorkbench:allow_enemy_actor(enemyByName[name])) then return nil end\n'
             '            return enemyByName[name]\n'),
            ('        handlers = handlers,       -- event type -> function(rest); other modules add their own types',
             '        retireWorkbenchGhosts = function()\n'
             '            for _, p in ipairs(partners()) do\n'
             '                p.heldMove, p.ghostMontage, p.ghostPath, p.ghostMoveAt, p.stanceHeld = nil, nil, nil, nil, nil\n'
             '            end\n'
             '            destroyGhosts() -- BWB: preserve native clone parking\n'
             '        end,\n'
             '        workbenchEnemyState = function()\n'
             '            return {net=net,reach=reach,round=round,handover=handover,\n'
             '                names=enemyByName,seen=seen,puppets=api.puppets}\n'
             '        end,\n'
             '        handlers = handlers,       -- event type -> function(rest); other modules add their own types'),
            *[(f'    handlers.{kind} = function({signature})\n',
               f'    handlers.{kind} = function({signature})\n'
               f'        if api.bossWorkbench and not api.bossWorkbench:allow_enemy_event("{kind}", {argument}) then return end\n')
              for kind, signature, argument in (
                  ('N','rest','rest'), ('RUN','rest','rest'), ('GK','name','name'),
                  ('K','name, _, quiet','name'), ('D','rest, from','rest'),
                  ('LR','rest, from','rest'), ('HAS','name, from','name'),
                  ('NOT','name, from','name'), ('BEATEN','name, from','name'), ('B','name, from','name'))],
        ],
        'puppets.lua': [
            ('    function puppets.watchHost(name, actor, addr)\n',
             '    function puppets.watchHost(name, actor, addr)\n'
             '        if api.bossWorkbench and not api.bossWorkbench:allow_enemy_actor(actor, addr) then return end\n'),
            ('    function puppets.follow(name, actor, target)\n',
             '    function puppets.follow(name, actor, target)\n'
             '        if api.bossWorkbench and not api.bossWorkbench:allow_enemy_actor(actor) then return end\n'),
            ('    function puppets.release(addr)\n',
             '    function puppets.forgetWorkbenchActor(addr, owned, names)\n'
             '        local p = byAddr[addr]\n'
             '        local removed = p and owned(p.actor, addr)\n'
             '        if removed then byAddr[addr] = nil end\n'
             '        if removed or next(names) ~= nil then hostMoves[addr] = nil end\n'
             '        for name in pairs(names) do hostSeen[name] = nil end\n'
             '        if (removed or next(names) ~= nil) and game.freeCopy then game.freeCopy(addr, true) end\n'
             '    end\n\n'
             '    function puppets.release(addr)\n'),
            ('    coop.handlers.A = function(rest, from)\n',
             '    coop.handlers.A = function(rest, from)\n'
             '        if api.bossWorkbench and not api.bossWorkbench:allow_enemy_event("A", rest) then return end\n'),
        ],
        'moves.lua': [
            ('    coop.frameTicks.moveStarts = function()\n',
             '    coop.frameTicks.moveStarts = function()\n'
             '        if api.bossWorkbench then return end -- BWB uses its bounded cosmetic pose sampler\n'),
            ('    coop.extraTicks.moves = function()\n',
             '    coop.extraTicks.moves = function()\n'
             '        if api.bossWorkbench then return end -- BWB: no gear, props or backpack observers\n'),
            ('    coop.handlers.U = function(rest, from)\n',
             '    coop.handlers.U = function(rest, from)\n'
             '        if api.bossWorkbench and not api.bossWorkbench:allow_legacy_ghost() then return end\n'),
            ('    local function playHeld(now)\n',
             '    local function playHeld(now)\n'
             '        if api.bossWorkbench and not api.bossWorkbench:allow_legacy_ghost() then return end\n'),
        ],
        'autostart.lua': [
            ('    local function startRelay(c, s)\n',
             '    local function startRelay(c, s)\n'
             '        if api.bossWorkbench and not api.bossWorkbench:transport_allowed() then return false end\n'),
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
    release_raw = (ROOT / 'releases' / RELEASE / 'pbz-release.json').read_bytes()
    if sha(release_raw) != RELEASE_SHA:
        raise ValueError('Local control dependency provenance changed')
    release_files = json.loads(release_raw)['files']
    for name in LOCAL_MODULES:
        target = f'PBZCoop/Scripts/bwb_local_native/{name}.lua'
        original = f'PBZBossControl/Scripts/{name}.lua'
        if manifest['files'].get(target) != release_files[original]:
            raise ValueError('Local control dependency differs from pinned release: ' + name)
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
    for local in ('protocol', 'adapter', 'entry', 'host', 'enemy_fence', 'online_scope', 'online_control',
                  'local_dependencies', 'online_arena', 'spawn_native', 'online_session', 'startup', 'combat_runtime',
                  'visual', 'visual_native', 'visual_session', 'launch_gate', 'online_workbench', 'workbench_native'):
        contents[f'PBZCoop/Scripts/bwb_{local}.lua'] = (root / f'tools/phantom_boss_{local}.lua').read_bytes()
    for name in LOCAL_MODULES:
        contents[f'PBZCoop/Scripts/bwb_local_native/{name}.lua'] = (release / f'PBZBossControl/Scripts/{name}.lua').read_bytes()
    for name,data in workbench_art(root).items():
        contents['PBZCoop/art/bwb_workbench/'+name]=data
    for name in patches():
        contents['upstream-local-patches/' + name] = patch_source(
            name, (source / SCRIPTS / name).read_text(encoding='utf-8')).encode()
    contents['catalog.json'] = canonical(bosses) + b'\n'
    contents['README.txt'] = (
        'SOURCE-ONLY BACKEND CANDIDATE. NOT AN INSTALLER OR MULTIPLAYER RELEASE.\n'
        'Requires a separately acquired Phantom Pact 1.7.3; no upstream DLL or complete mod is bundled.\n'
        'Insert: Boss chooser; arrows/Enter/Esc: select/confirm/close; F6/F10: control/restore.\n'
        'Native UMG presentation is conditional on current-process UI declarations.\n'
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
