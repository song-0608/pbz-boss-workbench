import json
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_boss_capture import combat_body_coverage, configuration_gaps


class CombatBodyCoverageTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE boss_group_coverage (folder, body_status, config_exports, actor_count);
            CREATE TABLE skills (folder, class_path);
            INSERT INTO boss_group_coverage VALUES ('legacy', 'no_serialized_body_or_config', 0, 0);
            INSERT INTO skills VALUES ('legacy', '/Game/Shot.Shot_C');
        """)
        self.encounter = dict(ability_folder='legacy', ability_class='/Game/Shot.Shot_C',
                              actor=dict(config_path='/Game/NewActor.NewActor'))

    def test_all_skills_have_a_verified_encounter_body(self):
        missing, shared = combat_body_coverage(self.db, [self.encounter], [])
        self.assertEqual(missing, [])
        self.assertEqual(shared[0]['skill_classes'], ['/Game/Shot.Shot_C'])

    def test_keeps_the_gap_with_an_unlinked_skill_or_separate_config(self):
        self.db.execute("INSERT INTO skills VALUES ('legacy', '/Game/Other.Other_C')")
        self.assertEqual(len(combat_body_coverage(self.db, [self.encounter], [])[0]), 1)
        self.db.execute("DELETE FROM skills WHERE class_path='/Game/Other.Other_C'")
        self.db.execute("UPDATE boss_group_coverage SET config_exports=1")
        self.assertEqual(len(combat_body_coverage(self.db, [self.encounter], [])[0]), 1)

    def test_requires_actor_configuration_and_preserves_quarantines(self):
        self.assertEqual(len(combat_body_coverage(self.db, [self.encounter], [dict(folder='legacy')])[0]), 1)
        self.encounter['actor']['config_path'] = None
        self.assertEqual(len(combat_body_coverage(self.db, [self.encounter], [])[0]), 1)


class ConfigurationGapTests(unittest.TestCase):
    def test_dynamic_markers_and_closed_cycles_keep_actual_gaps_visible(self):
        with sqlite3.connect(':memory:') as db:
            self.addCleanup(db.close)
            db.executescript('''
                CREATE TABLE boss_config_strategy_selectors
                    (config_path, tree_path, export_index, source_sha256, mode, payload);
                CREATE TABLE boss_combat_config_index (config_path, diagnostics);
            ''')
            selector = dict(mode='dynamic_subtree', injection_tag='AI.Tag', strategy_path='/Game/Strategy.Strategy')
            for ordinal, payload in enumerate((selector, dict(selector, configured={'ObjectName': 'Verified'}))):
                db.execute('INSERT INTO boss_config_strategy_selectors VALUES (?, ?, ?, ?, ?, ?)',
                           ('Config', 'Tree', ordinal, 'sha', 'dynamic_subtree', json.dumps(dict(selector=payload))))
            db.execute('INSERT INTO boss_combat_config_index VALUES (?, ?)', ('Config', json.dumps([
                dict(source='Tree', reason='dynamic_subtree_selection'),
                dict(source='UnknownTree', reason='dynamic_subtree_selection'),
                dict(source='Strategy', reason='strategy_tree_cycle_or_depth_limit', cycle=['A', 'B', 'A']),
                dict(source='Strategy', reason='strategy_tree_cycle_or_depth_limit'),
                dict(source='Pool', reason='authored_null_subpool_slot'),
            ])))
            missing, authored, unresolved = configuration_gaps(db)
            self.assertEqual(missing, [dict(config_path='Config', tree_path='Tree', export_index=0,
                                            tree_sha256='sha', **selector)])
            self.assertEqual(len(authored), 3)
            self.assertEqual([row['source'] for row in unresolved], ['UnknownTree', 'Strategy'])
