"""Prepare independent host/guest settings for a same-PC research pair; never launch."""
import argparse
import json
from pathlib import Path
import re
import secrets

from build_phantom_boss_candidate import ROOT, COMMIT, SOURCES, build, canonical, safe_file, sha, verify_candidate, verify_release

ROLES = ('host', 'guest')


def ini(role, port, secret):
    # ThisPCOnly is a real pinned native/relay.hpp option: both UDP sockets bind
    # INADDR_LOOPBACK; the guest binds port 0 and connects to the host's port.
    settings = dict(Role='Host' if role == 'host' else 'Guest', Connect='Tailscale',
        HostAddress='127.0.0.1', Port=str(port), ThisPCOnly='On', AllowAnyAddress='Off',
        PartySize='2', Secret=secret, Language='Chinese', OnlinePanel='On',
        PartnerTeleport='Off', FollowHostStory='Off', PvP='Off', Revive='Off',
        FreeBellTravel='Off', ClearMapFog='Off', GhostTwins='0', CoopDifficulty='Off',
        CoopEnemyHealth='100', CoopEnemyPosture='100', CoopBossPosture='100',
        CoopEnemyDamage='100', CoopBossDamage='100', CoopBossArmor='Off', CoopBossPoise='100')
    return ('; BWB same-PC research pair; native relay not started by preparation.\n'
            + ''.join(f'{key} = {value}\n' for key, value in settings.items())).encode()


