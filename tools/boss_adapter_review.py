"""Prepare variant/config review and missing metadata jobs from replayed receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import boss_adapter_registry as registry
import boss_metadata_jobs as metadata
from boss_adaptation_workflow import ROOT, BUILD, GATES, sha, write_json
from collect_boss_metadata_jobs import repository_path, verify_receipt

SOURCES=('tools/boss_adapter_review.py','tests/test_boss_adapter_review.py')
OUTPUT='evidence/adaptation/boss-adapter-review.json'
RECEIPTS='research/boss-adaptation/adapter-metadata-receipts'


def plan(catalog,identifiers,receipts):
    """Pure planning over independently verified receipts; never choose a variant."""
    prepared=registry.plan(catalog,identifiers)
    candidates=[next(c for c in catalog['candidates'] if c['id']==i) for i in identifiers]
    jobs=[j for c in candidates for j in metadata.jobs_for(c)]
    history={job['key']:[] for job in jobs}
    for path,receipt in sorted(receipts.items()):
        assert receipt['target_build_sha256']==BUILD and receipt['metadata_only'] is True
        assert all(receipt[key] is False for key in ('playable','control_verified','runtime_acceptance_current'))
        for outcome in receipt['outcomes']:
            if outcome['key'] in history:
                history[outcome['key']].append(dict(receipt=path,outcome=outcome))
    pending=[];adapters=[];conflict_keys=[];verified_keys=[]
    for base,candidate in zip(prepared['adapters'],candidates):
        variants=[];skills=[];failed=missing=0
        for job in metadata.jobs_for(candidate):
            rows=history[job['key']]
            successes=[row for row in rows if row['outcome']['metadata_verified'] is True]
            for row in rows:
                outcome=row['outcome']
                assert (outcome['id'],outcome['role'],outcome['class_path'])==(job['id'],job['role'],job['lookup_path'])
                assert all(outcome[key] is False for key in ('identity_verified','live_grant_verified','activation_verified','playable'))
            distinct={metadata.canonical(row['outcome']) for row in successes}
            fact=successes[0]['outcome'] if len(distinct)==1 else None
            if len(distinct)>1:
                status='conflicting_metadata';conflict_keys.append(job['key'])
            elif fact:
                status='awaiting_identity_review' if job['role']=='character' else 'awaiting_live_grant_binding'
                verified_keys.append(job['key'])
            else:
                status='metadata_rejected' if rows else 'awaiting_metadata'
                failed+=bool(rows);missing+=not rows;pending.append(job['key'])
            row=dict(key=job['key'],class_path=job['lookup_path'],status=status,
                metadata_verified=fact is not None,evidence=rows,playable=False)
            if job['role']=='character':
                row.update(config_candidates=job['config_candidates'],observed_config=None,display_name=None,
                    config_in_observed_candidates=None,identity_verified=False,selected=False)
                if fact:
                    row.update({key:fact[key] for key in ('observed_config','display_name','lineage','config_in_observed_candidates')})
                    if not fact['config_in_observed_candidates']:
                        row['status']='config_review_required'
                variants.append(row)
            else:
                asset=next(a for a in candidate['assets'] if a['package']==job['package'])
                row.update(ability_kind=fact['ability_kind'] if fact else None,resource_role=asset['role'],
                    granted_to_selected_actor=False,owned_variant_class=None,player_key=None,
                    live_grant_verified=False,activation_verified=False)
                skills.append(row)
        blockers=['Select and independently review the exact Boss variant; no automatic first-class selection.',
            'Collect native granted ability ownership for the reviewed variant before assigning player keys.',
            'Validate control lifecycle, effects, recovery and measured performance in a consolidated session.']
        if failed or missing:
            blockers.insert(0,'Collect only missing or rejected metadata jobs in the prepared retry batches.')
        if any(row['status']=='conflicting_metadata' for row in variants+skills):
            blockers.insert(0,'Resolve contradictory successful observations; do not silently select the latest receipt.')
        if any(row['status']=='config_review_required' for row in variants):
            blockers.insert(0,'Review the actual CDO config outside the historical candidate list; do not rewrite catalog clues.')
        adapters.append(dict(id=base['id'],resource_folder=base['resource_folder'],variants=variants,skills=skills,
            selected_variant=None,enabled=False,playable=False,runtime_profile=None,runtime_policy=None,
            identity_verified=False,control_verified=False,capabilities={gate:False for gate in GATES},
            missing_metadata_jobs=missing,rejected_metadata_jobs=failed,blockers=blockers))
    return dict(schema_version=1,target_build_sha256=BUILD,adapters=adapters,
        verified_metadata_job_keys=verified_keys,conflicting_metadata_job_keys=conflict_keys,
        pending_metadata_job_keys=pending,retry_job_batches=metadata.batches(candidates,pending),
        metadata_queries_avoided=len(verified_keys)+len(conflict_keys),
        conflicts_require_review=True,automatic_variant_selection=False,
        automatic_skill_grants=False,game_started=False,installed=False,
        new_playable_bosses=0,complete_mod=False,runtime_acceptance_current=False)


def inputs(root):
    registry.verify(root=root)
    expansion=root/'evidence/adaptation/boss-adapter-expansion.json'
    report=json.loads(expansion.read_bytes())
    catalog_path=repository_path(root,report['catalog'])
    catalog=json.loads(catalog_path.read_bytes())
    queue=json.loads((root/registry.QUEUE).read_bytes())
    receipts={}
    directory=repository_path(root,RECEIPTS)
    if directory.exists():
        for path in sorted(directory.iterdir()):
            assert path.is_file() and path.suffix=='.json','Only closed receipt JSON files belong in this directory'
            receipts[path.relative_to(root).as_posix()]=verify_receipt(path,root)
    result=plan(catalog,queue['candidate_ids'],receipts)
    sources={name:sha(repository_path(root,name)) for name in SOURCES}
    identity=dict(plan=result,expansion_sha256=sha(expansion),source_files=sources,
        receipt_files={name:sha(repository_path(root,name)) for name in receipts})
    return identity,hashlib.sha256(metadata.canonical(identity)).hexdigest()[:20]


def build(root=ROOT):
    root=Path(root).resolve();identity,fingerprint=inputs(root)
    target=root/'runtime/boss-reviews'/fingerprint
    batches=[]
    for jobs in identity['plan']['retry_job_batches']:
        directory=metadata.freeze(jobs,target/'metadata',root)
        batches.append(dict(directory=directory.relative_to(root).as_posix(),requests=len(jobs),
            manifest_sha256=sha(directory/'metadata-probe-manifest.json'),
            candidate_ids=list(dict.fromkeys(job['id'] for job in jobs))))
    write_json(target/'review-plan.json',identity['plan'])
    report=dict(schema_version=1,status='offline-adapter-review',fingerprint=fingerprint,
        directory=target.relative_to(root).as_posix(),**identity,retry_batches=batches,
        plan_sha256=sha(target/'review-plan.json'))
    path=root/OUTPUT;write_json(path,report)
    verify(path,root)
    return path


def verify(path=None,root=ROOT):
    root=Path(root).resolve();report=json.loads(Path(path or root/OUTPUT).read_bytes())
    identity,fingerprint=inputs(root)
    assert report['schema_version']==1 and report['status']=='offline-adapter-review'
    assert report['fingerprint']==fingerprint and all(report[key]==value for key,value in identity.items())
    assert report['directory']=='runtime/boss-reviews/'+fingerprint
    target=repository_path(root,report['directory'])
    assert sha(target/'review-plan.json')==report['plan_sha256']
    assert json.loads((target/'review-plan.json').read_bytes())==identity['plan']
    expected_batches=identity['plan']['retry_job_batches']
    assert len(report['retry_batches'])==len(expected_batches)
    for row,jobs in zip(report['retry_batches'],expected_batches):
        directory=repository_path(root,row['directory'])
        assert directory.parent==target/'metadata'
        manifest=metadata.verify_batch(directory,root)
        assert manifest['jobs']==jobs and row['requests']==len(jobs)
        assert sha(directory/'metadata-probe-manifest.json')==row['manifest_sha256']
        assert row['candidate_ids']==list(dict.fromkeys(job['id'] for job in jobs))
    return dict(passed=True,adapters=len(identity['plan']['adapters']),closed_receipts=len(identity['receipt_files']),
        verified_metadata_jobs=len(identity['plan']['verified_metadata_job_keys']),
        conflicting_metadata_jobs=len(identity['plan']['conflicting_metadata_job_keys']),
        pending_metadata_jobs=len(identity['plan']['pending_metadata_job_keys']),
        retry_batches=len(report['retry_batches']),new_playable_bosses=0,game_started=False,
        complete_mod=False,runtime_acceptance_current=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    if not args.verify:
        build()
    print(json.dumps(verify(),ensure_ascii=False))
