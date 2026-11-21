import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import build_boss_disk_combo_index as combo
from boss_disk_declarations import digest, write_new


def ref(package, index, kind, name):
    return dict(ObjectName=f"{kind}'{name}'", ObjectPath=f'{package}.{index}')


class ComboIndexTests(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.directory = Path(scratch.name)
        self.packages = []
        self.child = ref('/Game/Move', 0, 'LegoAbilityBlueprintGeneratedClass', 'Move_C')
        self.add('/Game/Move', [dict(Type='LegoAbilityBlueprintGeneratedClass', Name='Move_C', Package='/Game/Move')])

    def add(self, name, exports):
        filename = name.rsplit('/', 1)[-1]
        path = self.directory / (filename + '.json')
        write_new(path, exports)
        self.packages.append(dict(package='ProjectPBZ/Content/' + filename + '.uasset',
                                  declaration=str(path), declaration_sha256=digest(path)))

    def tree(self, name, nested=None, bad_owner=False):
        path = '/Game/' + name
        tree = ref(path, 0, 'BehaviorTree', name)
        root = ref(path, 1, 'BTComposite_Selector', name + ':Selector')
        task = ref(path, 2, 'BTTask_ActivateAbility', name + ':Move')
        decorator = ref(path, 3, 'BTDecorator_Tag', name + ':RequiresTag')
        children = [dict(ChildTask=task, Decorators=[decorator], DecoratorOps=[{'Number': 0}])]
        exports = [dict(Type='BehaviorTree', Name=name, Package=path, Properties=dict(RootNode=root)),
                   dict(Type='BTComposite_Selector', Name='Selector', Outer=tree,
                        Properties=dict(TreeAsset=tree, Children=children)),
                   dict(Type='BTTask_ActivateAbility', Name='Move', Outer=tree,
                        Properties=dict(TreeAsset=tree, AbilityToActivate=self.child)),
                   dict(Type='BTDecorator_Tag', Name='RequiresTag', Outer=tree,
                        Properties=dict(TreeAsset=tree, Condition='Fixture.Tag'))]
        if bad_owner:
            exports[2]['Outer'] = ref('/Game/Wrong', 0, 'BehaviorTree', 'Wrong')
        if nested:
            children.append(dict(ChildTask=ref(path, 4, 'BTTask_RunBehavior', name + ':Nested')))
            exports.append(dict(Type='BTTask_RunBehavior', Name='Nested', Outer=tree,
                                Properties=dict(TreeAsset=tree, BehaviorAsset=nested)))
        self.add(path, exports)
        return tree

    def scheduler(self, path, props, parent=None):
        filename = path.rsplit('/', 1)[-1]
        name = filename + '_C'
        export = dict(Type='BlueprintGeneratedClass', Name=name, Package=path,
                      SuperStruct=parent or combo.NATIVE_PARENT,
                      ClassDefaultObject=ref(path, 1, name, 'Default__' + name))
        self.add(path, [export, dict(Type=name, Name='Default__' + name, Package=path, Properties=props)])
        return export

    def test_weighted_inherited_tree_keeps_branch_and_nested_task(self):
        nested = self.tree('Nested-01')
        self.tree('Outer-01', nested)
        self.scheduler('/Game/Base', {'ComboTreeWithWeight': [
            dict(Key="BehaviorTree'/Game/Bad.Bad'", Value=25),
            dict(Key="BehaviorTree'/Game/Outer-01.Outer-01'", Value=75)]})
        child = self.scheduler('/Game/Child', {}, ref('/Game/Base', 0, 'BlueprintGeneratedClass', 'Base_C'))
        source = combo.Capture(self.packages)
        graph, trees = combo.graph(source, child, lambda ref: combo.ordered_nodes(source, ref))
        self.assertEqual(graph['issues'], ['package_not_captured'])
        self.assertEqual(graph['referenced_abilities'], ['/Game/Move.Move_C'])
        self.assertEqual(graph['choices'], [dict(path='/Game/Outer-01.Outer-01', field='ComboTreeWithWeight',
                                                 weight=75, owner='/Game/Base.Base_C')])
        nodes = trees['/Game/Outer-01.Outer-01']['nodes']
        self.assertEqual([row['branch'] for row in nodes], [[], [0], [1]])
        self.assertEqual(nodes[1]['decorators'][0]['properties'], {'Condition': 'Fixture.Tag'})
        self.assertIn('/Game/Nested-01.Nested-01', trees)

    def test_foreign_tree_node_and_changed_package_are_rejected(self):
        tree = self.tree('WrongOuter', bad_owner=True)
        source = combo.Capture(self.packages)
        graph = combo.ordered_nodes(source, combo.split_reference(tree))
        self.assertEqual(graph['issues'], ['tree_owner_mismatch'])
        self.assertFalse(any('ability' in node for node in graph['nodes']))
        Path(self.packages[-1]['declaration']).write_text('[]', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
            combo.ordered_nodes(combo.Capture(self.packages), combo.split_reference(tree))

    def test_only_same_actor_config_and_grant_dump_count_as_coobserved(self):
        observed = dict(actor='actor', config='variant', session='20261121-080000', grant_count_line=12, count=1)
        parent = dict(historical_unique_grants=[observed])
        changed = [dict(observed, **{field: value}) for field, value in
                   [('config', 'another'), ('actor', 'another'), ('grant_count_line', 13), ('count', 2)]]
        self.assertEqual(combo.coobserved(parent, dict(historical_unique_grants=changed)), [])
        expected = {key: value for key, value in observed.items() if key != 'count'}
        self.assertEqual(combo.coobserved(parent, parent), [expected])