def prepare(candidate=None, port=47800, duration=600, host_boss='ahua_guitoudao', guest_boss='056_youlong', output_parent=None):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('Invalid research UDP port')
    if type(duration) is not int or not 60 <= duration <= 1200:
        raise ValueError('Research duration must be 60..1200 seconds')
    candidate = Path(candidate) if candidate else build()
    accepted = verify_candidate(candidate)
    if accepted['own_sources'] != {name: sha(safe_file(ROOT, name).read_bytes()) for name in SOURCES}:
        raise ValueError('Candidate source differs from current adapter')
    catalog = json.loads((candidate / 'catalog.json').read_bytes())
    if host_boss not in catalog or guest_boss not in catalog:
        raise ValueError('Boss absent from pinned four-Boss catalog')
    session = 'bwb_' + secrets.token_hex(16)
    secret = secrets.token_hex(32)
    files = {}
    for role in ROLES:
        files[f'{role}/Mods/PBZCoop/PhantomPact.ini'] = ini(role, port, secret)
    # The accepted manifest pins the full executable hash; no process or DLL is opened.
    _, singleplayer = verify_release(ROOT)
    for role, boss in zip(ROLES, (host_boss, guest_boss)):
        request = dict(schema=1, mode='two-player-online-research', role=role, boss_id=boss,
            session=session, duration_seconds=duration, upstream_commit=COMMIT,
            exe_sha256=singleplayer['exe_sha256'], catalog_sha256=accepted['catalog_sha256'],
            candidate_manifest_sha256=sha((candidate / 'candidate.json').read_bytes()),
            saved_directory='Saved', lease_issued=False, prepared_only=True)
        files[f'{role}/launch-request.json'] = canonical(request) + b'\n'
    parent = Path(output_parent) if output_parent else ROOT / 'runtime/online-pairs'
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / session
    target.mkdir()
    manifest = dict(schema=1, status='prepared-only', session=session, port=port,
        duration_seconds=duration, candidate_id=accepted['candidate_id'],
        candidate_manifest_sha256=sha((candidate / 'candidate.json').read_bytes()),
        upstream_commit=COMMIT, exe_sha256=singleplayer['exe_sha256'],
        catalog_sha256=accepted['catalog_sha256'],
        bosses=dict(host=host_boss, guest=guest_boss), source_sha256=sha(Path(__file__).read_bytes()),
        transport='udp', bind_address='127.0.0.1', destination_address='127.0.0.1',
        host_listen_port=port, guest_local_port=0,
        independent_saved_directories=True, native_relay_executed=False,
        game_started=False, installed=False, lease_issued=False,
        complete_mod=False, runtime_acceptance_current=False,
        files={name: sha(data) for name, data in sorted(files.items())})
    for name, data in files.items():
        path = safe_file(target, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    for role in ROLES:
        (target / role / 'Saved').mkdir()
    (target / 'pair.json').write_bytes(canonical(manifest) + b'\n')
    verify(target, candidate)
    return target


def verify(directory, candidate):
    directory, candidate = Path(directory), Path(candidate)
    m = json.loads((directory / 'pair.json').read_bytes())
    c = verify_candidate(candidate)
    _, singleplayer = verify_release(ROOT)
    assert m['schema'] == 1 and m['status'] == 'prepared-only'
    assert re.fullmatch(r'bwb_[0-9a-f]{32}', m['session']) and directory.name == m['session']
    assert m['candidate_id'] == c['candidate_id'] and m['upstream_commit'] == COMMIT
    assert m['candidate_manifest_sha256'] == sha((candidate / 'candidate.json').read_bytes())
    assert c['own_sources'] == {name: sha(safe_file(ROOT, name).read_bytes()) for name in SOURCES}
    assert m['exe_sha256'] == singleplayer['exe_sha256'] and m['catalog_sha256'] == c['catalog_sha256']
    bosses = json.loads((candidate / 'catalog.json').read_bytes())
    assert set(m['bosses']) == set(ROLES) and all(boss in bosses for boss in m['bosses'].values())
    assert m['source_sha256'] == sha(Path(__file__).read_bytes())
    assert m['bind_address'] == m['destination_address'] == '127.0.0.1' and m['transport'] == 'udp'
    assert m['guest_local_port'] == 0 and m['host_listen_port'] == m['port']
    assert type(m['port']) is int and 1024 <= m['port'] <= 65535
    assert type(m['duration_seconds']) is int and 60 <= m['duration_seconds'] <= 1200
    for key in ('native_relay_executed','game_started','installed','lease_issued','complete_mod','runtime_acceptance_current'):
        assert m[key] is False
    expected = {f'{role}/{name}' for role in ROLES for name in ('Mods/PBZCoop/PhantomPact.ini', 'launch-request.json')}
    assert set(m['files']) == expected
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    assert actual == expected | {'pair.json'}, 'Pair contains unexpected/missing files'
    for name, digest in m['files'].items():
        assert sha(safe_file(directory, name).read_bytes()) == digest, 'Pair payload drift'
    secret = None
    for role in ROLES:
        saved = safe_file(directory, f'{role}/Saved')
        assert saved.is_dir() and not list(saved.iterdir()), 'Prepared save directory must be empty'
        raw = safe_file(directory, f'{role}/Mods/PBZCoop/PhantomPact.ini').read_bytes()
        found = re.search(rb'^Secret = ([0-9a-f]{64})$', raw, re.M)
        assert found
        secret = secret or found[1].decode()
        assert raw == ini(role, m['port'], secret), 'Unexpected relay settings'
        request = json.loads(safe_file(directory, f'{role}/launch-request.json').read_bytes())
        assert request == dict(schema=1, mode='two-player-online-research', role=role, boss_id=m['bosses'][role],
            session=m['session'], duration_seconds=m['duration_seconds'], upstream_commit=COMMIT,
            exe_sha256=m['exe_sha256'], catalog_sha256=c['catalog_sha256'],
            candidate_manifest_sha256=m['candidate_manifest_sha256'], saved_directory='Saved',
            lease_issued=False, prepared_only=True)
    assert m['independent_saved_directories'] is True
    return dict(passed=True, status='prepared-only', session=m['session'], roles=list(ROLES),
        bind_address='127.0.0.1', installed=False, game_started=False, lease_issued=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--port', type=int, default=47800)
    parser.add_argument('--duration', type=int, default=600)
    parser.add_argument('--host-boss', default='ahua_guitoudao')
    parser.add_argument('--guest-boss', default='056_youlong')
    args = parser.parse_args()
    target = prepare(args.candidate, args.port, args.duration, args.host_boss, args.guest_boss)
    print(json.dumps(dict(prepared=str(target), installed=False, game_started=False, lease_issued=False), ensure_ascii=False))
