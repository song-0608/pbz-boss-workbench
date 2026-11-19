"""Run the focused reference-controller milestone entirely offline."""
import hashlib
import json
import re
import subprocess
import sys

from boss_adaptation_workflow import ROOT, sha, write_json
from build_boss_profile_candidate import lua
import prepare_boss_subtree_references as references
import run_boss_background_milestone as background
import stage_boss_subtree_references as collector
import prepare_boss_native_combo_workflow as native_combo

BASE = 'evidence/adaptation/boss-subtree-reference-delta-03a3da0f935731f9.json'
CURRENT = 'runtime/next-boss-reference-query.json'


def collector_modes(manifest):
    return ('ok', 'subtree', 'unavailable', 'wrong_identity', 'expired', 'frozen_clock') if manifest['jobs'] else ()


def record_report(report, root=ROOT):
    # Imported native receipts can change the plan without changing source
    # bytes. Keep both milestones instead of colliding on a source-only key.
    identity = {key: report[key] for key in ('base_report', 'base_sha256',
                'source_sha256', 'reference_plan', 'passed')}
    if 'combo_dependencies' in report:
        identity['combo_dependencies'] = report['combo_dependencies']
    identity['checks'] = [{key: value for key, value in check.items() if key != 'output'}
                          for check in report['checks']]
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    target = root / 'evidence/adaptation' / ('boss-reference-controller-milestone-' + key + '.json')
    if target.exists():
        previous = json.loads(target.read_bytes())
        assert all(previous[name] == report[name] for name in identity if name != 'checks'), \
            'preserve original milestone identity'
        assert [{k: v for k, v in check.items() if k != 'output'} for check in previous['checks']] == identity['checks']
    else:
        write_json(target, report)
    plan = report['reference_plan']
    status = 'offline_checks_failed'
    if report['passed']:
        status = 'ready_for_isolated_metadata_session' if plan['queries'] else 'reference_type_queue_complete'
    write_json(root / CURRENT, dict(schema=1, status=status,
        report=target.relative_to(root).as_posix(), report_sha256=sha(target),
        plan=plan['directory'], plan_manifest_sha256=plan['manifest_sha256'],
        request_counts=plan['request_counts'], batches=plan['batches'],
        offline_checks_passed=report['passed'], native_type_queries_executed=False,
        native_grants_verified=False, playable=False, game_started=False,
        authentication_state='not_inferred', session_state='check_existing_entry_before_preparing',
        separate_historical_grant_query_required=False))
    return target


def run():
    base = json.loads((ROOT / BASE).read_bytes())
    names = set(base['source_sha256']) | set(references.SOURCES)
    names.update(background.combo_dependencies.SOURCES)
    names.update(native_combo.SOURCES)
    names.update(native_combo.bundle.SOURCES)
    names.update(background.combo_audit.SOURCES)
    names.update(module.replace('.', '/') + '.py' for module in background.TEST_MODULES)
    names.add('tools/run_boss_reference_milestone.py')
    sources = {name: sha(ROOT / name) for name in sorted(names)}
    directory, manifest = references.build()
    manifest_sha = sha(directory / 'manifest.json')
    manifest, _ = collector.verify(directory)
    dependency_path, dependency_report = background.combo_dependencies.build()
    dependency_sha = sha(dependency_path)
    checks = []
    command = [sys.executable, '-B', '-X', 'utf8', '-m', 'unittest', *background.TEST_MODULES]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, encoding='utf-8', errors='replace', timeout=120)
    output = result.stdout + result.stderr
    counts = re.findall(r'Ran (\d+) tests?', output)
    checks.append(dict(name='Current Python regressions', passed=result.returncode == 0,
        tests=int(counts[-1]) if counts else None, output=output.strip()))
    print('Python regressions: ' + ('PASS' if result.returncode == 0 else 'FAIL'), flush=True)
    executable = ROOT.parent / 'build/lua-harness/Release/lua-lab.exe'
    fixture = ROOT / 'runtime' / ('reference-fixture-' + manifest['fingerprint'] + '.lua')
    fixture.write_text('return ' + lua(manifest['jobs']), encoding='utf-8')
    if not manifest['jobs']:
        checks.append(dict(name='No pending native reference queries; do not reload an empty collector',
                           passed=True, queries=0, native_input_required=False))
    for mode in collector_modes(manifest):
        result = subprocess.run([str(executable), 'tests/test_boss_subtree_reference_collector.lua',
            str(directory / 'metadata-collector.lua'), str(fixture), mode], cwd=ROOT,
            capture_output=True, encoding='utf-8', errors='replace', timeout=20)
        accepted = False
        try:
            outcomes = collector.analyze(collector.lines_for(result.stdout), manifest)
            accepted = True
        except AssertionError:
            outcomes = []
        expected = mode not in ('expired', 'frozen_clock')
        verified = sum(row['metadata_verified'] for row in outcomes)
        wanted = len(manifest['jobs']) if mode in ('ok', 'subtree') else 0
        passed = result.returncode == 0 and accepted is expected and verified == wanted
        check = dict(name=f"Generated {len(manifest['batches'])}-child collector: " + mode, passed=passed,
            simulated=True, queries=len(outcomes), verified=verified, accepted=accepted)
        if not passed:
            check['output'] = result.stdout + result.stderr
        checks.append(check)
        print(check['name'] + ': ' + ('PASS' if passed else 'FAIL'), flush=True)
    assert all(sha(ROOT / name) == digest for name, digest in sources.items()), 'sources changed during milestone'
    assert sha(directory / 'manifest.json') == manifest_sha
    assert sha(dependency_path) == dependency_sha, 'dependency graph changed during milestone'
    report = dict(schema=1, kind='boss_subtree_reference_controller_milestone',
        base_report=BASE, base_sha256=sha(ROOT / BASE),
        changed_base_sources=[p for p, h in base['source_sha256'].items() if sources[p] != h],
        source_sha256=sources, checks=checks,
        reference_plan=dict(directory=directory.relative_to(ROOT).as_posix(), manifest_sha256=manifest_sha,
            queries=len(manifest['jobs']), request_counts=manifest['request_counts'],
            batches=len(manifest['batches']), stage_supported=True,
            native_type_queries_executed=False, native_grants_verified=False, playable=False),
        combo_dependencies=dict(report=dependency_path.relative_to(ROOT).as_posix(),
            report_sha256=dependency_sha, summary=dependency_report['summary'],
            activation_allowed=False, execution_order_proven=False, playable=False),
        passed=all(check['passed'] for check in checks), game_started=False,
        ui_input_sent=False, live_carrier_staged=False, installed=False,
        runtime_acceptance_current=False, all_boss_skills_complete=False)
    target = record_report(report)
    print(json.dumps(dict(report=str(target), passed=report['passed'], plan=str(directory),
                          queries=len(manifest['jobs']), game_started=False), ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(run())
