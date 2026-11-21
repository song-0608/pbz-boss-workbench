"""Index serialized Boss combo branches and grants from the frozen offline capture."""
import argparse
from collections import Counter
from functools import lru_cache
import json
import math
import re
from pathlib import Path

from boss_disk_declarations import digest, write_new
from boss_disk_dependencies import native_package
from build_boss_disk_repertoire import read_verified, superclass


REFERENCE = re.compile(r"([A-Za-z0-9_]+)'([A-Za-z0-9_:\-]+)'")
WEIGHTED_TREE = re.compile(r"BehaviorTree'(/[A-Za-z0-9_/\-]+)\.([A-Za-z0-9_\-]+)'")
NATIVE_PARENT = {'ObjectName': "Class'RunSubtreeAbility'", 'ObjectPath': '/Script/SGameAI'}


class Unresolved(ValueError):
    """An exact serialized link could not be resolved in the captured data."""


def split_reference(ref):
    match = REFERENCE.fullmatch(ref.get('ObjectName', '')) if isinstance(ref, dict) else None
    if not match:
        raise Unresolved('invalid_object_reference')
    mount, _, index = ref.get('ObjectPath', '').rpartition('.')
    if not mount.startswith('/') or not index.isascii() or not index.isdecimal():
        raise Unresolved('invalid_export_index')
    return mount, int(index), match[1], match[2]


class Capture:
    def __init__(self, packages):
        self.packages = {native_package(row['package']).casefold(): row for row in packages}
        if len(packages) != len(self.packages):
            raise ValueError('Duplicate package in terminal scan')
        self.exports = lru_cache(maxsize=48)(self._exports)

    def _exports(self, key):
        package = self.packages.get(key)
        if package is None:
            raise Unresolved('package_not_captured')
        return read_verified(package['declaration'], package['declaration_sha256'])

    def exact(self, mount, index, export_type, name):
        exports = self.exports(mount.casefold())
        if index >= len(exports):
            raise Unresolved('export_out_of_range')
        item = exports[index]
        owner = item.get('Package')
        if (item['Type'] != export_type or item['Name'] != name.rsplit(':', 1)[-1]
                or (owner is not None and owner.casefold() != mount.casefold())
                or (owner is None and ':' not in name)):
            raise Unresolved('export_identity_mismatch')
        return item

    def resolve(self, ref):
        return self.exact(*split_reference(ref))

    def weighted_tree(self, value):
        match = WEIGHTED_TREE.fullmatch(value) if isinstance(value, str) else None
        if not match:
            raise Unresolved('invalid_weighted_tree')
        mount, name = match.groups()
        exports = self.exports(mount.casefold())
        indices = [i for i, row in enumerate(exports) if row['Type'] == 'BehaviorTree' and row['Name'] == name]
        if len(indices) != 1:
            raise Unresolved('nonunique_weighted_tree')
        return mount, indices[0], 'BehaviorTree', name

    def defaults(self, item):
        cdo = self.resolve(item.get('ClassDefaultObject'))
        if cdo['Package'] != item['Package'] or cdo['Name'] != 'Default__' + item['Name']:
            raise Unresolved('class_default_identity_mismatch')
        return cdo.get('Properties', {})


def mappings(capture, item):
    """Find the nearest serialized value for each tree-bearing CDO field."""
    found, seen = {}, set()
    while True:
        identity = item['Package'] + '.' + item['Name']
        if identity in seen or len(seen) == 64:
            raise Unresolved('class_ancestry_cycle_or_limit')
        seen.add(identity)
        defaults = capture.defaults(item)
        for field in ('BehaviorAsset', 'ComboTreeWithWeight'):
            if field in defaults and field not in found:
                found[field] = (identity, defaults[field])
        parent = superclass(item)
        if parent == NATIVE_PARENT:
            return found
        if not parent or parent['ObjectPath'].startswith('/Script/'):
            raise Unresolved('run_subtree_ancestry_unverified')
        item = capture.resolve(parent)


