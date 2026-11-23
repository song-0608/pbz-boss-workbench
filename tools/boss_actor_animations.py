"""Record each Boss body's animation references and reachable native clips."""
from collections import defaultdict
from contextlib import closing
from functools import lru_cache
import json
import sqlite3

from boss_catalog_assets import animation_refs
from boss_catalog_database import DATABASE, connect_readonly, encode
from boss_disk_dependencies import native_package
from build_boss_disk_repertoire import read_verified
from research_storage import PROJECT_STORAGE


def identity(ref):
    mount, ordinal, kind, name = ref
    return mount.casefold(), ordinal, kind, name.rsplit(':', 1)[-1]


def graph(db):
    records = {}
    for package, ordinal, name, kind, declaration, sha in db.execute('''
        SELECT package,export_index,name,export_type,declaration,declaration_sha256 FROM boss_native_animation'''):
        records[identity((native_package(package), ordinal, kind, name))] = (package, declaration, sha)

    @lru_cache(maxsize=None)
    def children(declaration, sha):
        return {identity(ref) for ref in animation_refs(read_verified(declaration, sha))}

    roots = defaultdict(set)
    for actor, raw in db.execute("SELECT class_path,payload FROM boss_actor_control WHERE domain IN ('character','movement')"):
        roots[actor].update(identity(ref) for ref in animation_refs(json.loads(raw)))

    related, gaps = [], []
    for actor, references in sorted(roots.items()):
        queue, seen = list(references), set()
        while queue:
            key = queue.pop()
            if key in seen:
                continue
            seen.add(key)
            _, ordinal, kind, _ = key
            if key not in records:
                gaps.append((actor, *key))
                continue
            package, declaration, sha = records[key]
            related.append((actor, package, ordinal, kind, int(key in references)))
            if kind not in ('AnimSequence', 'Skeleton'):
                queue.extend(children(declaration, sha) - seen)
    return sorted(related), sorted(gaps)


def populate(db):
    related, gaps = graph(db)
    db.execute('''CREATE TABLE IF NOT EXISTS boss_actor_animations (
        class_path TEXT NOT NULL, package TEXT NOT NULL, export_index INTEGER NOT NULL,
        export_type TEXT NOT NULL, directly_declared INTEGER NOT NULL,
        PRIMARY KEY (class_path,package,export_index)) WITHOUT ROWID''')
    db.execute('''CREATE TABLE IF NOT EXISTS boss_actor_animation_gaps (
        class_path TEXT NOT NULL, mount TEXT NOT NULL, export_index INTEGER NOT NULL,
        export_type TEXT NOT NULL, name TEXT NOT NULL,
        PRIMARY KEY (class_path,mount,export_index,export_type,name)) WITHOUT ROWID''')
    db.execute('DELETE FROM boss_actor_animations')
    db.execute('DELETE FROM boss_actor_animation_gaps')
    db.executemany('INSERT INTO boss_actor_animations VALUES (?,?,?,?,?)', related)
    db.executemany('INSERT INTO boss_actor_animation_gaps VALUES (?,?,?,?,?)', gaps)
    result = summary(db)
    db.execute("INSERT OR REPLACE INTO metadata VALUES ('boss_actor_animation_counts',?)", (encode(result),))
    return result


def summary(db):
    count, actors, clips = db.execute('''SELECT count(*),count(DISTINCT class_path),
        count(DISTINCT CASE WHEN export_type='AnimSequence' THEN package END) FROM boss_actor_animations''').fetchone()
    gaps, = db.execute('SELECT count(*) FROM boss_actor_animation_gaps').fetchone()
    return dict(relationships=count, actor_variants=actors, clip_packages=clips, unresolved=gaps)


if __name__ == '__main__':
    path = PROJECT_STORAGE / DATABASE
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        print(json.dumps(populate(db), ensure_ascii=False))
