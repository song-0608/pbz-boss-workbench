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
        skills_with_timelines=sum(bool(a.get('timelines',a.get('declared_timelines',0)))
                                  for p in index['packages'] for a in p['abilities']),
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


def dependency_coverage(report,snapshot):
    """Keep capture gaps and inheritance separate from closed native grants."""
    result=coverage(report,snapshot)
    abilities={a['class_path']:a for p in report['packages'] for a in p['abilities']
               if a['class_path'] and not a['issues']}
    quarantined=[]
    for package in report['packages']:
        for ability in package['abilities']:
            if ability['class_path'] and not ability['issues']:
                continue
            quarantined.append(dict(class_path=ability['class_path'],folder=package['folder'],
                disk_declaration=package['declaration'],
                disk_declaration_sha256=package['declaration_sha256'],
                issues=ability['issues'] or ['exact serialized class identity is unresolved'],
                current_process_grant_verified=False,activation_allowed=False,playable=False))
    if len(result['rows'])+len(quarantined)!=report['ability_classes']:
        raise ValueError('Every serialized ability must remain represented in the offline queue')
    for row in result['rows']:
        ability=abilities[row['class_path']]
        row.update(timeline_resolution=ability['timeline_resolution'],
                   effective_timeline_class=ability['effective_timeline_class'],
                   effective_declared_actions=ability['effective_declared_actions'])
    result.update(kind='dependency_disk_and_closed_native_skill_coverage',
        source_ability_classes=report['ability_classes'],quarantined_skills=len(quarantined),
        quarantined_rows=quarantined,
        timeline_inheritance_resolution=report['timeline_inheritance_resolution'],
        capture_gaps=dict(failed_dependencies=report['failed_dependency_count'],
            deferred_dependencies=report.get('deferred_dependency_count',0),
            unindexed_references=len(report['unindexed_references']),
            unresolved_script_functions=report['unresolved_script_functions'],
            ability_indexing_issues=report['ability_indexing_issues']),
        ready_for_final_delivery=False)
    return result


def build_from_workflow(result_path,root=ROOT):
    result_path=Path(result_path).resolve()
    workflow=json.loads(result_path.read_bytes())
    if (workflow.get('schema')!=1 or workflow.get('kind')!='offline_boss_dependency_workflow_result'
            or workflow.get('bounded_traversal_completed') is not True
            or workflow.get('status') not in ('converged_with_known_gaps','converged_indexed_dependencies')
            or any(workflow.get(k) is not False for k in ('game_started','computer_use_used','installed',
                'live_grant_verified','execution_verified','all_boss_skills_complete','ready_for_final_delivery'))):
        raise ValueError('A completed offline dependency workflow is required')
    scan=Path(workflow['final_scan']).resolve()
    last=workflow['rounds'][-1]
    if (scan.parent!=result_path.parent or scan.name!=last['scan']
            or disk.digest(scan)!=workflow['final_scan_sha256']
            or workflow['final_scan_sha256']!=last['scan_sha256']
            or last.get('terminal') is not True or last['pending_dependencies']!=0
            or last['new_script_packages']!=0):
        raise ValueError('Exact terminal dependency scan is required')
    report=json.loads(scan.read_bytes())
    if (report.get('schema')!=1 or report.get('kind')!='offline_native_dependency_scan'
            or report.get('declaration_contents_verified') is not True
            or report.get('pending_roots')!=0 or report.get('pending_dependency_count')!=0
            or report['root_packages']!=report['extracted_roots']):
        raise ValueError('Verified root coverage and converged indexed references are required')
    snapshot,*_=native.inputs(root)
    result=dependency_coverage(report,snapshot)
    result.update(dependency_workflow_sha256=disk.digest(result_path),
        disk_dependency_scan_sha256=workflow['final_scan_sha256'],
        capture_status=workflow['status'],closed_native_sources=snapshot['sources'],
        dependency_policy=workflow.get('dependency_policy','all_serialized_references'),
        source_sha256={name:disk.digest(root/name) for name in
            ('tools/boss_disk_live_coverage.py','tools/boss_combat_candidate_policy.py',
             'tests/test_boss_disk_live_coverage.py')})
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('index',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--dependency-workflow',action='store_true',
                        help='Read an immutable converged workflow result instead of the legacy skill index')
    args=parser.parse_args()
    result=build_from_workflow(args.index) if args.dependency_workflow else build(args.index)
    disk.write_new(args.output,result)
    print(json.dumps({k:v for k,v in result.items() if k not in
        ('rows','quarantined_rows','closed_native_sources','source_sha256')},ensure_ascii=False))