def ordered_nodes(capture, tree_ref):
    """Follow the serialized root and child slots, retaining branch conditions."""
    tree = capture.exact(*tree_ref)
    mount = tree['Package']
    nodes, seen, issues = [], set(), set()

    def local(ref):
        target = split_reference(ref)
        if target[0].casefold() != mount.casefold() or not target[3].startswith(tree['Name'] + ':'):
            raise Unresolved('foreign_tree_node')
        node = capture.exact(*target)
        for link in (node.get('Outer'), node.get('Properties', {}).get('TreeAsset')):
            owner, index, kind, name = split_reference(link)
            if (owner.casefold(), index, kind, name) != (mount.casefold(), *tree_ref[1:]):
                raise Unresolved('tree_owner_mismatch')
        return target[1], node

    def visit(ref, branch, decorators=(), operations=()):
        if len(branch) > 64 or len(nodes) >= 2048:
            issues.add('tree_traversal_limit')
            return
        try:
            ordinal, node = local(ref)
            if ordinal in seen:
                raise Unresolved('repeated_tree_node')
            seen.add(ordinal)
            props = node.get('Properties', {})
            kind = node['Type']
            row = dict(export_index=ordinal, type=kind, branch=list(branch), name=props.get('NodeName', node['Name']),
                       decorators=[dict(type=d['Type'], name=d['Name'], properties={k: v for k, v in
                                   d.get('Properties', {}).items() if k not in ('TreeAsset', 'ParentNode')})
                                   for _, d in map(local, decorators)], decorator_ops=operations,
                       properties={k: v for k, v in props.items()
                                   if k not in ('TreeAsset', 'ParentNode', 'NodeName', 'Children')})
            nodes.append(row)
            if 'AbilityToActivate' in props or kind == 'BTTask_ActivateAbility':
                if props.get('AbilityToActivate') is None:
                    issues.add('unserialized_task_ability')
                    row['ability_resolution'] = 'unserialized_task_ability'
                else:
                    a = capture.resolve(props['AbilityToActivate'])
                    if not a['Type'].endswith('BlueprintGeneratedClass') or not a['Name'].endswith('_C'):
                        raise Unresolved('invalid_task_ability_type')
                    row['ability'] = a['Package'] + '.' + a['Name']
            if 'BehaviorAsset' in props or kind in ('BTTask_RunBehavior', 'BTTask_RunBehaviorDynamic'):
                if kind == 'BTTask_RunBehaviorDynamic':
                    issues.add('dynamic_subtree_selection')
                if props.get('BehaviorAsset') is not None:
                    target = split_reference(props['BehaviorAsset'])
                    capture.exact(*target)
                    if target[2] != 'BehaviorTree':
                        raise Unresolved('invalid_subtree_type')
                    row['subtree'] = target
                elif kind != 'BTTask_RunBehaviorDynamic':
                    issues.add('unserialized_subtree')
            for index, child in enumerate(props.get('Children', [])):
                links = [child[key] for key in ('ChildTask', 'ChildComposite') if child.get(key)]
                if len(links) != 1:
                    issues.add('ambiguous_tree_child')
                    continue
                visit(links[0], (*branch, index), child.get('Decorators', []), child.get('DecoratorOps', []))
        except Unresolved as error:
            issues.add(str(error))

    root = tree.get('Properties', {}).get('RootNode')
    if root is None:
        issues.add('unserialized_root')
    else:
        visit(root, ())
    return dict(path=mount + '.' + tree['Name'], nodes=nodes, issues=sorted(issues),
                declaration_sha256=capture.packages[mount.casefold()]['declaration_sha256'])


def graph(capture, item, tree_for):
    trees, issues, choices = {}, set(), []

    def follow(ref, stack):
        key = ref[0].casefold(), ref[1]
        if key in stack or len(stack) == 64:
            issues.add('subtree_cycle_or_depth_limit')
            return
        try:
            tree = tree_for(ref)
        except Unresolved as error:
            issues.add(str(error))
            return
        if tree['path'] in trees:
            return
        trees[tree['path']] = tree
        issues.update(tree['issues'])
        for node in tree['nodes']:
            if 'subtree' in node:
                follow(tuple(node['subtree']), (*stack, key))

    try:
        fields = mappings(capture, item)
        for field, (owner, value) in fields.items():
            if field == 'BehaviorAsset':
                refs = [(split_reference(value), None)] if value is not None else []
            else:
                if not isinstance(value, list):
                    raise Unresolved('invalid_weighted_tree_list')
                refs = []
                for row in value:
                    try:
                        weight = row['Value']
                        if type(weight) not in (int, float) or not math.isfinite(weight) or weight < 0:
                            raise Unresolved('invalid_tree_weight')
                        refs.append((capture.weighted_tree(row['Key']), weight))
                    except Unresolved as error:
                        issues.add(str(error))
            for ref, weight in refs:
                tree = capture.exact(*ref)
                if tree['Type'] != 'BehaviorTree':
                    raise Unresolved('invalid_tree_type')
                choices.append(dict(path=tree['Package'] + '.' + tree['Name'], field=field, owner=owner, weight=weight))
                follow(ref, ())
    except Unresolved as error:
        issues.add(str(error))
    if not choices:
        issues.add('no_serialized_tree_choice')
    hits = {node['ability'] for tree in trees.values() for node in tree['nodes'] if 'ability' in node}
    return dict(choices=choices, trees=sorted(trees), referenced_abilities=sorted(hits), issues=sorted(issues)), trees


