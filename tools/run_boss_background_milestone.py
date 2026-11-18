"""Run the offline Boss inventory, candidate generation and regression milestone.

Never launches Steam or PBZ, stages a live carrier, or sends game input.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from boss_adaptation_workflow import ROOT, sha, write_json
import boss_offline_inventory as inventory
from build_boss_profile_candidate import lua
import prepare_boss_inventory_workflow as workflows
import prepare_full_boss_catalog as full_catalog


TEST_MODULES = (
    'tests.test_boss_offline_inventory', 'tests.test_boss_inventory_boundaries',
    'tests.test_boss_metadata_jobs', 'tests.test_boss_native_grant_followup',
    'tests.test_native_grant_metadata_workflow', 'tests.test_native_grant_developer',
    'tests.test_native_grant_ui_stage', 'tests.test_expanded_boss_developer',
    'tests.test_full_boss_catalog', 'tests.test_full_catalog_progress',
)


def invoke(name, command):
    result = subprocess.run(command, cwd=ROOT, capture_output=True, encoding='utf-8', errors='replace', timeout=90)
    record = dict(name=name, passed=result.returncode == 0, output=(result.stdout + result.stderr).strip())
    print(name + ': ' + ('PASS' if record['passed'] else 'FAIL'), flush=True)
    if not record['passed']:
        print(record['output'], flush=True)
    return record


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    directory, summary = inventory.build()
    print('Inventory frozen: ' + summary['fingerprint'], flush=True)
    snapshot = inventory.read(directory / 'inventory.json')
    source_files = {name: digest for name, digest in snapshot['sources'].items()
                    if name.startswith(('tools/', 'tests/'))}
    for name in ('tools/run_boss_background_milestone.py', 'tools/boss_inventory_bundle.py',
                 'tools/prepare_boss_inventory_workflow.py', 'tools/native_grant_skill_gate.py',
                 'tools/prepare_full_boss_catalog.py', 'tools/full_boss_catalog_probe.lua',
                 'tools/stage_full_boss_catalog.py', 'tests/test_full_boss_catalog.lua',
                 'tests/test_boss_inventory_boundaries.py', 'tests/test_native_grant_candidate.lua',
                 'tests/test_expanded_boss_candidate.lua', *workflows.previous.SOURCES):
        source_files[name] = sha(ROOT / name)
    for module in TEST_MODULES:
        path = module.replace('.', '/') + '.py'
        source_files[path] = sha(ROOT / path)
    checks = [invoke('Python regressions', [sys.executable, '-B', '-X', 'utf8', '-m', 'unittest', *TEST_MODULES])]
    packages = []
    executable = ROOT.parent / 'build/lua-harness/Release/lua-lab.exe'
    queue, catalog = full_catalog.build()
    checks.append(invoke('Full catalog queue verification', [sys.executable, '-B', '-X', 'utf8',
                         'tools/stage_full_boss_catalog.py', 'verify', str(queue)]))
    scripts = [queue / 'metadata-collector.lua'] + [ROOT / row['directory'] / 'metadata-probe.lua'
                                                  for row in catalog['batches']]
    syntax = queue / 'offline-syntax.lua'
    syntax.write_bytes(('local files=' + lua([path.relative_to(ROOT).as_posix() for path in scripts])
        + "\nfor _,path in ipairs(files)do assert(loadfile(path))end\nprint('PASS catalog syntax: '..#files)\n").encode('utf-8'))
    checks.append(invoke('Full catalog and child Lua syntax', [str(executable), str(syntax)]))
    for mode in ('ok', 'expired', 'partial'):
        checks.append(invoke('Full catalog serial scheduling ' + mode, [str(executable),
                             'tests/test_full_boss_catalog.lua', '.', mode]))
    for pool in summary['skill_pools']:
        path = ROOT / pool['directory']
        identifier = pool['id']
        definition = inventory.read(path / 'manifest.json')['definition']
        config = directory / (identifier + '-fixture.lua')
        config.write_bytes(('return ' + lua(definition) + '\n').encode('utf-8'))
        fixture = 'tests/test_native_grant_candidate.lua' if len(pool['skills']) == 2 else 'tests/test_expanded_boss_candidate.lua'
        checks.append(invoke(identifier + ' native binding fixture', [str(executable), fixture,
                             str(path / 'boss_candidate.lua'), str(config)]))
        flow = workflows.build(path)
        checks.append(invoke(identifier + ' staged workflow verification', [sys.executable, '-B', '-X', 'utf8',
                             str(flow / 'inventory_ui_controller.py'), 'verify', str(flow)]))
        packages.append(dict(id=identifier, pool=pool['directory'], skills=len(pool['skills']),
                             pool_manifest_sha256=sha(path / 'manifest.json'),
                             workflow=flow.relative_to(ROOT).as_posix(), workflow_manifest_sha256=sha(flow / 'manifest.json')))
    for batch in summary['exact_grant_batches']:
        checks.append(invoke('Exact grant metadata batch verification', [sys.executable, '-B', '-X', 'utf8',
                             'tools/stage_boss_inventory_metadata.py', 'verify', str(ROOT / batch['directory'])]))
    unchanged = all(sha(ROOT / path) == digest for path, digest in source_files.items())
    unchanged = unchanged and inventory.read(directory / 'inventory.json') == snapshot
    assert unchanged, 'Source or inventory changed during this milestone; retain incomplete output'
    report = dict(schema=1, inventory=directory.relative_to(ROOT).as_posix(), inventory_sha256=sha(directory / 'inventory.json'),
                  source_sha256=source_files, summary=summary, packages=packages, checks=checks,
                  full_catalog=dict(directory=queue.relative_to(ROOT).as_posix(),
                      manifest_sha256=sha(queue / 'manifest.json'), batches=len(catalog['batches']),
                      requests=sum(row['requests'] for row in catalog['batches']),
                      complete_package_inventory=False, playable=False),
                  passed=all(check['passed'] for check in checks), game_started=False, ui_input_sent=False,
                  live_carrier_staged=False, installed=False, all_boss_skills_complete=False,
                  runtime_acceptance_current=False)
    key = hashlib.sha256(json.dumps(dict(sources=source_files, inventory=report['inventory_sha256']),
                                   sort_keys=True).encode()).hexdigest()[:16]
    target = ROOT / 'evidence/adaptation' / ('boss-background-milestone-' + key + '-' + str(time.time_ns()) + '.json')
    write_json(target, report)
    print(json.dumps(dict(report=str(target), passed=report['passed'], packages=packages,
                          exact_grant_requests=sum(batch['requests'] for batch in summary['exact_grant_batches']),
                          full_catalog=report['full_catalog'],
                          game_started=False), ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
