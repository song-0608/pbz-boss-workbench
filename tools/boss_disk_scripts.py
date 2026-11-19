"""Plan, extract and reconcile offline Blueprint functions from a verified disk scan."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import boss_disk_declarations as disk
import boss_disk_dependencies as dependencies


def plan(scan, mapping, target):
    scan, mapping, target = Path(scan).resolve(), Path(mapping).resolve(), Path(target).resolve()
    report = json.loads(scan.read_bytes())
    if (report.get('kind') != 'offline_native_dependency_scan'
            or report.get('declaration_contents_verified') is not True
            or report['mapping_sha256'] != disk.digest(mapping)):
        raise ValueError('Verified disk scan and exact mapping required')
    rows = []
    for item in report['packages']:
        count = item['function_count']
        if type(count) is not int or not 0 <= count <= 1024:
            raise ValueError('Bounded serialized function count required')
        if count:
            dependencies.native_package(item['package'])
            rows.append(dict(package=item['package'], functions=count,
                             declaration_sha256=item['declaration_sha256']))
    if not rows or len({r['package'].casefold() for r in rows}) != len(rows):
        raise ValueError('Unique nonempty native function package list required')
    target.mkdir(parents=True, exist_ok=False)
    batches = []
    for offset in range(0, len(rows), 64):
        ordinal = offset//64
        filename = f'job-{ordinal:04d}.json'
        packages = [r['package'] for r in rows[offset:offset+64]]
        disk.write_new(target/filename, dict(mode='native_scripts', usmap=str(mapping), packages=packages))
        batches.append(dict(job=filename, sha256=disk.digest(target/filename), packages=packages,
                            output=f'batch-{ordinal:04d}'))
    result = dict(schema=1, kind='offline_native_skill_script_plan',
        scan=str(scan), scan_sha256=disk.digest(scan), mapping_sha256=disk.digest(mapping),
        source_sha256=disk.digest(__file__),
        exporter_sources={n: disk.digest(Path(__file__).parent/'boss_skill_bytecode_exporter'/n)
                          for n in ('Program.cs', 'PBZSkillBytecode.csproj')},
        packages=rows, batches=batches, game_started=False, installed=False,
        runtime_behavior_verified=False, all_boss_skills_complete=False)
    disk.write_new(target/'plan.json', result)
    return result


def checked_plan(target):
    target = Path(target).resolve()
    record = json.loads((target/'plan.json').read_bytes())
    if record.get('kind') != 'offline_native_skill_script_plan' or record.get('schema') != 1:
        raise ValueError('Native script plan required')
    if disk.digest(record['scan']) != record['scan_sha256']:
        raise ValueError('Source scan changed')
    for ordinal, batch in enumerate(record['batches']):
        if batch['job'] != f'job-{ordinal:04d}.json' or batch['output'] != f'batch-{ordinal:04d}':
            raise ValueError('Unexpected bounded job path')
        path = target/batch['job']
        if disk.digest(path) != batch['sha256']:
            raise ValueError('Script job changed')
        job = json.loads(path.read_bytes())
        if (job['mode'] != 'native_scripts' or job['packages'] != batch['packages']
                or not 1 <= len(job['packages']) <= 64
                or disk.digest(job['usmap']) != record['mapping_sha256']):
            raise ValueError('Script job or mapping mismatch')
    if [p for b in record['batches'] for p in b['packages']] != [r['package'] for r in record['packages']]:
        raise ValueError('Script plan coverage mismatch')
    return target, record


def checked_batch(target, batch, expected):
    directory = target/batch['output']
    receipt = directory/'result.json'
    if not receipt.is_file():
        raise ValueError('Preserve unfinished script batch')
    record = json.loads(receipt.read_bytes())
    job = json.loads((target/batch['job']).read_bytes())
    if (record.get('kind') != 'offline_native_skill_blueprint_scripts'
            or record.get('job_sha256') != batch['sha256']
            or record.get('mapping_sha256') != disk.digest(job['usmap'])
            or not re.fullmatch('[0-9a-f]{64}', record.get('tool_sha256', ''))
            or record.get('game_started') is not False or record.get('installed') is not False
            or record.get('runtime_behavior_verified') is not False
            or [r['package'] for r in record['packages']] != batch['packages']):
        raise ValueError('Script receipt source or scope mismatch')
    for row in record['packages']:
        if row.get('passed') is not True:
            continue
        name = row.get('script_file', '')
        if not re.fullmatch(r'script-[0-9]{4}\.json', name):
            raise ValueError('Bounded local script filename required')
        path = directory/name
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size == row['bytes'] <= 32*1024*1024:
            raise ValueError('Script file or size mismatch')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Script digest mismatch')
        functions = json.loads(data)
        complete = 0
        if len(functions) != row['functions'] or len(functions) != expected[row['package']]:
            raise ValueError('Declared function coverage mismatch')
        for function in functions:
            statements = function.get('statements')
            ended = bool(statements) and statements[-1]['expression'].get('Token') == 'EX_EndOfScript'
            if function.get('complete') is not ended:
                raise ValueError('Script EndOfScript mismatch')
            if ended:
                offsets = [s['offset'] for s in statements]
                if (any(type(n) is not int or n < 0 for n in offsets) or offsets != sorted(set(offsets)) or offsets[0] != 0):
                    raise ValueError('Invalid native statement offsets')
                complete += 1
        if complete != row['complete_functions'] or len(functions)-complete != row['unresolved_functions']:
            raise ValueError('Script decoding coverage mismatch')
    if record['passed'] is not all(r.get('passed') is True for r in record['packages']):
        raise ValueError('Script receipt completion mismatch')
    return record['packages']


def summarize(target):
    target, record = checked_plan(target)
    expected = {r['package']: r['functions'] for r in record['packages']}
    rows, pending = [], 0
    for batch in record['batches']:
        if not (target/batch['output']).exists():
            pending += len(batch['packages'])
            continue
        rows.extend(checked_batch(target, batch, expected))
    good = [r for r in rows if r.get('passed') is True]
    return dict(schema=1, kind='offline_native_skill_script_summary',
        plan_sha256=disk.digest(target/'plan.json'), requested=len(expected), extracted=len(good),
        failed=len(rows)-len(good), pending=pending,
        declared_functions=sum(expected.values()), extracted_functions=sum(r['functions'] for r in good),
        complete_functions=sum(r['complete_functions'] for r in good),
        unresolved_functions=sum(r['unresolved_functions'] for r in good),
        all_functions_decoded=not pending and len(good)==len(expected) and all(not r['unresolved_functions'] for r in good),
        game_started=False, installed=False, runtime_behavior_verified=False, all_boss_skills_complete=False)


def run(target, exporter, paks, crypto, limit=None):
    target, record = checked_plan(target)
    exporter, paks, crypto = Path(exporter).resolve(), Path(paks).resolve(), Path(crypto).resolve()
    if (not exporter.is_file() or not paks.is_dir() or not crypto.is_file()
            or target == paks or paks in target.parents):
        raise ValueError('Existing local inputs and separate output required')
    expected = {r['package']: r['functions'] for r in record['packages']}
    executed = 0
    for batch in record['batches']:
        directory = target/batch['output']
        if directory.exists():
            rows = checked_batch(target, batch, expected)
            if not all(r.get('passed') is True for r in rows):
                raise ValueError('Preserve failed script batch; no automatic retry')
            continue
        if limit is not None and executed >= limit:
            break
        with (target/(batch['output']+'.log')).open('x', encoding='utf-8') as log:
            result = subprocess.run(['dotnet', str(exporter), str(paks), str(crypto),
                str(target/batch['job']), str(directory)], stdout=log, stderr=subprocess.STDOUT, timeout=240)
        rows = checked_batch(target, batch, expected)
        print(json.dumps(dict(batch=batch['output'], packages=len(rows),
                             passed=result.returncode==0 and all(r.get('passed') is True for r in rows))), flush=True)
        if result.returncode or not all(r.get('passed') is True for r in rows):
            raise ValueError('Script extraction failed; local diagnostics preserved')
        executed += 1
    return summarize(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    create = commands.add_parser('plan')
    for name in ('scan', 'mapping', 'target'):
        create.add_argument('--'+name, type=Path, required=True)
    execute = commands.add_parser('run')
    execute.add_argument('target', type=Path)
    for name in ('exporter', 'paks', 'crypto'):
        execute.add_argument('--'+name, type=Path, required=True)
    execute.add_argument('--limit', type=int)
    inspect = commands.add_parser('summarize')
    inspect.add_argument('target', type=Path)
    inspect.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'plan':
        result = plan(args.scan, args.mapping, args.target)
        print(json.dumps(dict(packages=len(result['packages']), functions=sum(r['functions'] for r in result['packages']),
                              batches=len(result['batches']), game_started=False)))
    elif args.action == 'run':
        if args.limit is not None and args.limit < 1:
            parser.error('--limit must be positive')
        print(json.dumps(run(args.target, args.exporter, args.paks, args.crypto, args.limit)))
    else:
        result = summarize(args.target)
        if args.output:
            disk.write_new(args.output, result)
        print(json.dumps(result))


if __name__ == '__main__':
    main()
