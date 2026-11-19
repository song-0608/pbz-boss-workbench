"""Resolve observed combo dependencies offline, retaining exact variant grants.

Declaration graphs are not execution traces. This report never registers a
parent with the scheduler or grants activation permission to its descendants.
"""
import argparse
from collections import Counter
import hashlib
import json
import re

from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from boss_combat_candidate_policy import ability_reason
from boss_metadata_jobs import canonical
import boss_offline_inventory as inventory
from collect_boss_subtree_progress import history

SOURCES = ('tools/boss_combo_dependencies.py', 'tests/test_boss_combo_dependencies.py',
           'tools/boss_combat_candidate_policy.py')
OUTPUT = 'runtime/boss-combo-dependencies'


def declarations(audits):
    found = {}
    for audit in audits:
        assert audit['metadata_only'] is True and audit['playable'] is False
        for row in audit['outcomes']:
            parent = row['parent_class']
            assert inventory.OBJECT.fullmatch(parent) and parent.endswith('_C')
            if not row['mapping_observed']:
                assert not row['trees'], 'rejected graph must not supply dependencies'
                continue
            assert row['native_grant_verified'] is False and row['activation_verified'] is False
            trees = []
            for tree in row['trees']:
                refs = sorted({r['value'].split(' ', 1)[1] for r in tree['references']
                               if r['property'] == 'AbilityToActivate'})
                assert all(inventory.OBJECT.fullmatch(p) and p.endswith('_C') for p in refs)
                trees.append(dict(path=tree['path'], weight=tree['weight'], references=refs,
                                  declaration_sha256=hashlib.sha256(canonical(tree)).hexdigest()))
            trees.sort(key=lambda tree: tree['path'])
            assert len({t['path'] for t in trees}) == len(trees)
            entry = found.setdefault(parent, dict(trees=trees, origins=[]))
            # Conflicting maps cannot be merged into one apparent combo.
            assert entry['trees'] == trees, 'conflicting closed declarations: ' + parent
            entry['origins'].append(dict(session=audit['session'], key=row['key']))
    for entry in found.values():
        entry['origins'].sort(key=lambda row: (row['session'], row['key']))
    return found


def resolve(parent, abilities, graphs):
    prefix = '/'.join(parent.split('/')[:5]) + '/'
    leaves, subtrees, issues = set(), set(), set()

    def visit(path, stack):
        if path in stack:
            issues.add(('cycle', path)); return
        if not path.startswith(prefix):
            issues.add(('foreign_character', path)); return
        ability = abilities.get(path)
        if not ability or ability['metadata'] != 'verified':
            issues.add(('unverified_type', path)); return
        if ability['kind'] == 'leaf':
            leaves.add(path); return
        assert ability['kind'] == 'subtree', 'unknown verified ability kind'
        subtrees.add(path)
        graph = graphs.get(path)
        if graph is None:
            issues.add(('missing_closed_graph', path)); return
        refs = {p for tree in graph['trees'] for p in tree['references']}
        if not refs:
            issues.add(('no_declared_ability_reference', path)); return
        for child in sorted(refs):
            visit(child, (*stack, path))

    visit(parent, ())
    return dict(leaf_classes=sorted(leaves), subtree_classes=sorted(subtrees),
                issues=[dict(reason=reason, path=path) for reason, path in sorted(issues)],
                declaration_closure_complete=not issues)


