"""Export and index editable source clips referenced by Boss skill timelines."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import struct
import subprocess

from boss_catalog_database import DATABASE, connect_readonly, encode
from boss_disk_declarations import digest, write_new
from boss_disk_dependencies import native_package
from boss_asset_extensions import CHARACTER_GROUPS
from research_storage import PROJECT_STORAGE


QUERY = '''
WITH RECURSIVE reachable(folder,package,ordinal) AS (
    SELECT DISTINCT s.folder,l.package,l.export_index FROM skills s
    JOIN skill_animation_links l ON l.owner=s.timeline_owner
    WHERE s.folder<>'native_support' AND l.package IS NOT NULL
    UNION
    SELECT r.folder,d.target_package,d.target_index FROM reachable r
    JOIN boss_animation_dependencies d ON d.source_package=r.package AND d.source_index=r.ordinal
    WHERE d.target_package IS NOT NULL
)
SELECT r.folder,a.package,a.export_index,a.name,a.declaration_sha256
FROM reachable r JOIN boss_native_animation a ON a.package=r.package AND a.export_index=r.ordinal
WHERE a.export_type='AnimSequence'
ORDER BY r.folder='888_UltimateBoss' DESC,r.folder,a.package,a.export_index
'''
ACTOR_QUERY = '''
SELECT DISTINCT b.folder,a.package,a.export_index,a.name,a.declaration_sha256
FROM boss_actor_animations x JOIN boss_native_actors b USING (class_path)
JOIN boss_native_animation a USING (package,export_index)
WHERE x.export_type='AnimSequence'
ORDER BY b.folder='888_UltimateBoss' DESC,b.folder,a.package,a.export_index
'''
CATALOG_QUERY = '''
SELECT NULL,package,export_index,name,declaration_sha256 FROM boss_native_animation
WHERE export_type='AnimSequence' ORDER BY package,export_index
'''


def boss_sequence_package(package):
    mount = native_package(package).casefold()
    if mount.startswith('/pbzcombatasset/actordata/mobs/'):
        return True
    parts = mount.strip('/').split('/')
    return len(parts) > 4 and parts[:2] == ['huashira', 'characters'] and parts[2] in CHARACTER_GROUPS


def clips(db, scope='skills'):
    queries = {'skills': QUERY, 'actor': ACTOR_QUERY, 'catalog': CATALOG_QUERY}
    prior = {'skills': (), 'actor': ('skills',), 'catalog': ('skills', 'actor')}
    if scope not in queries:
        raise ValueError('Unknown animation source scope')
    excluded = {row['package'] for previous in prior[scope] for row in clips(db, previous)}
    indexed = {}
    for folder, package, ordinal, name, sha in db.execute(queries[scope]):
        if package in excluded or (scope == 'catalog' and not boss_sequence_package(package)):
            continue
        entry = indexed.setdefault(package, dict(package=package, export_index=ordinal, name=name,
                                                declaration_sha256=sha, folders=[]))
        if (entry['export_index'], entry['name'], entry['declaration_sha256']) != (ordinal, name, sha):
            raise ValueError(f'Expected one exact skill clip in {package}')
        if folder is not None:
            entry['folders'].append(folder)
    return list(indexed.values())


def prepare(database, target, mapping, exporter, batch_size=24, scope='skills'):
    with closing(connect_readonly(database)) as db:
        entries = clips(db, scope)
    if not entries or not 1 <= batch_size <= 64:
        raise ValueError('Nonempty native clip list and bounded batch size required')
    target.mkdir(parents=True, exist_ok=False)
    batches = []
    for offset in range(0, len(entries), batch_size):
        name = f'batch-{len(batches):04d}'
        job = target / (name + '.json')
        packages = [entry['package'] for entry in entries[offset:offset + batch_size]]
        write_new(job, dict(mode='export', game='GAME_UE5_7', usmap=str(mapping.resolve()),
                            mesh_format='USD', export_materials=False, packages=packages))
        batches.append(dict(name=name, job_sha256=digest(job), packages=packages))
    write_new(target / 'plan.json', dict(schema=1, scope=scope, mapping_sha256=digest(mapping), exporter_sha256=digest(exporter),
                                         clips=entries, batches=batches))
    return len(entries), len(batches)


def inspect_batch(target, batch, plan):
    output = target / batch['name']
    path = output / 'conversion-result.json'
    report = json.loads(path.read_bytes())
    if (report['mode'] != 'export' or report['game_started'] is not False
            or report['input_job_sha256'] != batch['job_sha256'] or report['tool_sha256'] != plan['exporter_sha256']
            or report['mapping_sha256'] != plan['mapping_sha256']
            or [row['package'] for row in report['packages']] != batch['packages']):
        raise ValueError(f'Animation export receipt mismatch: {path}')
    return output, report['packages']


def inspect_usda(path):
    digestor = hashlib.sha256()
    markers = (re.compile(rb'def SkelAnimation\s+"'),
               re.compile(rb'translations\.timeSamples = \{\s*[\d.eE+-]+:\s*\[\('),
               re.compile(rb'rotations\.timeSamples = \{\s*[\d.eE+-]+:\s*\[\('))
    missing = set(markers)
    size = 0
    tail = b''
    with path.open('rb') as stream:
        while block := stream.read(1 << 20):
            if not size and not block.startswith(b'#usda 1.0'):
                raise ValueError(f'Invalid USDA header: {path}')
            size += len(block)
            digestor.update(block)
            joined = tail + block
            missing = {marker for marker in missing if not marker.search(joined)}
            tail = joined[-128:]
    if missing or not tail.rstrip().endswith(b'}'):
        raise ValueError(f'Incomplete skeletal animation samples: {path}')
    return digestor.hexdigest(), size


def inspect_psa(path):
    width_by_name = {b'ANIMHEAD': 0, b'BONENAMES': 120, b'ANIMINFO': 168, b'ANIMKEYS': 32, b'SCALEKEYS': 16}
    chunks = {}
    size = path.stat().st_size
    with path.open('rb') as stream:
        while stream.tell() < size:
            raw = stream.read(32)
            if len(raw) != 32:
                raise ValueError(f'Truncated PSA chunk header: {path}')
            name, _, width, count = struct.unpack('<20siii', raw)
            name = name.rstrip(b'\0')
            if (name in chunks or width_by_name.get(name) != width or count < 0
                    or stream.tell() + width * count > size):
                raise ValueError(f'Invalid PSA chunk: {path}')
            chunks[name] = count
            stream.seek(width * count, 1)
    if (not chunks or next(iter(chunks)) != b'ANIMHEAD' or chunks.get(b'ANIMINFO') != 1
            or not chunks.get(b'BONENAMES') or chunks.get(b'ANIMKEYS', 0) < chunks[b'BONENAMES']
            or chunks[b'ANIMKEYS'] % chunks[b'BONENAMES']):
        raise ValueError(f'Missing PSA skeleton or animation samples: {path}')
    return digest(path), size


def recover_batch(target, batch, plan, failed, invoke=None):
    name = batch['name'] + '-actorx'
    job = target / (name + '.json')
    output = target / name
    request = json.loads((target / (batch['name'] + '.json')).read_bytes())
    request.update(mesh_format='ActorX', packages=failed)
    if not job.exists() and invoke is not None:
        write_new(job, request)
    if not job.exists():
        return {}
    if json.loads(job.read_bytes()) != request:
        raise ValueError(f'Fallback job does not match the failed USDA requests: {job}')
    if not output.exists() and invoke is not None:
        invoke(name, job, output)
    directory, rows = inspect_batch(target, dict(name=name, job_sha256=digest(job), packages=failed), plan)
    return {row['package']: (directory, row) for row in rows}


def run(target, exporter, paks, crypto, workers=3):
    plan = json.loads((target / 'plan.json').read_bytes())
    if digest(exporter) != plan['exporter_sha256'] or not 1 <= workers <= 4:
        raise ValueError('Exact animation exporter and bounded worker count required')

    def invoke(name, job, output):
        with (target / (name + '.log')).open('xb') as log:
            result = subprocess.run(['dotnet', str(exporter), str(paks), str(crypto), str(job), str(output)],
                                    stdout=log, stderr=subprocess.STDOUT, timeout=300)
        if result.returncode not in (0, 1):
            raise ValueError(f'Animation exporter did not finish: {name}')

    def export(batch):
        job = target / (batch['name'] + '.json')
        if digest(job) != batch['job_sha256']:
            raise ValueError(f'Animation job changed: {job}')
        output = target / batch['name']
        if not output.exists():
            invoke(batch['name'], job, output)
        _, rows = inspect_batch(target, batch, plan)
        failed = [row['package'] for row in rows if row['passed'] is not True]
        recovered = recover_batch(target, batch, plan, failed, invoke) if failed else {}
        return len(rows), len(rows) - len(failed) + sum(row['passed'] is True for _, row in recovered.values())

    total = passed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for number, (count, successful) in enumerate(pool.map(export, plan['batches']), 1):
            total += count
            passed += successful
            if number % 10 == 0 or number == len(plan['batches']):
                print(json.dumps(dict(batches=number, checked=total, exported=passed)), flush=True)
    return dict(checked=total, exported=passed)


def load_records(db, target):
    plan = json.loads((target / 'plan.json').read_bytes())
    scope = plan.get('scope', 'skills')
    if clips(db, scope) != plan['clips']:
        raise ValueError('Animation plan does not match the current native references')
    wanted = {item['package']: item for item in plan['clips']}
    records = {}
    for batch in plan['batches']:
        output, rows = inspect_batch(target, batch, plan)
        failed = [row['package'] for row in rows if row['passed'] is not True]
        recovered = recover_batch(target, batch, plan, failed) if failed else {}
        for row in rows:
            entry = wanted[row['package']]
            ordinal, name = entry['export_index'], entry['name']
            directory = output
            suffix, inspect = '.usda', inspect_usda
            if row['package'] in recovered:
                directory, row = recovered[row['package']]
                suffix, inspect = '.psa', inspect_psa
            exports = row.get('exports')
            if (row['package'] in records or (exports is not None and
                    (ordinal >= len(exports) or exports[ordinal] != {'type': 'AnimSequence', 'name': name}))):
                raise ValueError(f'Unexpected exported clip: {row["package"]}')
            item = dict(entry, status='export_failed', path=None, sha256=None, size=None, scope=scope)
            if row['passed'] is True:
                if exports is None:
                    raise ValueError(f'Missing exact export list: {row["package"]}')
                candidates = [Path(x).resolve() for x in row['files'] if Path(x).suffix.lower() == suffix]
                if len(candidates) != 1:
                    raise ValueError(f'One {suffix} source expected: {row["package"]}')
                path, = candidates
                if not path.is_relative_to(directory.resolve()):
                    raise ValueError(f'Animation output escaped its batch: {path}')
                sha, size = inspect(path)
                item.update(status='exported', path=str(path), sha256=sha, size=size, format=suffix[1:])
            else:
                item['error_type'] = row.get('error_type')
            records[row['package']] = item
    if records.keys() != wanted.keys():
        raise ValueError('Batch receipts do not cover every clip in the plan')
    return records


def summary(db):
    return dict(db.execute('SELECT status,count(*) FROM boss_editable_clips GROUP BY status'))


def populate(db, records, paths):
    for scope, entries in records.items():
        current = {row['package']: row for row in clips(db, scope)}
        if (current.keys() != entries.keys() or any(row['declaration_sha256'] != current[p]['declaration_sha256']
                                                  for p, row in entries.items())):
            raise ValueError('Native animation references changed during indexing')
    db.execute('''CREATE TABLE IF NOT EXISTS boss_editable_clips (
        package TEXT PRIMARY KEY, export_index INTEGER NOT NULL, scope TEXT NOT NULL, status TEXT NOT NULL,
        payload TEXT NOT NULL) WITHOUT ROWID''')
    for scope, entries in records.items():
        db.execute('DELETE FROM boss_editable_clips WHERE scope=?', (scope,))
        db.executemany('INSERT INTO boss_editable_clips VALUES (?,?,?,?,?)', (
            (p, r['export_index'], scope, r['status'], encode(r)) for p, r in entries.items()))
    row = db.execute("SELECT value FROM metadata WHERE key='boss_editable_clip_plans'").fetchone()
    sources = json.loads(row[0]) if row else {}
    sources.update({scope: dict(path=str(path), sha256=digest(path / 'plan.json')) for scope, path in paths.items()})
    db.execute("INSERT OR REPLACE INTO metadata VALUES ('boss_editable_clip_plans',?)", (encode(sources),))
    result = summary(db)
    db.execute("INSERT OR REPLACE INTO metadata VALUES ('boss_editable_clip_counts',?)", (encode(result),))
    return result


def index(database, target):
    plan = json.loads((target / 'plan.json').read_bytes())
    scope = plan.get('scope', 'skills')
    with closing(connect_readonly(database)) as db:
        records = load_records(db, target)
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=rw', uri=True)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        return populate(db, {scope: records}, {scope: target})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run', 'index'))
    parser.add_argument('target', type=Path)
    for option in ('mapping', 'exporter', 'paks', 'crypto'):
        parser.add_argument('--' + option, type=Path)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--scope', choices=('skills', 'actor', 'catalog'), default='skills')
    args = parser.parse_args()
    args.target = args.target.resolve()
    database = PROJECT_STORAGE / DATABASE
    if args.action == 'prepare' and args.mapping and args.exporter:
        result = prepare(database, args.target, args.mapping, args.exporter, scope=args.scope)
    elif args.action == 'run' and args.exporter and args.paks and args.crypto:
        result = run(args.target, args.exporter, args.paks, args.crypto, args.workers)
    elif args.action == 'index':
        result = index(database, args.target)
    else:
        parser.error('Missing local inputs for this action')
    print(json.dumps(result, ensure_ascii=False))