def build(scan_path, queue_path, output):
    queue_sha = digest(queue_path)
    queue = read_verified(queue_path, queue_sha)
    scan_sha = digest(scan_path)
    if (queue['kind'] != 'dependency_disk_and_closed_native_skill_coverage'
            or queue['disk_dependency_scan_sha256'] != scan_sha
            or any(queue[key] is not False for key in ('activation_allowed', 'playable', 'game_started', 'installed'))):
        raise ValueError('Matching terminal offline queue required')
    scan = read_verified(scan_path, scan_sha)
    if (scan['declaration_contents_verified'] is not True or scan['pending_roots'] or scan['pending_dependency_count']):
        raise ValueError('Terminal disk capture required')
    capture = Capture(scan['packages'])
    abilities = {ability['class_path']: (package, ability) for package in scan['packages']
                 for ability in package['abilities'] if ability['class_path'] and not ability['issues']}
    routes = {row['class_path']: row for row in queue['rows']}
    if routes.keys() != abilities.keys() or len(routes) != len(queue['rows']):
        raise ValueError('Queue does not match captured ability identities')
    tree_for = lru_cache(maxsize=256)(lambda ref: ordered_nodes(capture, ref))
    rows, trees = [], {}
    for path, route in sorted(routes.items()):
        if route['native_kind'] != 'subtree' or route['native_metadata'] != 'verified':
            continue
        package, ability = abilities[path]
        if route['disk_declaration_sha256'] != package['declaration_sha256']:
            raise ValueError('Subtree declaration changed after scan')
        mount, name = path.rsplit('.', 1)
        parent = capture.exact(mount, ability['export_index'], ability['export_type'], name)
        row, parsed = graph(capture, parent, tree_for)
        trees.update(parsed)
        row.update(class_path=path, folder=route['folder'], declaration_sha256=package['declaration_sha256'],
                   historical_unique_grants=route['historical_unique_grants'], context_review=route['context_review'],
                   activation_allowed=False)
        row['referenced_abilities'] = [dict(class_path=child, native_route=routes.get(child, {}).get('native_route'),
            historical_grant_cohorts=coobserved(route, routes.get(child, {})))
            for child in row['referenced_abilities']]
        rows.append(row)
    output.mkdir(parents=True, exist_ok=False)
    write_new(output/'parents.json', rows)
    write_new(output/'trees.json', trees)
    summary = dict(schema=1, kind='offline_boss_combo_tree_index', scan_sha256=scan_sha, queue_sha256=queue_sha,
                   source_sha256=digest(__file__),
                   parents=len(rows), mapped_parents=sum(bool(r['choices']) for r in rows), trees=len(trees),
                   parents_with_gaps=sum(bool(r['issues']) for r in rows), folders=len({r['folder'] for r in rows}),
                   parents_by_folder=dict(Counter(r['folder'] for r in rows)),
                   gaps=dict(Counter(issue for r in rows for issue in r['issues'])),
                   files={name: digest(output/name) for name in ('parents.json', 'trees.json')},
                   game_started=False, installed=False, activation_allowed=False, execution_order_verified=False)
    write_new(output/'summary.json', summary)
    return summary


def coobserved(parent, child):
    fields = ('actor', 'config', 'session', 'grant_count_line')
    def keys(route):
        return {tuple(row[key] for key in fields) for row in route.get('historical_unique_grants', ())
                if row['count'] == 1}
    return [dict(zip(fields, key)) for key in sorted(keys(parent) & keys(child))]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('scan', 'queue', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.scan, args.queue, args.output), ensure_ascii=False))
