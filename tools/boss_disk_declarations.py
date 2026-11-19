"""Plan and reconcile bounded offline Boss declarations; never promote live grants.

Raw game properties stay in the local E-drive project. The existing closed
research receipts remain the authority for grants, execution and player access.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

FOLDER = re.compile(r'^ProjectPBZ/Plugins/Secret/PBZCombatAsset/Content/ActorData/Mobs/([0-9]{3}_[A-Za-z0-9_]+)/(.+)\.uasset$')
MAX_BYTES = 16 * 1024 * 1024


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def selected_packages(index):
    """Use exact index paths, including nested skill data; names are only clues."""
    found = {}
    with Path(index).open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream, skipinitialspace=True):
            name = row.get('Filename', '').strip()
            if not name.startswith('../../../'):
                continue
            path = name[len('../../../'):]
            if '\\' in path or ':' in path or '..' in PurePosixPath(path).parts:
                continue
            match = FOLDER.fullmatch(path)
            if not match:
                continue
            folder, relative = match.groups()
            parts = relative.casefold().split('/')
            leaf = parts[-1]
            if not (set(parts[:-1]) & {'ability', 'abilities'}
                    or leaf.startswith(('ga_', 'actorc_', 'bp_monster_'))):
                continue
            if row.get('ChunkType', '').strip() != 'ExportBundleData':
                continue
            item = dict(package=path, folder=folder, package_hash=row.get('Hash', '').strip())
            if path in found and found[path] != item:
                raise ValueError('Conflicting package index entry: ' + path)
            found[path] = item
    priority = {'042_AHua':0, '057_WanJun':1, '056_YouLong':2, '073_YanQianSui':3,
                '058_MadDoctor':4, '071_XianZhe':5, '044_PengMeng':6, '054_ZuoShang':7,
                '066_RenTuZi':8, '067_MoTian':9}
    return sorted(found.values(), key=lambda row:(priority.get(row['folder'],10),row['package']))


def plan(index, mapping, target):
    target, mapping = Path(target), Path(mapping).resolve()
    rows = selected_packages(index)
    if not rows:
        raise ValueError('No indexed Boss declaration candidates')
    if not mapping.is_file():
        raise ValueError('Exact local mapping required')
    target.mkdir(parents=True, exist_ok=False)
    batches = []
    for offset in range(0, len(rows), 64):
        filename = f'job-{offset // 64:04d}.json'
        packages = [row['package'] for row in rows[offset:offset+64]]
        write_new(target / filename, dict(mode='declarations', game='GAME_UE5_7',
                  usmap=str(mapping), packages=packages))
        batches.append(dict(job=filename, sha256=digest(target/filename), packages=packages,
                            output=f'batch-{offset // 64:04d}'))
    result = dict(schema=1, kind='offline_boss_disk_declarations',
        index_sha256=digest(index), mapping_sha256=digest(mapping),
        packages=rows, batches=batches,
        folders=dict(sorted(Counter(row['folder'] for row in rows).items())),
        disk_metadata_only=True, complete_package_inventory=False,
        live_grant_verified=False, execution_verified=False, playable=False,
        game_started=False, installed=False)
    write_new(target/'plan.json', result)
    return result


def checked_batch(target, batch):
    """Match exact requested paths and every declaration digest before reuse."""
    directory = target / batch['output']
    if not (directory/'conversion-result.json').is_file():
        raise ValueError('Preserve unfinished declaration batch; no completed receipt: '+batch['output'])
    report = json.loads((directory/'conversion-result.json').read_bytes())
    if report['mode'] != 'declarations' or report['game_started'] is not False:
        raise ValueError('Unexpected declaration receipt')
    job = json.loads((target/batch['job']).read_bytes())
    if report.get('input_job_sha256') != batch['sha256'] or report.get('mapping_sha256') != digest(job['usmap']):
        raise ValueError('Declaration receipt source job/mapping mismatch')
    if not re.fullmatch(r'[0-9a-f]{64}',report.get('tool_sha256','')):
        raise ValueError('Declaration exporter identity missing')
    rows = report['packages']
    if [row['package'] for row in rows] != batch['packages']:
        raise ValueError('Declaration receipt does not match exact job order')
    for row in rows:
        if row.get('passed') is not True:
            continue
        name = row['declaration_file']
        if not re.fullmatch(r'declaration-[0-9]{4}\.json', name):
            raise ValueError('Unexpected declaration filename')
        path = directory/name
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
            raise ValueError('Invalid bounded declaration file')
        if digest(path) != row['declaration_sha256'] or path.stat().st_size != row['declaration_bytes']:
            raise ValueError('Declaration digest/size mismatch')
    if report['passed'] is not all(row.get('passed') is True for row in rows):
        raise ValueError('Declaration completion status mismatch')
    return rows


def checked_plan(target):
    target = Path(target).resolve()
    record = json.loads((target/'plan.json').read_bytes())
    if record['kind'] != 'offline_boss_disk_declarations' or record['schema'] != 1:
        raise ValueError('Unexpected plan')
    for ordinal, batch in enumerate(record['batches']):
        if batch['job'] != f'job-{ordinal:04d}.json' or batch['output'] != f'batch-{ordinal:04d}':
            raise ValueError('Unexpected job/output path')
        path = target/batch['job']
        if digest(path) != batch['sha256']:
            raise ValueError('Frozen declaration job changed')
        job = json.loads(path.read_bytes())
        if job['mode'] != 'declarations' or job['packages'] != batch['packages'] or not 1 <= len(job['packages']) <= 64:
            raise ValueError('Unexpected bounded declaration job')
        if digest(job['usmap']) != record['mapping_sha256']:
            raise ValueError('Exact mapping changed')
    if [p for b in record['batches'] for p in b['packages']] != [r['package'] for r in record['packages']]:
        raise ValueError('Declaration plan coverage mismatch')
    return target, record


def run(target, exporter, paks, crypto, limit=None):
    """Resume only untouched batches; preserve any failure for explicit review."""
    target, record = checked_plan(target)
    exporter, paks, crypto = Path(exporter).resolve(), Path(paks).resolve(), Path(crypto).resolve()
    if not exporter.is_file() or not paks.is_dir() or not crypto.is_file():
        raise ValueError('Existing local exporter, packages and private crypto file required')
    if target == paks or paks in target.parents:
        raise ValueError('Output must be outside game packages')
    executed = 0
    for batch in record['batches']:
        directory = target/batch['output']
        if directory.exists():
            rows = checked_batch(target, batch)
            if not all(r.get('passed') is True for r in rows):
                raise ValueError('Preserve failed declaration batch; review before preparing a new plan')
            continue
        if limit is not None and executed >= limit:
            break
        command = ['dotnet', str(exporter), str(paks), str(crypto), str(target/batch['job']), str(directory)]
        directory.mkdir()
        # Keep native diagnostics local; never echo command lines or key data.
        with (target/(batch['output']+'.log')).open('x', encoding='utf-8') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        rows = checked_batch(target, batch)
        print(json.dumps(dict(batch=batch['output'], packages=len(rows),
                         passed=result.returncode == 0 and all(r['passed'] for r in rows))), flush=True)
        if result.returncode or not all(r['passed'] for r in rows):
            raise ValueError('Offline declaration batch failed; original logs preserved locally')
        executed += 1
    return summarize(target)


def summarize(target):
    target, record = checked_plan(target)
    indexed = {r['package']: r for r in record['packages']}
    rows, pending, exporters, incomplete = [], [], set(), []
    for batch in record['batches']:
        if not (target/batch['output']).exists():
            pending.extend(batch['packages'])
            continue
        if not (target/batch['output']/'conversion-result.json').is_file():
            pending.extend(batch['packages'])
            incomplete.append(batch['output'])
            continue
        for item in checked_batch(target, batch):
            row = dict(package=item['package'], folder=indexed[item['package']]['folder'],
                       passed=item['passed'], live_grant_verified=False, execution_verified=False)
            if item['passed']:
                declaration = target/batch['output']/item['declaration_file']
                objects = json.loads(declaration.read_bytes())
                if not isinstance(objects, list) or not objects:
                    raise ValueError('Nonempty serialized object list required')
                row.update(declaration=str(declaration.relative_to(target)),
                           declaration_sha256=item['declaration_sha256'],
                           exports=item['exports'], serialized_objects=len(objects))
            rows.append(row)
        report=json.loads((target/batch['output']/'conversion-result.json').read_bytes())
        exporters.add(report['tool_sha256'])
    return dict(schema=1, plan_sha256=digest(target/'plan.json'), requested=len(indexed),
        extracted=sum(r['passed'] for r in rows), failed=sum(not r['passed'] for r in rows),
        pending=len(pending), packages=rows,
        incomplete_batches=incomplete,
        exporter_sha256=sorted(exporters),
        extracted_by_folder=dict(sorted(Counter(r['folder'] for r in rows if r['passed']).items())),
        disk_metadata_only=True, complete_package_inventory=False,
        live_grant_verified=False, execution_verified=False, playable=False,
        game_started=False, installed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    create = commands.add_parser('plan')
    create.add_argument('--index', type=Path, required=True)
    create.add_argument('--mapping', type=Path, required=True)
    create.add_argument('--target', type=Path, required=True)
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
        result = plan(args.index, args.mapping, args.target)
        print(json.dumps(dict(packages=len(result['packages']), batches=len(result['batches']),
                         folders=result['folders'], game_started=False), ensure_ascii=False))
    else:
        if args.action == 'run':
            if args.limit is not None and args.limit < 1:
                parser.error('--limit must be positive')
            result = run(args.target, args.exporter, args.paks, args.crypto, args.limit)
        else:
            result = summarize(args.target)
            if args.output:
                write_new(args.output, result)
        print(json.dumps({k:v for k,v in result.items() if k != 'packages'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
