"""Publish the exact three-profile payload after independent closed-session proof."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import types

from mod_installation import ROOT, MANIFEST, assert_closed, digest, validate_package
from build_youlong_workbench_candidate import expected, verify as verify_candidate
from four_boss_integration_workflow import modules
from youlong_workbench_acceptance import verify_current

BASE = 'ahua-boss-workbench-v1-f0bcf1323e641e03'
BASE_SHA = '6cf83a155b7fab444d0ad0796c442a757f3b0f5df7d2c282d4903bad76fb78b7'
WORKFLOW = ROOT / 'runtime/integration-workflows/four-boss-50445b9aeb27f044'
LOCAL_REPORT = ROOT / 'evidence/adaptation/three-boss-v2-release-checks.json'
BASELINE_REPORT = ROOT / 'evidence/adaptation/three-boss-v2-baseline-checks.json'
OWN_SOURCES = ('tools/release_youlong_workbench.py', 'tools/boss_workbench_v2_window.py',
               'tests/test_boss_workbench_v2_window.py', 'tests/test_three_boss_release.py')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def source_hashes(sources):
    for name, value in sources.items():
        path = (ROOT / name).resolve()
        assert path.is_relative_to(ROOT.resolve()) and digest(path) == value, 'Source changed: ' + name


def inherited_payload(candidate):
    """Reconstruct every changed common module from the immutable published base."""
    from build_clearance_candidate import patched
    from build_selection_candidate import patch_arena, patch_workbench
    from build_three_boss_candidate import payloads
    from build_youlong_profile import build as youlong_profile

    current = validate_package(candidate)
    base_dir = ROOT / 'releases' / BASE
    base = validate_package(base_dir)
    assert digest(base_dir / MANIFEST) == BASE_SHA
    original = ROOT / 'runtime/release-candidates/ahua-boss-workbench-v2-dev-fc170a5ecd820768'
    _, contents = payloads(base_dir, original / 'PBZBossControl/Scripts/profiles')
    assert {n: hashlib.sha256(v).hexdigest() for n, v in contents.items()} == validate_package(original)['files']
    arena = 'PBZBossControl/Scripts/owned_arena.lua'
    menu = 'PBZBossControl/Scripts/boss_workbench.lua'
    contents[arena] = patch_arena(patched(contents[arena].decode('utf-8'))).encode('utf-8')
    contents[menu] = patch_workbench(contents[menu].decode('utf-8')).encode('utf-8')
    for name in ('yanqiansui_arena_clearance.lua', 'boss_selection_preflight.lua'):
        contents['PBZBossControl/Scripts/' + name] = (ROOT / 'tools' / name).read_bytes()
    profile = youlong_profile('20261116-073449')
    for name in ('youlong.lua', 'youlong_bindings.lua'):
        contents['PBZBossControl/Scripts/profiles/' + name] = (profile / name).read_bytes()
    registry = 'PBZBossControl/Scripts/boss_catalog.lua'
    text = (candidate / registry).read_bytes()
    additions = [line for line in text.splitlines(keepends=True) if line.startswith(b"    {id='056_youlong',name=")]
    assert len(additions) == 1
    assert text.replace(additions[0], b'') == (base_dir / registry).read_bytes()
    contents[registry] = text
    preview = 'PBZBossControl/Scripts/workbench_catalog.lua'
    contents[preview] = contents[preview].decode('utf-8').replace(
        "reason='身份已核实，独立操控和技能验收尚未通过',",
        "reason='烟千岁的地形、移动镜头及载图验收未完成，暂不开放',").encode('utf-8')
    # Documentation is independently checked by the exact candidate verifier.
    contents['PBZBossControl/README.md'] = (candidate / 'PBZBossControl/README.md').read_bytes()
    assert {n: hashlib.sha256(v).hexdigest() for n, v in contents.items()} == current['files'], \
        'Unrelated runtime, profile, loader entry, or assembly changed'
    accepted = ROOT / base['acceptance_report']
    assert digest(accepted) == base['acceptance_report_sha256']
    report = read(accepted)
    assert report['passed'] and report['ahua_current_source']['ready_for_release']
    assert all(report['ahua_current_source']['gates'].values())
    assert report['module_source_sha256'] == modules(base)
    for key in ('wanjun_independent_base', 'ordinary_switching', 'workbench', 'dead_target_recovery'):
        row = report[key]
        path = ROOT / row['path']
        assert digest(path) == row['sha256']
        evidence = read(path)
        source_hashes(evidence.get('sources', {}))
        assert evidence.get('passed', evidence.get('base_control_accepted')) is True
    checks = ROOT / 'evidence/adaptation/ahua-delivery-local-checks.json'
    assert digest(checks) == base['local_checks_sha256'] and read(checks)['passed']
    # Historical tooling has versioned additions for the new profiles. Preserve
    # its original report; only the inherited Lua runtime must remain identical.
    historical = read(checks)['source_sha256']
    source_hashes({n: d for n, d in historical.items() if n.startswith('mod/')})
    return {'release': BASE, 'manifest_sha256': BASE_SHA,
            'acceptance_report': base['acceptance_report'], 'acceptance_report_sha256': digest(accepted),
            'scope': 'Inherited accepted Ahua and WanJun behavior; only exact initialization, catalog and selection patches allowed',
            'unmodified_combat_camera_input_and_restoration': True,
            'historical_tool_changes_require_current_offline_checks': sorted(
                n for n, d in historical.items() if not n.startswith('mod/') and digest(ROOT / n) != d)}


def validate_world_report(report, current):
    assert report['passed'] and report['module_source_sha256'] == current
    assert report['id'] == '056_youlong' and report['ordinary_roundtrip_verified']
    assert report['ordinary_skills_verified'] and report['new_profile_world_cycle_verified']
    assert report['world_cycle']['passed'] and len(report['skill_proofs']) == 2
    assert len(report['reused_ordinary_skills']) == 8
    for proof in report['skill_proofs']:
        assert proof['local_displacement_verified'] and proof['natural_completion']
        assert proof['restoration']['passed']
    assert report['world_cycle']['skill_natural_damage']


def acceptance(candidate, session):
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    manifest = verify_candidate(candidate)
    current = modules(manifest)
    verify_current(current)
    inherited = inherited_payload(candidate)
    path = ROOT / 'research/boss-adaptation/developer-attempt-receipts' / ('four-boss-youlong-world-' + session + '.json')
    report = read(path)
    validate_world_report(report, current)
    source_hashes(report['sources'])
    # Read-only replay: retain every collector gate and replace only its final
    # non-overwriting write with a return, so the archived receipt stays intact.
    collector_path = ROOT / 'tools/collect_four_boss_world_missing.py'
    source = collector_path.read_text(encoding='utf-8')
    anchor = '    assert not output.exists();write_json(output,result)'
    assert source.count(anchor) == 1
    collector = types.ModuleType('readonly_three_profile_collector')
    collector.__file__ = str(collector_path)
    exec(compile(source.replace(anchor, '    return result'), str(collector_path), 'exec'), collector.__dict__)
    collector.verify = verify_current
    assert collector.collect(session, WORKFLOW.resolve()) == report
    independent_path = ROOT / 'research/boss-adaptation/developer-attempt-receipts/youlong-20261116-073449.json'
    independent = read(independent_path)
    source_hashes(independent['sources'])
    from collect_practice_stability import proof as stability
    from collect_youlong_attempt import actions_proof
    from collect_boss_candidate_acceptance import candidate_interval
    work = ROOT / 'evidence/official-validation/20261116-073449'
    raw = (work / 'UE4SS.log').read_text(encoding='utf-8', errors='replace')
    begin, _ = candidate_interval(raw, '056_youlong')
    assert stability(raw[begin:], '20261116-073449', '发狂的水行帮主：游龙') == independent['stability']
    assert independent['stability']['passed'] and independent['formal_postcheck_passed']
    assert actions_proof(raw, read(work / 'player-extra-skill-actions.json'),
        str(ROOT / 'runtime/official-validation-20261116-073449/state.json'), begin,
        independent['bindings']) == independent['actions']
    return manifest, {'inherited_v1': inherited,
        'exact_registry_world': {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest(path)},
        'youlong_independent': {'path': independent_path.relative_to(ROOT).as_posix(), 'sha256': digest(independent_path)},
        'ordinary_action_count': 8, 'current_world_skill_count': 2,
        'world_cycle': report['world_cycle'], 'session': session}


def offline(candidate, session):
    assert_closed()
    manifest, _ = acceptance(candidate, session)
    frozen_check = ROOT / 'tools/check_ahua_delivery.py'
    assert digest(frozen_check) == 'af3f76ea755ecdba2dbb4d0ca4883184a201f07ad154e97924e0dcbfd27ccf40'
    cached = read(BASELINE_REPORT) if BASELINE_REPORT.exists() else {}
    reusable = cached.get('passed') and len(cached.get('checks', [])) == 79 and all(
        (ROOT / n).is_file() and digest(ROOT / n) == d for n, d in cached.get('source_sha256', {}).items())
    if reusable:
        print('79 baseline check groups: current source snapshot reused', flush=True)
    else:
        source = frozen_check.read_text(encoding='utf-8')
        anchor = "target = ROOT / 'evidence/adaptation/ahua-delivery-local-checks.json'"
        assert source.count(anchor) == 1
        source = source.replace(anchor, "target = ROOT / 'evidence/adaptation/three-boss-v2-baseline-checks.json'")
        baseline = types.ModuleType('versioned_v2_baseline_checks')
        baseline.__file__ = str(frozen_check)
        exec(compile(source, str(frozen_check), 'exec'), baseline.__dict__)
        assert baseline.main() == 0, 'Current baseline offline regression failed'
    harness = str(ROOT.parent / 'build/lua-harness/Release/lua-lab.exe')
    jobs = [('exact_three_profiles', [harness, 'tests/test_youlong_workbench_candidate.lua', str(candidate)]),
        ('selection_cleanup', [harness, 'tests/test_workbench_selection_preflight.lua', str(candidate / 'PBZBossControl/Scripts/boss_workbench.lua')])]
    for pattern in ('test_youlong_workbench_acceptance.py', 'test_boss_workbench_v2_window.py',
                    'test_three_boss_release.py', 'test_youlong_attempt.py', 'test_youlong_profile.py',
                    'test_player_status_stream.py', 'test_performance_comparison.py',
                    'test_workbench_release_runtime.py', 'test_mod_installation.py'):
        jobs.append((pattern, [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', pattern, '-v']))
    syntax = ROOT / 'runtime/three-boss-v2-syntax.lua'
    syntax.write_text('\n'.join('assert(loadfile(' + json.dumps((candidate / n).relative_to(ROOT).as_posix()) + '))'
        for n in manifest['files'] if n.endswith('.lua')) + '\n', encoding='utf-8')
    jobs.append(('all_payload_lua_syntax', [harness, str(syntax)]))
    jobs.append(('player_window_smoke', [sys.executable, 'tools/boss_workbench_v2_window.py', '--smoke']))
    personal = {name: digest(ROOT / name) for name in ('玩家设置.json', '玩家键位.json')}
    results = []
    for name, args in jobs:
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
        print(name + ': ' + ('PASS' if result.returncode == 0 else 'FAIL'), flush=True)
        results.append({'name': name, 'passed': result.returncode == 0,
                        'output': (result.stdout + result.stderr).strip()})
    assert personal == {name: digest(ROOT / name) for name in personal}, 'Smoke changed personal settings'
    source_names = set(OWN_SOURCES)
    source_names.update('tests/' + name for name, _ in jobs if name.startswith('test_'))
    source_names.update(('tests/test_youlong_workbench_candidate.lua', 'tests/test_workbench_selection_preflight.lua'))
    report = {'passed': all(row['passed'] for row in results), 'checks': results,
        'candidate': candidate.name, 'candidate_manifest_sha256': digest(candidate / MANIFEST),
        'session': session, 'game_started': False, 'personal_settings_unchanged': True,
        'baseline_checks': {'path': BASELINE_REPORT.relative_to(ROOT).as_posix(), 'sha256': digest(BASELINE_REPORT)},
        'sources': {name: digest(ROOT / name) for name in sorted(source_names)}}
    LOCAL_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    assert report['passed'], 'Offline release checks failed'
    return report


def release(candidate, session):
    assert_closed()
    manifest, evidence = acceptance(candidate, session)
    checks = read(LOCAL_REPORT)
    assert checks['passed'] and checks['candidate'] == candidate.name and checks['session'] == session
    assert checks['candidate_manifest_sha256'] == digest(candidate / MANIFEST)
    source_hashes(checks['sources'])
    assert digest(BASELINE_REPORT) == checks['baseline_checks']['sha256']
    baseline = read(BASELINE_REPORT)
    assert baseline['passed']
    source_hashes(baseline['source_sha256'])
    fingerprint = hashlib.sha256(json.dumps(manifest['files'], sort_keys=True).encode()).hexdigest()[:16]
    identifier = 'ahua-boss-workbench-v2-' + fingerprint
    target = ROOT / 'releases' / identifier
    report_path = ROOT / 'evidence/releases' / (identifier + '-acceptance.json')
    assert not target.exists() and not report_path.exists(), 'Preserve immutable releases'
    report = dict(evidence, release_id=identifier, passed=True,
        at=datetime.now().astimezone().isoformat(), module_source_sha256=modules(manifest),
        candidate=candidate.name, candidate_manifest_sha256=digest(candidate / MANIFEST),
        scope='current fixed PBZ build, local protected offline launcher',
        local_checks={'path': LOCAL_REPORT.relative_to(ROOT).as_posix(), 'sha256': digest(LOCAL_REPORT)},
        source_sha256={name: digest(ROOT / name) for name in OWN_SOURCES},
        bosses=manifest['bosses'], locked_previews=['073_yanqiansui'],
        performance='Native UObject cache and prior incremental scheduling retained; no GPU FPS claim',
        evidence_policy='Unchanged v1 behavior inherited; YouLong independent baseline and eight ordinary actions reused by exact sources; fresh three-profile World cycle reparsed')
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    target.mkdir(parents=True)
    for name in manifest['files']:
        output = target / name
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate / name, output)
    manifest.update(release_id=identifier, status='release', complete_mod=True,
        runtime_acceptance_current=True, at=report['at'], integration_only=False, pending=[],
        accepted_candidate=candidate.name, acceptance_report=report_path.relative_to(ROOT).as_posix(),
        acceptance_report_sha256=digest(report_path), local_checks_sha256=digest(LOCAL_REPORT))
    (target / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    validate_package(target)
    return {'release': str(target), 'release_id': identifier, 'bosses': 3, 'abilities': 36, 'bindings': 37}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('check', 'release'))
    parser.add_argument('--session', required=True)
    args = parser.parse_args()
    candidate = ROOT / 'runtime/release-candidates' / expected()[-1]
    result = offline(candidate, args.session) if args.action == 'check' else release(candidate, args.session)
    print(json.dumps({k: v for k, v in result.items() if k not in ('checks', 'sources')}, ensure_ascii=False))
