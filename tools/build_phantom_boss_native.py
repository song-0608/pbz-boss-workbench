"""Build a local same-PC relay dependency from verified sources; never load the DLL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from build_phantom_boss_candidate import COMMIT, ROOT, canonical, safe_file, sha, verify_upstream
from phantom_boss_native_patches import PATCHES, patched

BOOTSTRAP = 'tools/phantom_boss_native_bootstrap.cpp'


def sources():
    reviewed = ROOT / 'runtime/integration-research/PhantomPact' / COMMIT
    verify_upstream(reviewed)
    folder = reviewed / 'runtime-sources'
    receipt = json.loads((folder / 'source-receipt.json').read_bytes())
    assert receipt['commit'] == COMMIT and receipt['executed'] is False
    for name, row in receipt['files'].items():
        data = safe_file(folder, name).read_bytes()
        assert len(data) == row['bytes'] and sha(data) == row['sha256']
        assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == row['git_blob']
        if (reviewed / name).is_file():
            assert data == (reviewed / name).read_bytes(), 'Native source differs from reviewed pin'
    return folder, receipt


def compiler_environment():
    locator = Path(os.environ['ProgramFiles(x86)']) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    installation = subprocess.check_output([str(locator), '-latest', '-products', '*', '-requires',
        'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], timeout=20).decode().strip()
    setup = Path(installation) / 'VC/Auxiliary/Build/vcvars64.bat'
    assert setup.is_file()
    result = subprocess.run(f'cmd.exe /d /s /c "call "{setup}" >nul && set"',
                            capture_output=True, timeout=30, check=True)
    # Never print the captured environment: it may contain unrelated credentials.
    env = dict(os.environ)
    for line in result.stdout.decode('mbcs', errors='replace').splitlines():
        if '=' in line and not line.startswith('='):
            key, value = line.split('=', 1)
            for existing in tuple(env):
                if existing.lower() == key.lower():
                    del env[existing]
            env[key] = value
    compiler = shutil.which('cl.exe', path=next(v for k, v in env.items() if k.lower() == 'path'))
    assert compiler
    return env, Path(compiler)


def build():
    folder, receipt = sources()
    identities = {name: sha((ROOT / name).read_bytes()) for name in (BOOTSTRAP,
        'tools/build_phantom_boss_native.py', 'tools/fetch_phantom_boss_runtime_sources.py',
        'tools/phantom_boss_native_patches.py', 'tools/phantom_boss_native_probe.cpp')}
    env, compiler = compiler_environment()
    identity = dict(own_sources=identities, upstream_commit=COMMIT, upstream_files=receipt['files'],
                    compiler_path=str(compiler), compiler_sha256=sha(compiler.read_bytes()),
                    patches=PATCHES, deterministic_build=True)
    target = ROOT / 'runtime/native-builds' / ('bwb-loopback-' + sha(canonical(identity))[:20])
    target.mkdir(parents=True, exist_ok=True)
    source_copy = target / 'source'
    prepared = {}
    for name in receipt['files']:
        if name.startswith('native/'):
            data = patched(name, safe_file(folder, name).read_bytes())
            path = safe_file(source_copy, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            prepared[name] = sha(data)
    for name in (BOOTSTRAP, 'tools/phantom_boss_native_probe.cpp'):
        shutil.copyfile(ROOT / name, source_copy / Path(name).name)
    native = source_copy / 'native'
    commands = [
        ('main', ['/LD', str(source_copy / Path(BOOTSTRAP).name), '/Fe:' + str(target / 'main.dll')]),
        ('relay_cli', [str(native / 'relay_cli.cpp'), '/Fe:' + str(target / 'relay_cli.exe')]),
        ('bootstrap_probe', [str(source_copy / 'phantom_boss_native_probe.cpp'), '/Fe:' + str(target / 'bootstrap_probe.exe')]),
    ]
    logs = {}
    for name, extra in commands:
        command = [str(compiler), '/nologo', '/std:c++20', '/O2', '/MT', '/EHsc', '/W3', '/utf-8',
                   '/D_WINSOCK_DEPRECATED_NO_WARNINGS', '/I' + str(native), '/Brepro',
                   '/Fo:' + str(target / (name + '.obj')), *extra,
                   '/link', '/NOLOGO', '/Brepro', 'ws2_32.lib', 'bcrypt.lib', 'winmm.lib', 'user32.lib']
        completed = subprocess.run(command, cwd=target, env=env, capture_output=True, timeout=90)
        raw = completed.stdout + completed.stderr
        (target / (name + '-build.txt')).write_bytes(raw)
        logs[name] = sha(raw)
        if completed.returncode:
            raise RuntimeError(name + ' compilation failed: ' + raw.decode('mbcs', errors='replace')[-2000:])
        print('Compiled ' + name + '; not executed', flush=True)
    manifest = dict(schema=1, status='compiled-not-loaded', identity=identity,
        files={name: sha((target / name).read_bytes()) for name in ('main.dll', 'relay_cli.exe', 'bootstrap_probe.exe')},
        prepared_native_source_sha256=prepared,
        build_log_sha256=logs, game_started=False, dll_loaded=False, installed=False,
        native_relay_executed=False, complete_mod=False, runtime_acceptance_current=False,
        scope='same-PC loopback UDP; signed two-player relay; no Steam/pad/cursor/display threads')
    (target / 'native-build.json').write_bytes(canonical(manifest) + b'\n')
    print(json.dumps(dict(native_build=str(target), files=manifest['files'], dll_loaded=False), ensure_ascii=False))
    return target


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    build()
