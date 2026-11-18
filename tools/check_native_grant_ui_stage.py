"""Freeze input-free staging workflows and run offline regression only."""
import hashlib
import json
import subprocess
import sys
import time

from boss_adaptation_workflow import ROOT, sha, write_json
import native_grant_ui_stage as flow


def check():
    sources = {p: sha(ROOT / p) for p in (*flow.SOURCES, 'tools/check_native_grant_ui_stage.py')}
    packages = []
    for identifier in flow.bundle.REVIEWS:
        target = flow.bundle.build(identifier)
        output = flow.build(target)
        manifest = flow.verify(output)
        assert manifest['ui_input_sent'] is False and manifest['playable'] is False
        packages.append(dict(id=identifier, bundle=target.relative_to(ROOT).as_posix(),
            workflow=output.relative_to(ROOT).as_posix(), workflow_manifest_sha256=sha(output / 'manifest.json'),
            manifest=manifest, staged_on_game=False, native_grants_current=False,
            activation_verified=False, damage_verified=False, playable=False))
    result = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-m', 'unittest',
        'tests.test_native_grant_ui_stage', 'tests.test_native_grant_developer',
        'tests.test_native_grant_metadata_workflow', 'tests.test_boss_native_grant_followup'],
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert all(sha(ROOT / p) == digest for p, digest in sources.items())
    report = dict(schema=1, kind='native_grant_ui_stage_offline', sources=sources,
        packages=packages, passed=result.returncode == 0, output=result.stdout + result.stderr,
        game_started=False, ui_input_sent=False, installed=False, new_playable_bosses=0,
        runtime_acceptance_current=False)
    key = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()[:16]
    target = ROOT / 'evidence/adaptation' / ('native-grant-ui-stage-offline-' + key + '-' + str(time.time_ns()) + '.json')
    assert not target.exists()
    write_json(target, report)
    print(json.dumps(dict(report=str(target), passed=report['passed'], workflows=[
        p['workflow'] for p in packages], game_started=False), ensure_ascii=False))
    if not report['passed']: print(report['output'])
    return report['passed']


if __name__ == '__main__': raise SystemExit(0 if check() else 1)