def plan(characters, audits):
    # Global passives can occur in many actors' dumps. Only exact NPC-folder
    # records participate; sharing a global grant does not imply shared moves.
    owned = [a for c in characters for a in c['abilities']
             if a['path'].startswith('/PBZCombatAsset/ActorData/Mobs/' + c['folder'] + '/')]
    abilities = {a['path']: a for a in owned}
    assert len(abilities) == len(owned), 'duplicate same-folder ability metadata'
    graphs = declarations(audits)
    rows = []
    for character in characters:
        prefix = '/PBZCombatAsset/ActorData/Mobs/' + character['folder'] + '/'
        variants = {v['path']: v for v in character['variants']}
        for ability in character['abilities']:
            if ability['metadata'] != 'verified' or ability['kind'] != 'subtree':
                continue
            parent = ability['path']
            assert parent.startswith(prefix)
            closure = resolve(parent, abilities, graphs)
            cohorts = {}
            for grant in ability['grants']:
                if grant['count'] != 1:
                    continue
                assert re.fullmatch(r'\d{8}-\d{6}', grant['session']), 'exact closed parent session required'
                assert type(grant['grant_count_line']) is int and grant['grant_count_line'] > 0, \
                    'complete parent grant snapshot required'
                actor, config = grant['actor'], grant['config']
                assert actor.startswith(prefix) and config.startswith(prefix)
                variant = variants.get(actor)
                fact = variant and variant.get('observation')
                if not fact or fact['observed_config'] != config:
                    continue
                lineage = fact.get('lineage', [])
                if (variant['metadata'] != 'verified' or not variant['receipts']
                        or not lineage or lineage[0] != actor
                        or '/Script/ProjectPBZ.PBZCharacter_NPC' not in lineage
                        or '/Script/Engine.Character' not in lineage):
                    continue
                key = actor, config
                cohorts.setdefault(key, []).append(dict(session=grant['session'],
                    grant_count_line=grant['grant_count_line']))
            exact = [dict(actor=actor, config=config,
                          parent_grant_snapshots=sorted(snapshots, key=lambda s: (s['session'], s['grant_count_line'])))
                     for (actor, config), snapshots in sorted(cohorts.items())]
            rows.append(dict(id=character['id'], parent_class=parent, **closure,
                trees=graphs.get(parent, {}).get('trees', []),
                origins=graphs.get(parent, {}).get('origins', []),
                exact_parent_variants=exact,
                context_review=[dict(path=p, reason=ability_reason(p))
                    for p in closure['leaf_classes'] if ability_reason(p)],
                activation_allowed=False, execution_order_proven=False, playable=False))
    return sorted(rows, key=lambda row: (row['id'], row['parent_class']))


def build_snapshot(root=ROOT):
    """Return the freshly replayed inventory with its derived dependency report.

    Callers that need exact Actor/CDO observations must use this same replay,
    rather than independently scanning the entire closed history a second time.
    No inventory is accepted from a caller or reused across commands.
    """
    snapshot, *_ = inventory.inputs(root)
    audits = history(root)
    sources = dict(snapshot['sources'])
    for audit in audits:
        for name, digest in audit['sources'].items():
            assert name not in sources or sources[name] == digest
            assert sha(root / name) == digest, 'closed dependency source changed'
            sources[name] = digest
    sources.update({name: sha(root / name) for name in SOURCES})
    rows = plan(snapshot['characters'], audits)
    report = dict(schema=1, build=BUILD, parents=rows, sources=sources,
        summary=dict(parents=len(rows), closed_graphs=sum(bool(r['trees']) for r in rows),
            complete_declaration_closures=sum(r['declaration_closure_complete'] for r in rows),
            exact_parent_variant_pairs=sum(len(r['exact_parent_variants']) for r in rows),
            issues=dict(Counter(i['reason'] for r in rows for i in r['issues']))),
        game_started=False, stage_supported=False, activation_allowed=False,
        installed=False, execution_order_proven=False, playable=False)
    key = hashlib.sha256(canonical(report)).hexdigest()[:20]
    target = root / OUTPUT / key / 'dependencies.json'
    if target.exists():
        assert inventory.read(target) == report, 'preserve frozen dependency report'
    else:
        write_json(target, report)
    return target, report, snapshot


def build(root=ROOT):
    target, report, _ = build_snapshot(root)
    return target, report


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    target, result = build()
    print(json.dumps(dict(report=str(target), **result['summary'], game_started=False,
                          activation_allowed=False), ensure_ascii=False, indent=2))
