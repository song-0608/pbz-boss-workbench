"""Publish four roles only after exact closed-session integration and offline gates."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import types

from mod_installation import ROOT, MANIFEST, assert_closed, digest, read, validate_package
from four_boss_integration_workflow import modules, verify as verify_workflow
from build_yanqiansui_centered_candidate import expected, verify as verify_candidate
from yanqiansui_centered_acceptance import verify_current
from release_youlong_workbench import acceptance as accepted_three, source_hashes

BASE = 'ahua-boss-workbench-v2-7b83ce4aa5d15a03'
BASE_SHA = 'ce424d1c9c3063a85955a15ef016d1f7ed13fc42db932ebd4ac9eb27a1394746'
WORKFLOW = ROOT / 'runtime/integration-workflows/four-boss-50445b9aeb27f044'
COLLECTOR_SHA = '4bbfc4528c086607ce81cb6aa603000717e607a8155d6e5a0a958801132a94e9'
OFFLINE = ROOT / 'evidence/adaptation/four-boss-v3-offline.json'
OWN = ('tools/release_four_boss_workbench.py', 'tools/boss_workbench_v3_window.py',
       'tests/test_four_boss_release.py', 'tests/test_boss_workbench_v3_window.py',
       'tools/terrain_startup_preflight.py', 'tests/test_terrain_startup_preflight.lua')
IDS = ['ahua_guitoudao', '057_wanjun', '073_yanqiansui', '056_youlong']


def inherited(candidate):
    current = verify_candidate(candidate)
    base_path = ROOT / 'releases' / BASE
    base = validate_package(base_path)
    assert digest(base_path / MANIFEST) == BASE_SHA
    old, new = modules(base), modules(current)
    assert {n for n in old if new.get(n) != old[n]} == {'boss_catalog.lua', 'workbench_catalog.lua', 'yanqiansui_arena_clearance.lua'}
    assert set(new) - set(old) == {'yanqiansui_clearance_core.lua'}
    registry = candidate / 'PBZBossControl/Scripts/boss_catalog.lua'
    lines = [r for r in registry.read_bytes().splitlines(keepends=True) if r.startswith(b"    {id='073_yanqiansui',name=")]
    assert len(lines) == 1
    assert registry.read_bytes().replace(lines[0], b'') == (base_path / 'PBZBossControl/Scripts/boss_catalog.lua').read_bytes()
    accepted_candidate = ROOT / 'runtime/release-candidates' / base['accepted_candidate']
    before, evidence = accepted_three(accepted_candidate, '20261116-115608')
    assert before['files'] == base['files']
    checks_path = ROOT / read(ROOT / base['acceptance_report'])['local_checks']['path']
    assert digest(checks_path) == base['local_checks_sha256']
    checks = read(checks_path)
    assert checks['passed'] and len(checks['checks']) == 13
    source_hashes(checks['sources'])
    baseline = ROOT / checks['baseline_checks']['path']
    assert digest(baseline) == checks['baseline_checks']['sha256']
    assert read(baseline)['passed'] and len(read(baseline)['checks']) == 79
    source_hashes(read(baseline)['source_sha256'])
    return {'release': BASE, 'manifest_sha256': BASE_SHA, 'unchanged_execution_camera_input_restoration': True,
            'accepted_three_evidence': evidence, 'baseline_groups': 79, 'release_groups': 13}


def validate_integration(report, current, previous):
    assert report['id'] == '073_yanqiansui' and report['module_source_sha256'] == current
    for key in ('passed', 'ordinary_roundtrip_verified', 'input_layers_recovered',
                'owned_object_cleanup_verified', 'new_profile_world_cycle_verified'):
        assert report[key] is True, key
    assert report['movement_camera']['passed'] and report['world_cycle']['passed']
    assert report['world_cycle']['skill_natural_damage']
    assert report['reused_ordinary_skills'] == previous and len(previous) == 8
    assert [(r['boss'], r['skill'], r['interrupt']) for r in report['skill_proofs']] == [
        ('ahua_guitoudao', 'skill_01', False), ('ahua_guitoudao', 'skill_08', True),
        ('073_yanqiansui', 'skill_01', False), ('073_yanqiansui', 'skill_01', False)]
    for row in report['skill_proofs']:
        assert row['local_displacement_verified']
        assert row['active_cancel_and_restoration'] if row['interrupt'] else row['natural_completion'] and row['restoration']['passed']


def integration(candidate, session):
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    manifest = verify_candidate(candidate)
    current = modules(manifest)
    previous, _ = verify_current(current)
    report_path = ROOT / 'research/boss-adaptation/developer-attempt-receipts' / ('four-boss-073_yanqiansui-' + session + '.json')
    report = read(report_path)
    validate_integration(report, current, previous)
    source_hashes(report['sources'])
    verify_workflow(WORKFLOW)
    path = ROOT / 'tools/collect_four_boss_integration.py'
    assert digest(path) == COLLECTOR_SHA
    source = path.read_text(encoding='utf-8')
    anchor = "    assert not output.exists(),'Preserve collected result';write_json(output,result)"
    assert source.count(anchor) == 1
    collector = types.ModuleType('readonly_four_boss_release_collector')
    collector.__file__ = str(path)
    exec(compile(source.replace(anchor, '    return result'), str(path), 'exec'), collector.__dict__)
    collector.verify_current = verify_current
    assert collector.collect(session, WORKFLOW.resolve(), '073_yanqiansui') == report
    independent_path = ROOT / 'evidence/official-validation/20261116-055334/boss-candidate-acceptance.json'
    independent = read(independent_path)
    from build_yanqiansui_profile import validate_report
    from collect_boss_candidate_acceptance import candidate_interval
    from collect_practice_stability import proof
    validate_report(independent)
    source_hashes(independent['sources'])
    raw = (independent_path.parent / 'UE4SS.log').read_text(encoding='utf-8', errors='replace')
    begin, _ = candidate_interval(raw, '073_yanqiansui')
    assert proof(raw[begin:], '20261116-055334', '琴女烟千岁') == independent['stability']
    assert independent['stability']['passed'] and independent['stability']['elapsed_seconds'] >= 600
    return {'session': session, 'ordinary_integration': {'path': report_path.relative_to(ROOT).as_posix(), 'sha256': digest(report_path)},
            'independent_base': {'path': independent_path.relative_to(ROOT).as_posix(), 'sha256': digest(independent_path)},
            'movement_camera': report['movement_camera'], 'world_cycle': report['world_cycle']}


def offline(candidate):
    assert_closed()
    manifest = verify_candidate(candidate)
    inherited(candidate)
    verify_current(modules(manifest))
    lua = str(ROOT.parent / 'build/lua-harness/Release/lua-lab.exe')
    from terrain_startup_preflight import render
    payload = ROOT / 'runtime/four-boss-startup-preflight-offline.lua'
    payload.write_bytes(render(candidate, int(time.time()) + 120, '123'))
    jobs = [
        ('four_profile_catalog', [lua, 'tests/test_four_boss_candidate.lua', str(candidate)]),
        ('centered_floor', [lua, 'tests/test_yanqiansui_clearance_centered.lua', str(ROOT), str(candidate)]),
        ('startup_readonly_preflight', [lua, 'tests/test_terrain_startup_preflight.lua', str(candidate), str(payload)]),
        ('selection_preserves_current', [lua, 'tests/test_workbench_selection_preflight.lua', str(candidate / 'PBZBossControl/Scripts/boss_workbench.lua')]),
    ]
    patterns = ('test_yanqiansui_centered_candidate.py', 'test_four_boss_release.py', 'test_boss_workbench_v3_window.py',
                'test_performance_comparison.py', 'test_player_status_stream.py', 'test_mod_installation.py')
    jobs.extend((name, [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', name, '-v']) for name in patterns)
    syntax = ROOT / 'runtime/four-boss-v3-syntax.lua'
    syntax.write_text('\n'.join('assert(loadfile(' + json.dumps((candidate / n).relative_to(ROOT).as_posix()) + '))' for n in manifest['files'] if n.endswith('.lua')) + '\n', encoding='utf-8')
    jobs.append(('all_lua_syntax', [lua, str(syntax)]))
    jobs.append(('player_window_smoke', [sys.executable, 'tools/boss_workbench_v3_window.py', '--smoke']))
    before = {n: digest(ROOT / n) for n in ('玩家设置.json', '玩家键位.json')}
    results = []
    for label, command in jobs:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
        print(label + ': ' + ('PASS' if result.returncode == 0 else 'FAIL'), flush=True)
        results.append({'name': label, 'passed': result.returncode == 0, 'output': (result.stdout + result.stderr).strip()})
    assert before == {n: digest(ROOT / n) for n in before}
    names = set(OWN) | {'tests/' + name for name in patterns}
    for name in ('test_four_boss_candidate.lua', 'test_workbench_selection_preflight.lua', 'test_yanqiansui_clearance_centered.lua'):
        names.add('tests/' + name)
    report = {'passed': all(r['passed'] for r in results), 'candidate': candidate.name,
              'candidate_manifest_sha256': digest(candidate / MANIFEST), 'checks': results,
              'source_sha256': {n: digest(ROOT / n) for n in sorted(names)}, 'game_started': False,
              'personal_settings_unchanged': True}
    OFFLINE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    assert report['passed'], 'Offline milestone not ready'
    return {'passed': True, 'groups': len(results), 'game_started': False}


def release(candidate, session):
    assert_closed()
    manifest = verify_candidate(candidate)
    checks = read(OFFLINE)
    assert checks['passed'] and checks['candidate'] == candidate.name
    assert checks['candidate_manifest_sha256'] == digest(candidate / MANIFEST)
    source_hashes(checks['source_sha256'])
    evidence = {'inherited_three': inherited(candidate), 'yanqiansui': integration(candidate, session)}
    contents = {n: (candidate / n).read_bytes() for n in manifest['files']}
    contents['PBZBossControl/README.md'] = ('# Boss 工作台 v3\n\n当前核定PBZ构建的本机隔离离线版。'
        '阿花、万钧、烟千岁、游龙四角色，共40项能力、41个绑定。\n\n'
        'Insert工作台，↑↓选择，Enter确认，F6接管，F10恢复。烟千岁及游龙在游戏内选择。'
        '工作台为Windows键盘浮层；保留原生冷却、地形及每轮十分钟限制。\n\n'
        '烟千岁保留900cm净空、24点、192次上限，仅初始化查询。新增落点中心与主角地面高差最多100cm，'
        '两个目标和全部净空点相对已投影中心地面高差不超过30cm。空间不足拒绝并保留当前角色。\n\n'
        '不会修改正式游戏、正式存档或回写研究进度。使用根目录开始Boss工作台.cmd，详见70-四Boss工作台v3操作说明.md。\n').encode('utf-8')
    hashes = {n: hashlib.sha256(data).hexdigest() for n, data in contents.items()}
    key = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:16]
    identifier = 'ahua-boss-workbench-v3-' + key
    target = ROOT / 'releases' / identifier
    report_path = ROOT / 'evidence/releases' / (identifier + '-acceptance.json')
    assert not target.exists() and not report_path.exists(), 'Preserve immutable releases'
    report = dict(evidence, passed=True, release_id=identifier, at=datetime.now().astimezone().isoformat(),
                  candidate=candidate.name, candidate_manifest_sha256=digest(candidate / MANIFEST),
                  module_source_sha256=modules(manifest), bosses=manifest['bosses'], locked_previews=[],
                  local_checks={'path': OFFLINE.relative_to(ROOT).as_posix(), 'sha256': digest(OFFLINE)},
                  source_sha256={n: digest(ROOT / n) for n in OWN})
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    target.mkdir(parents=True)
    for name, data in contents.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    manifest.update(release_id=identifier, files=hashes, status='release', complete_mod=True,
                    runtime_acceptance_current=True, integration_only=False, pending=[], locked_previews=[],
                    acceptance_report=report_path.relative_to(ROOT).as_posix(), acceptance_report_sha256=digest(report_path),
                    accepted_candidate=candidate.name, local_checks_sha256=digest(OFFLINE))
    (target / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    validate_package(target)
    return {'release': str(target), 'release_id': identifier, 'bosses': 4, 'abilities': 40, 'bindings': 41}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('check', 'release'))
    parser.add_argument('--session')
    args = parser.parse_args()
    candidate = ROOT / 'runtime/release-candidates' / expected()[-1]
    print(json.dumps(offline(candidate) if args.action == 'check' else release(candidate, args.session), ensure_ascii=False))
