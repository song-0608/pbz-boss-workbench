"""Check the standalone native relay and bootstrap; never load a game DLL."""
import argparse
import json
from pathlib import Path
import secrets
import socket
import subprocess
import time
import uuid

from build_phantom_boss_candidate import ROOT, canonical, sha
from build_phantom_boss_native import sources
from phantom_boss_native_patches import PATCHES, patched
from prepare_phantom_boss_pair import ini


def verify_build(target):
    target = Path(target)
    manifest = json.loads((target / 'native-build.json').read_bytes())
    folder, receipt = sources()
    identity = manifest['identity']
    assert identity['upstream_files'] == receipt['files']
    assert identity['patches'] == json.loads(json.dumps(PATCHES))
    for name, digest in identity['own_sources'].items():
        assert sha((ROOT / name).read_bytes()) == digest, 'Native tool source drift: ' + name
    for name, digest in manifest['prepared_native_source_sha256'].items():
        data = patched(name, (folder / name).read_bytes())
        assert sha(data) == digest and (target / 'source' / name).read_bytes() == data
    for name in ('phantom_boss_native_bootstrap.cpp', 'phantom_boss_native_probe.cpp'):
        assert (target / 'source' / name).read_bytes() == (ROOT / 'tools' / name).read_bytes()
    for name, digest in manifest['files'].items():
        assert sha((target / name).read_bytes()) == digest, 'Native binary drift'
    return manifest


