"""Single backend milestone: source gates, Lua simulations and candidate syntax; never launch."""
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid
from build_phantom_boss_candidate import ROOT, SOURCES, build, sha, verify_candidate, verify_release

TESTS = ('tests/test_phantom_boss_protocol.lua', 'tests/test_phantom_boss_adapter.lua',
         'tests/test_phantom_boss_candidate.py', 'tests/compile_phantom_boss_candidate.lua',
         'tests/test_phantom_boss_entry.lua')


def protected_files():
    names = ['玩家设置.json', '玩家键位.json', '项目状态.json', '开始Boss工作台.cmd']
    files = {n: sha((ROOT / n).read_bytes()) if (ROOT / n).exists() else None for n in names}
    directory, manifest = verify_release(ROOT)
    files['accepted-release'] = sha((directory / 'pbz-release.json').read_bytes())
    files['accepted-payload'] = manifest['files']
    return files


def run():
    before = protected_files()
    target = build()
    lab = ROOT.parent / 'build/lua-harness/Release/lua-lab.exe'
    commands = [
        ('protocol_simulation', [str(lab), str(ROOT / TESTS[0]), str(ROOT)], 16),
        ('adapter_mocked_api', [str(lab), str(ROOT / TESTS[1]), str(ROOT)], 18),
        ('candidate_python', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_phantom_boss_candidate.py', '-v'], 14),
        ('entry_mocked_research_lease', [str(lab), str(ROOT / TESTS[4]), str(target)], 6),
        ('patched_lua_compile_only', [str(lab), str(ROOT / TESTS[3]), str(target)], 10),
    ]
    log_directory = ROOT / 'runtime/online-checks' / uuid.uuid4().hex
    log_directory.mkdir(parents=True)
    results = []
    for name, command, expected in commands:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=90)
        raw = completed.stdout + completed.stderr
        output = raw.decode('utf-8', errors='replace')
        print(output, flush=True)
        if completed.returncode:
            raise RuntimeError(name + ' failed')
        pattern = r'Ran (\d+) tests?' if name == 'candidate_python' else (
            r'PASS syntax only: (\d+)' if name == 'patched_lua_compile_only' else r'PASS (\d+) (?:protocol|adapter|entry) groups')
        found = re.search(pattern, output)
        if not found or int(found[1]) != expected:
            raise RuntimeError(name + ' did not report its complete expected test count')
        log = log_directory / (name + '.txt')
        log.write_bytes(raw)
        results.append(dict(name=name, passed=True, groups=expected,
                            output=log.relative_to(ROOT).as_posix(), output_sha256=sha(raw)))
    if protected_files() != before:
        raise RuntimeError('Protected single-player package, entry or settings changed')
    manifest = verify_candidate(target)
    report = dict(schema=1, status='backend-milestone-only', passed=True,
        complete_mod=False, runtime_acceptance_current=False, game_started=False,
        native_relay_executed=False, installed=False, candidate=target.relative_to(ROOT).as_posix(),
        candidate_manifest_sha256=sha((target / 'candidate.json').read_bytes()),
        singleplayer_payload_files_verified=len(before['accepted-payload']),
        personal_settings_and_singleplayer_unchanged=True, upstream_commit=manifest['upstream_commit'],
        upstream_reviewed_sources=19, catalog_bosses=4, catalog_abilities=40,
        control_plane_test_groups=sum(row['groups'] for row in results[:-1]),
        syntax_checked_lua_files=10, checks=results, pending=manifest['pending'],
        source_sha256={n: sha((ROOT / n).read_bytes()) for n in (*SOURCES, *TESTS, 'tools/check_phantom_boss_backend.py',
            'tools/verify_phantom_boss_backend.py')})
    path = ROOT / 'evidence/adaptation/phantom-pact-backend.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.pending')
    pending.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    pending.replace(path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    run()
