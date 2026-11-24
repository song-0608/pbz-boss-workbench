import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from boss_mechanism_database import populate, read_export, verify_contents, verify_inventory


class MechanismDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db.executescript('''
            CREATE TABLE metadata (key,value);
            CREATE TABLE packages (package,folder,declaration,declaration_sha256);
            CREATE TABLE additional_boss_packages (package,declaration,declaration_sha256);
            CREATE TABLE native_package_exports (package,export_index,mount,name,export_type);
            CREATE TABLE additional_boss_exports (package,export_index,name,export_type);
            CREATE TABLE skills (class_path,folder,package,native_route,timeline_owner);
            CREATE TABLE capture_gaps (category,identifier,payload);
        ''')

    def freeze(self, filename, exports):
        raw = json.dumps(exports, indent=2).encode()
        file = self.root / filename
        file.write_bytes(raw)
        return str(file), hashlib.sha256(raw).hexdigest()

    def test_keeps_original_exports_map_and_quarantine_in_the_same_database(self):
        package = 'Test.uasset'
        mount = '/Game/Test'
        class_path = mount + '.GA_Test_C'
        native = dict(ObjectPath='/Script/GameplayAbilities', ObjectName="Class'GameplayAbility'")
        code = dict(Name='GA_Test_C', Type='LegoAbilityBlueprintGeneratedClass', Package=mount, Super=native,
                    Properties={'Action': None})
        tree = dict(Name='BT_Example', Type='BehaviorTree', Properties={'RootNode': {'ObjectPath': '/Game/Test.2'}})
        passive = dict(Name='BP_ExamplePassive_C', Type='BlueprintGeneratedClass', Package=mount, SuperStruct=native)
        exports = [code, tree, passive]
        asset_file, asset_sha = self.freeze('asset.json', exports)
        self.db.execute('INSERT INTO packages VALUES (?,?,?,?)', (package, 'Example', asset_file, asset_sha))
        for i, obj in enumerate(exports):
            self.db.execute('INSERT INTO native_package_exports VALUES (?,?,?,?,?)',
                            (package, i, mount, obj['Name'], obj['Type']))
        gap = dict(class_path=class_path, folder='Example', issues=['Unknown timeline slot'])
        self.db.execute('INSERT INTO capture_gaps VALUES (?,?,?)', ('quarantined', class_path, json.dumps(gap)))
        map_export = dict(Name='BP_Spawner', Type='BP_AISpawner_C')
        map_file, map_sha = self.freeze('map.json', [map_export])
        source = dict(map_package='Encounter.umap', declaration=map_file, declaration_sha256=map_sha)
        self.db.execute('INSERT INTO metadata VALUES (?,?)', ('boss_encounter_source:1', json.dumps(source)))
        populate(self.db)
        self.assertEqual(verify_contents(self.db), 2)
        self.assertEqual(read_export(self.db, package, 0), code)
        self.assertEqual(read_export(self.db, 'Encounter.umap', 0), map_export)
        self.assertEqual(verify_inventory(self.db)['skills'], {'ancestry_verified': 1, 'quarantined': 1})
        found, raw = self.db.execute('SELECT class_path,ancestry FROM boss_mechanism_ability_ancestry').fetchone()
        self.assertEqual(found, mount + '.' + passive['Name'])
        self.assertEqual(json.loads(raw), dict(chain=[native], verified_by=class_path))
        self.assertEqual(verify_inventory(self.db)['mechanism_exports'], {'behavior_tree': 1, 'encounter_flow': 1})
        with self.assertRaisesRegex(ValueError, 'Invalid export index'):
            read_export(self.db, package, -1)
        self.db.execute("UPDATE boss_mechanism_declarations SET raw_bytes=raw_bytes+1 WHERE package=?", (package,))
        with self.assertRaisesRegex(ValueError, 'differs from its digest'):
            read_export(self.db, package, 0)

    def test_rejects_changed_frozen_declaration(self):
        file, _ = self.freeze('asset.json', [dict(Name='Example', Type='BehaviorTree')])
        self.db.execute('INSERT INTO packages VALUES (?,?,?,?)', ('Test.uasset', 'Example', file, 'incorrect'))
        with self.assertRaisesRegex(ValueError, 'Frozen declaration changed'):
            populate(self.db)
