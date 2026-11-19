"""Join disk skill declarations to closed native evidence without merging trust levels."""
import argparse
from collections import Counter
import json
from pathlib import Path

import boss_disk_declarations as disk
import boss_offline_inventory as native
from boss_adaptation_workflow import ROOT
from boss_combat_candidate_policy import ability_reason


def coverage(index, snapshot):
    observed={}
    for character in snapshot['characters']:
        for ability in character['abilities']:
            # Only this character's exact native package is eligible for a join.
            if ability['path'].startswith('/PBZCombatAsset/ActorData/Mobs/'+character['folder']+'/'):
                if ability['path'] in observed:
                    raise ValueError('Duplicate exact native skill identity')
                observed[ability['path']]=ability
    rows=[]
    for package in index['packages']:
        for ability in package['abilities']:
            path=ability['class_path']
            if not path or ability['issues']:
                continue
            actual=observed.get(path)
            route=actual['route'] if actual else 'no_closed_native_record'
            reason=ability_reason(path)
            if route=='in_v5_profile':
                action='keep_accepted_v5_mapping'
            elif reason:
                action='separate_context_review'
            elif actual and actual['metadata']=='verified' and actual['kind']=='subtree':
                action='review_native_subtree_dependencies'
            elif route=='leaf_with_historical_grant':
                action='review_exact_historical_actor_config_before_candidate'
            else:
                action='review_disk_parent_and_observe_exact_native_grant'
            rows.append(dict(class_path=path,folder=package['folder'],
                disk_declaration=package['declaration'],disk_declaration_sha256=package['declaration_sha256'],
                native_route=route,native_metadata=actual['metadata'] if actual else 'unobserved',
                native_kind=actual['kind'] if actual else None,
                native_receipts=actual['receipts'] if actual else [],
                historical_unique_grants=[g for g in actual['grants'] if g['count']==1] if actual else [],
                next_action=action,context_review=reason,
                current_process_grant_verified=False,activation_allowed=False,playable=False))
    if len({r['class_path'] for r in rows})!=len(rows):
        raise ValueError('Duplicate serialized skill identity')
    return dict(schema=1,kind='disk_and_closed_native_skill_coverage',
        skills=len(rows),native_routes=dict(Counter(r['native_route'] for r in rows)),
        next_actions=dict(Counter(r['next_action'] for r in rows)),
        folders=dict(sorted(Counter(r['folder'] for r in rows).items())),
        skills_with_timelines=sum(bool(a['timelines']) for p in index['packages'] for a in p['abilities']),
        rows=rows,disk_does_not_replace_native_receipts=True,
        current_process_grant_verified=False,activation_allowed=False,playable=False,
        all_boss_skills_complete=False,game_started=False,installed=False)


def build(index_path,root=ROOT):
    index_path=Path(index_path)
    index=json.loads(index_path.read_bytes())
    if (index.get('kind')!='offline_serialized_boss_skill_index' or index.get('pending_packages')!=0
            or index.get('failed_packages')!=0 or index.get('indexing_issues')!=0):
        raise ValueError('A completed, issue-free offline skill index is required')
    snapshot,*_=native.inputs(root)
    result=coverage(index,snapshot)
    result['disk_skill_index_sha256']=disk.digest(index_path)
    result['closed_native_sources']=snapshot['sources']
    result['source_sha256']={name:disk.digest(root/name) for name in
        ('tools/boss_disk_live_coverage.py','tools/boss_combat_candidate_policy.py',
         'tests/test_boss_disk_live_coverage.py')}
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('index',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    result=build(args.index)
    disk.write_new(args.output,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','closed_native_sources','source_sha256')},ensure_ascii=False))
