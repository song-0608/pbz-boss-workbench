"""Compile the actual loader input implementation with deterministic Win32 API fixtures."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'upstream/RE-UE4SS/deps/first/Input'


def main():
    run_id = datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
    work = ROOT / 'evidence/input-regression' / run_id
    work.mkdir(parents=True)
    binary = work / 'input-regression.exe'
    env_run = subprocess.run(['cmd.exe', '/d', '/s', '/c',
        'call D:\\vs\\VC\\Auxiliary\\Build\\vcvars64.bat >nul && set'],
        capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    env = os.environ.copy()
    for line in env_run.stdout.decode('mbcs').splitlines():
        if '=' in line and not line.startswith('='):
            key, value = line.split('=', 1)
            env[key] = value
    compiler = Path(env['VCToolsInstallDir']) / 'bin/Hostx64/x64/cl.exe'
    compile_run = subprocess.run([str(compiler), '/nologo', '/std:c++20', '/EHsc', '/W4',
        '/I' + str(SOURCE / 'include'),
        '/I' + str(ROOT / 'upstream/RE-UE4SS/deps/first/String/include'),
        str(ROOT / 'tests/test_win32_async_input.cpp'), '/Fe:' + str(binary),
        '/Fo:' + str(work / 'input-regression.obj')], env=env, cwd=work,
        capture_output=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
    compile_text = (compile_run.stdout + compile_run.stderr).decode('mbcs', errors='replace')
    (work / 'compile.log').write_text(compile_text, encoding='utf-8')
    if compile_run.returncode:
        raise RuntimeError(compile_text)
    test = subprocess.run([str(binary)], capture_output=True, timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW)
    output = (test.stdout + test.stderr).decode('utf-8', errors='replace')
    files = [ROOT / 'tests/test_win32_async_input.cpp',
             SOURCE / 'src/Platform/Win32AsyncInputSource.cpp',
             SOURCE / 'include/Input/Platform/Win32AsyncInputSource.hpp']
    result = {'at': datetime.now().astimezone().isoformat(),
        'passed': test.returncode == 0 and 'WIN32_ASYNC_INPUT_REGRESSION:PASS' in output,
        'compiler': str(compiler), 'output': output,
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        'scope': 'Production C++ input implementation, deterministic Win32 API fixture; no game input sent'}
    (work / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (work.parent / 'latest-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(output)
    if not result['passed']:
        raise RuntimeError('Input regression failed')


if __name__ == '__main__':
    main()
