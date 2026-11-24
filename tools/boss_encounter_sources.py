"""Associate an authored encounter's actor, behavior tree, and abilities offline."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from boss_catalog_database import APPLICATION_ID, DATABASE, VERSION, encode
from boss_disk_dependencies import native_package
from build_boss_disk_combo_index import ordered_nodes, split_reference
from build_boss_disk_repertoire import read_verified
from research_storage import PROJECT_STORAGE


def single(rows, label):
    values = list(rows)
    if len(values) != 1:
        raise ValueError(f'Expected exactly one {label}, got {len(values)}')
    return values[0]


def source_from_receipt(receipt_path, state_index):
    receipt = json.loads(receipt_path.read_bytes())
    row = single(receipt['packages'], 'map package')
    if (receipt['passed'] is not True or receipt['mode'] != 'declarations'
            or receipt['game_started'] is not False or row['passed'] is not True
            or not row['package'].endswith('.umap')
            or Path(row['declaration_file']).name != row['declaration_file']):
        raise ValueError('A verified offline map declaration is required')
    return dict(map_package=row['package'], state_index=state_index,
                declaration=str(receipt_path.parent / row['declaration_file']),
                declaration_sha256=row['declaration_sha256'])


def map_reference(ref):
    kind, separator, qualified = ref['ObjectName'].partition("'")
    if not separator or not qualified.endswith("'"):
        raise ValueError('Invalid qualified map object name')
    leaf = qualified[:-1].rsplit('.', 1)[-1]
    return split_reference(dict(ref, ObjectName=f"{kind}'{leaf}'"))


def derive(db, source):
    exports = read_verified(source['declaration'], source['declaration_sha256'])
    map_package = source['map_package']
    if not map_package.startswith('ProjectPBZ/Content/') or not map_package.endswith('.umap'):
        raise ValueError('Expected an indexed ProjectPBZ map package')
    map_mount = native_package(map_package.removesuffix('.umap') + '.uasset')
    state_index = source['state_index']
    if not 0 <= state_index < len(exports):
        raise ValueError('Invalid encounter state export index')
    state = exports[state_index]
    props = state['Properties']
    outer_mount, outer_index, outer_type, outer_name = map_reference(state['Outer'])
    if outer_mount != map_mount or outer_type != 'BP_SwitchIdleStateTriggerVolume_C':
        raise ValueError('State is not owned by this map’s idle state trigger')
    trigger = exports[outer_index]
    if trigger['Type'] != outer_type or trigger['Name'] != outer_name:
        raise ValueError('Encounter trigger export type differs')

    assignments = trigger['Properties']['AIToTrigger']
    state_ref = (map_mount, state_index, state['Type'], state['Name'])
    assignment = single((row for row in assignments if
        map_reference(row['Value']['InstancedAIStateData']) == state_ref), 'spawner assignment for the encounter state')
    actor_world, _, spawner_path = assignment['Key'].partition(':')
    target = props['TargetActorSpawner']
    if (actor_world != target['AssetPathName'] or not actor_world.startswith(map_mount + '.')
            or not spawner_path.startswith('PersistentLevel.')
            or not target['SubPathString'].startswith('PersistentLevel.')):
        raise ValueError('Expected both encounter spawners in the verified map')

    def resolve_spawner(path):
        name = path.removeprefix('PersistentLevel.')
        spawner = single((obj for obj in exports if obj['Type'] == 'BP_AISpawner_C'
                          and obj['Name'] == name), 'map spawner')
        class_path = spawner['Properties']['Class']['AssetPathName']
        folder, config = single(db.execute('SELECT folder,config_path FROM boss_native_actors '
                                           'WHERE class_path=?', (class_path,)), 'catalog actor class')
        return dict(spawner=name, class_path=class_path, folder=folder, config_path=config)

    tree_ref = split_reference(props['BehaviorTreeAsset'])
    tree_mount, _, tree_type, _ = tree_ref
    if tree_type != 'BehaviorTree':
        raise ValueError('Expected a native behavior tree reference')
    from boss_config_abilities import database_capture
    capture = database_capture(db)
    tree = ordered_nodes(capture, tree_ref)
    if tree['issues']:
        raise ValueError(f"Could not verify reachable encounter tasks: {tree['issues']}")
    tree_source = capture.packages[tree_mount.casefold()]
    abilities = {task['ability'] for task in tree['nodes']
                 if task['type'] == 'BTTask_ActivateAbility' and 'ability' in task}
    ability = single(abilities, 'ability class activated by the encounter tree')
    folder, = single(db.execute('SELECT folder FROM skills WHERE class_path=?', (ability,)), 'catalog skill')
    return dict(source, actor=resolve_spawner(spawner_path), target=resolve_spawner(target['SubPathString']),
                trigger=trigger['Name'], state=state['Name'], tree_package=tree_source['package'],
                tree_sha256=tree_source['declaration_sha256'],
                ability_class=ability, ability_folder=folder, runtime_grant_verified=False)


def write(db, source):
    entry = derive(db, source)
    key = source_key(source)
    current = db.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()
    if current and json.loads(current[0]) != entry:
        raise ValueError('Encounter evidence already exists with different contents')
    db.execute('INSERT INTO metadata (key,value) VALUES (?,?) ON CONFLICT(key) DO NOTHING',
               (key, encode(entry)))
    return entry


def source_key(source):
    return f"boss_encounter_source:{source['map_package']}:{source['state_index']}"


def verified_records(db):
    records = []
    for key, value in db.execute("SELECT key,value FROM metadata WHERE key GLOB 'boss_encounter_source:*' ORDER BY key"):
        record = json.loads(value)
        source = {field: record[field] for field in ('map_package', 'state_index', 'declaration', 'declaration_sha256')}
        if key != source_key(source) or derive(db, source) != record:
            raise ValueError('Encounter association differs from the native map and behavior tree')
        records.append(record)
    return records


def verified(db):
    return [{field: record[field] for field in ('map_package', 'state_index', 'declaration', 'declaration_sha256')}
            for record in verified_records(db)]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path)
    parser.add_argument('--state-index', type=int, required=True)
    parser.add_argument('--storage', type=Path, default=PROJECT_STORAGE)
    args = parser.parse_args()
    database = (args.storage / DATABASE).resolve()
    with closing(sqlite3.connect(database.as_uri() + '?mode=rw', uri=True)) as db, db:
        if (db.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID
                or db.execute('PRAGMA user_version').fetchone()[0] != VERSION):
            raise ValueError('Unexpected Boss database format')
        db.execute('BEGIN IMMEDIATE')
        entry = write(db, source_from_receipt(args.receipt.resolve(), args.state_index))
        verified(db)
    print(json.dumps(entry, ensure_ascii=False, indent=2))
