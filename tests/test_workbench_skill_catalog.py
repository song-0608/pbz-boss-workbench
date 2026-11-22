import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
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
        self.tree = '/Game/Test.Test'
        self.parent = '/Game/Parent.Parent_C'
        self.child = '/Game/Child.Child_C'
        self.skills = [dict(class_path=path, declared_actions=None, native_route='no_closed_native_record',
                            timeline_resolution='native_default_unobserved', timeline_owner=None,
                            activation_allowed=False, playable=False) for path in (self.parent, self.child)]
        skill_files = {
            '056_YouLong.json': write(self.repertoire / '056_YouLong.json',
                                     {'folder': '056_YouLong', 'skills': self.skills}),
            'native_support.json': write(self.repertoire / 'native_support.json',
                                         {'folder': 'native_support', 'skills': []}),
        }
        combo_files = {
            'parents.json': write(self.combo / 'parents.json', [dict(class_path=self.parent, folder='056_YouLong',
                choices=[dict(path=self.tree, weight=100.0)], trees=[self.tree], issues=[], activation_allowed=False,
                referenced_abilities=[{'class_path': self.child}])]),
            'trees.json': write(self.combo / 'trees.json', {self.tree: {'nodes': [dict(
                branch=[0], name='Strike', type='BTTask_ActivateAbility', decorators=[], ability=self.child,
                properties={'AbilityActivationMethod': 'EAIAbilityActivationMethod::ByTactic'})]}}),
        }
        common = dict(scan_sha256='scan', queue_sha256='queue', game_started=False, installed=False,
                      activation_allowed=False)
        repertoire_sha = write(self.repertoire / 'summary.json', dict(common, kind='offline_boss_disk_repertoire',
                                                                      folders=1, files=skill_files))
        combo_sha = write(self.combo / 'summary.json', dict(common, kind='offline_boss_combo_tree_index',
                                                            parents=1, files=combo_files))
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
