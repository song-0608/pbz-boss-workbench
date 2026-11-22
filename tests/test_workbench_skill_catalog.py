import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from contextlib import closing

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from boss_catalog_database import DATABASE, NPC_RENEWAL, build, connect_readonly, open_catalog, priorities
from workbench_skill_catalog import CAPTURE, EVIDENCE, Catalog


def write(path, value):
    raw = json.dumps(value).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


class WorkbenchSkillCatalogTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repertoire = self.root / CAPTURE / 'repertoire'
        self.combo = self.root / CAPTURE / 'combo-index-v2'
        self.capture = self.root / CAPTURE / 'convergence-verified'
        self.tree = '/Game/Test.Test'
        self.parent = '/Game/Parent.Parent_C'
        self.child = '/Game/Child.Child_C'
        self.skills = [dict(class_path=path, declared_actions=None, native_route='no_closed_native_record',
                            timeline_resolution='native_default_unobserved', timeline_owner=None,
                            activation_allowed=False, playable=False, package='Boss.uasset')
                       for path in (self.parent, self.child)]
        self.skills[0].update(timeline_owner=self.parent, declared_actions=1)
        scan = self.capture / 'scan-0001.json'
        actor_class = '/PBZCombatAsset/ActorData/Mobs/056_YouLong/BP_Monster.BP_Monster_C'
        actor_base = dict(ObjectName="BlueprintGeneratedClass'BP_RenewalNPC_C'",
                          ObjectPath=NPC_RENEWAL.rsplit('.', 1)[0] + '.4')
        config = self.root / 'ActorC_Example.json'
        config_sha = write(config, [dict(Type='PDA_ActorConfig_C', Name='ActorC_Example'),
                                    dict(Type='Condition_C', Name='Condition_Example')])
        scan_sha = write(scan, dict(packages=[
            dict(package='Boss.uasset', folder='056_YouLong', declaration='boss.json', declaration_sha256='boss',
                 references=[], parent_classes=[dict(class_path=actor_class, export_index=2,
                     export_type='BlueprintGeneratedClass', serialized_super=actor_base)]),
            dict(package='Base.uasset', folder='native_support', declaration='base.json', declaration_sha256='base',
                 references=[], parent_classes=[dict(class_path=NPC_RENEWAL, export_index=4,
                     export_type='BlueprintGeneratedClass', serialized_super=None)]),
            dict(package='ActorC_Example.uasset', folder='056_YouLong', declaration=str(config),
                 declaration_sha256=config_sha, references=[])], pending_roots=0,
            pending_dependency_count=0, declaration_contents_verified=True, failed_dependencies=[],
            deferred_dependencies=[], unindexed_references=[]))
        queue_sha = write(self.capture / 'adaptation-queue-v1.json', dict(
            disk_dependency_scan_sha256=scan_sha, rows=[dict(class_path=s['class_path'], next_action='review')
                                                      for s in self.skills]))
        workflow_sha = write(self.capture / 'result.json', dict(final_scan=str(scan), final_scan_sha256=scan_sha))
        timeline = {self.parent: dict(declaration_sha256='boss', timelines=[dict(name='Main',
            declared_end_seconds=2.5, actions=[dict(ordinal=0, action_type='ExpectedAction',
                start_seconds=1.5, duration_seconds=.25)])])}
        skill_files = {
            '056_YouLong.json': write(self.repertoire / '056_YouLong.json',
                dict(folder='056_YouLong', skills=self.skills, root_packages=1, native_routes={})),
            'native_support.json': write(self.repertoire / 'native_support.json',
                dict(folder='native_support', skills=[], root_packages=0, native_routes={})),
            'timelines.json': write(self.repertoire / 'timelines.json', timeline),
            'scripts.json': write(self.repertoire / 'scripts.json', {}),
            'root-reference-gaps.json': write(self.repertoire / 'root-reference-gaps.json', []),
            'quarantined.json': write(self.repertoire / 'quarantined.json', []),
        }
        combo_files = {
            'parents.json': write(self.combo / 'parents.json', [dict(class_path=self.parent, folder='056_YouLong',
                choices=[dict(path=self.tree, weight=100.0)], trees=[self.tree], issues=[], activation_allowed=False,
                referenced_abilities=[{'class_path': self.child}])]),
            'trees.json': write(self.combo / 'trees.json', {self.tree: {'nodes': [dict(
                branch=[0], name='Strike', type='BTTask_ActivateAbility', decorators=[], ability=self.child,
                properties={'AbilityActivationMethod': 'EAIAbilityActivationMethod::ByTactic'})]}}),
        }
        common = dict(scan_sha256=scan_sha, queue_sha256=queue_sha, game_started=False, installed=False,
                      activation_allowed=False)
        repertoire_sha = write(self.repertoire / 'summary.json', dict(common, kind='offline_boss_disk_repertoire',
            folders=1, files=skill_files, workflow_sha256=workflow_sha, ability_classes=2, quarantined=0,
            script_packages=0, function_exports=0))
        combo_sha = write(self.combo / 'summary.json', dict(common, kind='offline_boss_combo_tree_index',
                                                            parents=1, trees=1, files=combo_files))
        write(self.root / EVIDENCE / 'native-boss-skill-repertoire-milestone-20261121.json',
              {'catalog_summary_sha256': repertoire_sha})
        write(self.root / EVIDENCE / 'native-boss-disk-combo-expansion-20261122.json',
              {'expanded_summary_sha256': combo_sha})

    def test_role_and_combo_details_join_with_tactic_selection_and_reverse_lookup(self):
        catalog = Catalog(self.root, self.root)
        self.assertEqual(catalog.folders, ('056_YouLong', 'native_support'))
        parent, child = catalog.role('056_YouLong')['skills']
        self.assertIsNone(catalog.trees)
        self.assertIn('Child_C（按战术标签选招）', catalog.details(parent))
        self.assertIn('引用这项技能的连招\nParent_C', catalog.details(child))
        with self.assertRaisesRegex(ValueError, '未知原生资源分组'):
            catalog.role('../combo-index-v2')

    def test_changed_role_or_tree_file_does_not_display_unverified_content(self):
        catalog = Catalog(self.root, self.root)
        write(self.repertoire / '056_YouLong.json', {'folder': 'wrong', 'skills': []})
        write(self.combo / 'trees.json', {})
        with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
            catalog.role('056_YouLong')
        with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
            catalog.details(self.skills[0])

    def test_database_import_is_queryable_by_workbench_and_can_be_verified_again(self):
        report = build(self.root, self.root)
        self.assertEqual(report, build(self.root, self.root, verify_only=True))
        self.assertEqual(report['counts']['skills'], 2)
        self.assertEqual(report['counts']['actor_variants'], 1)
        self.assertEqual(report['counts']['combat_config_exports'], 2)
        self.assertEqual(report['counts']['timeline_actions'], 1)
        with closing(connect_readonly(self.root / DATABASE)) as db:
            self.assertEqual(db.execute('SELECT DISTINCT next_action FROM boss_adaptation_queue').fetchall(),
                             [('review',)])
        # These raw row files are not needed once the database has been built.
        (self.repertoire / '056_YouLong.json').unlink()
        (self.combo / 'parents.json').unlink()
        (self.combo / 'trees.json').unlink()
        catalog = open_catalog(self.root, self.root)
        self.assertEqual(catalog.ordered_folders(), ('056_YouLong', 'native_support'))
        self.assertIn('ActorC_Example  PDA_ActorConfig_C', catalog.folder_details('056_YouLong'))
        child, parent = catalog.role('056_YouLong')['skills']
        self.assertEqual(child['class_path'], self.child)
        self.assertIn('1.5  ExpectedAction  0.25', catalog.details(parent))
        self.assertIn('Child_C（按战术标签选招）', catalog.details(parent))

    def test_failed_import_leaves_no_database_for_the_workbench(self):
        write(self.repertoire / 'timelines.json', {})
        with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
            build(self.root, self.root)
        self.assertFalse((self.root / DATABASE).exists())

    def test_failed_rebuild_preserves_previous_verified_database(self):
        before = build(self.root, self.root)
        write(self.repertoire / 'timelines.json', {})
        with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
            build(self.root, self.root, rebuild=True)
        self.assertEqual(before, build(self.root, self.root, verify_only=True))

    def test_priorities_use_combos_and_phase_family_and_keep_utility_last(self):
        role = dict(skills=[], root_packages=0, native_routes={})
        folders = ('888_UltimateBoss', 'native_support', '001_Light', '010_Heavy', '011_Heavy_P2')
        roles = {folder: role for folder in folders}
        parents = {self.parent: dict(folder='011_Heavy_P2', trees=[self.tree])}
        trees = {self.tree: dict(nodes=[dict(branch=[0], subtree=self.tree)])}
        rows = priorities(roles, parents, trees)
        self.assertEqual([row[0] for row in rows],
                         ['888_UltimateBoss', '011_Heavy_P2', '010_Heavy', '001_Light', 'native_support'])
        self.assertEqual(rows[1][1:4], ('heavy', 2, 2))