def check(target):
    target = Path(target).resolve()
    manifest = verify_build(target)
    directory = ROOT / 'runtime/native-checks' / uuid.uuid4().hex
    directory.mkdir(parents=True)
    results = []
    probe = target / 'bootstrap_probe.exe'

    def record(name, raw, passed, **details):
        path = directory / (name + '.txt')
        path.write_bytes(raw)
        if not passed:
            raise RuntimeError(name + ' failed: ' + raw.decode('utf-8', errors='replace')[-1500:])
        results.append(dict(name=name, passed=True, output=path.relative_to(ROOT).as_posix(),
                            output_sha256=sha(raw), **details))
        print('PASS ' + name, flush=True)

    def run(mode, folder):
        return subprocess.run([str(probe), mode, str(folder)], capture_output=True,
                              timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)

    secret = secrets.token_hex(32)
    session = secrets.token_hex(16)
    # Bind a temporary loopback socket only to choose a currently free port.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as port_probe:
        port_probe.bind(('127.0.0.1', 0))
        port = port_probe.getsockname()[1]

    def fixture(name, role='host', duration=8, lease_change=None, start_change=None, ini_change=None, key=secret):
        folder = directory / name
        folder.mkdir()
        now = int(time.time())
        lease = dict(mode='two-player-online-research', issued_at=str(now-1),
                     expires_at=str(now+duration), role=role, session=session)
        start = dict(role='host' if role == 'host' else 'client', port=str(port),
                     peer='127.0.0.1', transport='udp', version='1.7.3')
        lease.update(lease_change or {})
        start.update(start_change or {})
        for filename, data in (('bwb_native_lease.ini', lease), ('net_start.txt', start)):
            (folder / filename).write_text(''.join(f'{k}={v}\n' for k, v in data.items()), encoding='utf-8')
        config = ini(role, port, key)
        for before, after in ini_change or ():
            assert config.count(before) == 1
            config = config.replace(before, after, 1)
        (folder / 'PhantomPact.ini').write_bytes(config)
        return folder

    upstream = subprocess.run([str(target / 'relay_cli.exe'), 'test', '--sockets', '0'],
        capture_output=True, timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
    raw = upstream.stdout + upstream.stderr
    record('upstream-regression', raw, upstream.returncode == 0 and b'all passed' in raw,
           assertions=raw.count(b'  ok   '), real_sockets=False)

    for role in ('host', 'guest'):
        folder = fixture('valid-' + role, role)
        result = run('validate', folder)
        record('valid-' + role, result.stdout + result.stderr, result.returncode == 0)

    invalid = [
        ('trailing-time', dict(lease_change={'issued_at': str(int(time.time())-1)+'junk'})),
        ('nan-time', dict(lease_change={'expires_at': 'nan'})),
        ('expired', dict(duration=-1)),
        ('future-issued', dict(lease_change={'issued_at': str(int(time.time())+60)})),
        ('unbounded', dict(duration=1201)),
        ('wrong-mode', dict(lease_change={'mode': 'offline'})),
        ('wrong-role', dict(lease_change={'role': 'guest'})),
        ('bad-session', dict(lease_change={'session': '../bad'})),
        ('non-udp', dict(start_change={'transport': 'steam'})),
        ('wrong-version', dict(start_change={'version': 'other'})),
        ('bad-port', dict(start_change={'port': '47800junk'})),
        ('port-overflow', dict(start_change={'port': '999999999999999999999'})),
        ('external-peer', dict(role='guest', start_change={'peer': '192.0.2.1'})),
        ('external-bind', dict(ini_change=[(b'ThisPCOnly = On', b'ThisPCOnly = Off')])),
        ('unsigned', dict(ini_change=[(b'Secret = '+secret.encode(), b'Secret = Off')])),
        ('extra-players', dict(ini_change=[(b'PartySize = 2', b'PartySize = 4')])),
    ]
    for name, kwargs in invalid:
        folder = fixture(name, **kwargs)
        result = run('validate', folder)
        record(name, result.stdout + result.stderr, result.returncode == 5
               and not (folder / 'relay_log.txt').exists())

    mutations = [
        ('reload-secret', [(b'Secret = '+secret.encode(), b'Secret = '+secrets.token_hex(32).encode())]),
        ('reload-unsigned', [(b'Secret = '+secret.encode(), b'Secret = Off')]),
        ('reload-party', [(b'PartySize = 2', b'PartySize = 4')]),
        ('reload-bind', [(b'ThisPCOnly = On', b'ThisPCOnly = Off')]),
        ('reload-address-policy', [(b'AllowAnyAddress = Off', b'AllowAnyAddress = On')]),
        ('reload-role', [(b'Role = Host', b'Role = Guest')]),
        ('reload-port', [(f'Port = {port}'.encode(), b'Port = 1')]),
    ]
    for name, edits in mutations:
        folder = fixture(name)
        replacement = (folder / 'PhantomPact.ini').read_bytes()
        for before, after in edits:
            assert replacement.count(before) == 1
            replacement = replacement.replace(before, after, 1)
        (folder / 'replacement.ini').write_bytes(replacement)
        result = run('reload', folder)
        record(name, result.stdout + result.stderr, result.returncode == 0
               and b'settings changed or expired' in (folder / 'relay_error.txt').read_bytes()
               and b'PBZCoop relay' not in (folder / 'relay_log.txt').read_bytes())

    for name, same_secret in (('signed-two-process-exchange', True), ('mismatched-secret-refused', False)):
        host = fixture(name+'-host', duration=7 if same_secret else 4)
        guest = fixture(name+'-guest', role='guest', duration=7 if same_secret else 4,
                        key=secret if same_secret else secrets.token_hex(32))
        processes = []
        try:
            for folder in (host, guest):
                processes.append(subprocess.Popen([str(probe), 'exchange', str(folder)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW))
            outputs = [p.communicate(timeout=20) for p in processes]
        finally:
            for p in processes:
                if p.poll() is None:
                    p.kill()
                    p.communicate(timeout=5)
        raw = b'\n'.join(out+err for out, err in outputs)
        expected = b'connected=1 sample=1 event=1 reset=1' if same_secret else b'connected=0 sample=0 event=0 reset=1'
        record(name, raw, all(p.returncode == (0 if same_secret else 4) for p in processes)
               and raw.count(expected) == 2, independent_processes=2, real_sockets=True,
               deadline_exit=True, mailbox_reset=True, bind_address='127.0.0.1')

    verify_build(target)
    report = dict(schema=1, status='standalone-native-milestone-only', passed=True,
        native_build=target.relative_to(ROOT).as_posix(),
        native_build_manifest_sha256=sha((target / 'native-build.json').read_bytes()),
        checks=results, groups=len(results), game_started=False, game_dll_loaded=False,
        installed=False, standalone_relay_executed=True, complete_mod=False,
        runtime_acceptance_current=False, source_sha256={name: sha((ROOT / name).read_bytes())
            for name in ('tools/check_phantom_boss_native.py', *manifest['identity']['own_sources'])})
    (ROOT / 'evidence/adaptation/phantom-pact-native.json').write_bytes(canonical(report)+b'\n')
    print(json.dumps(dict(passed=True, groups=len(results), game_started=False, game_dll_loaded=False)))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_build', type=Path)
    check(parser.parse_args().native_build)
