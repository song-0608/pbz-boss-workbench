"""Build Boss adapter manifests and bounded metadata work from observed resources."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, OUT, BUILD, GATES, sha, write_json
from build_boss_adaptation_batch import candidate_work, freeze, select_batch
from build_boss_identity_probe import build as build_probe, requests, render

QUEUE='research/boss-adaptation/expansion-queue.json'
SOURCES=('tools/boss_adapter_registry.py','tools/boss_adaptation_workflow.py',
    'tools/build_boss_adaptation_batch.py','tools/build_boss_identity_probe.py',
    'tests/test_boss_adapter_registry.py','tests/test_boss_adaptation_batch.py',
    'tests/test_boss_identity_probe.lua',QUEUE)


def read(path):
    return json.loads(Path(path).read_bytes())


def safe(root,relative):
    if not isinstance(relative,str) or not relative or '\\' in relative or ':' in relative:
        raise ValueError('Relative repository path required')
    parts=relative.split('/')
    if any(part in ('','.','..') for part in parts):
        raise ValueError('Canonical repository path required')
    path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Repository path escaped')
    return path


def plan(catalog,identifiers):
    if catalog.get('target_build_sha256')!=BUILD:
        raise ValueError('Registered fixed build required')
    if not 1<=len(identifiers)<=12 or len(set(identifiers))!=len(identifiers):
        raise ValueError('One to twelve distinct adapter identifiers required')
    indexed={c['id']:c for c in catalog['candidates']}
    adapters=[]
    for identifier in identifiers:
        if not isinstance(identifier,str) or not re.fullmatch(r'[a-z0-9_]{1,80}',identifier):
            raise ValueError('Invalid adapter identifier')
        candidate=indexed.get(identifier)
        if not candidate or candidate.get('reference_only') or candidate['resource_folder']=='Common':
            raise ValueError('Unknown or reference-only adapter: '+identifier)
        work=candidate_work(candidate)
        unambiguous=len(work['class_candidates'])==len(work['config_candidates'])==1
        identity_jobs=requests(work) if unambiguous else []
        # Resource names are candidate metadata, never gameplay ability grants.
        adapters.append(dict(id=identifier,resource_folder=work['resource_folder'],
            stage='ready_for_identity_metadata' if unambiguous else 'variant_binding_required',
            class_candidates=work['class_candidates'],config_candidates=work['config_candidates'],
            identity_requests=identity_jobs,skills=work['skills'],
            enabled=False,playable=False,identity_verified=False,
            control_verified=False,runtime_acceptance_current=False,
            runtime_profile=None,runtime_policy=None,
            capabilities={name:False for name in GATES},
            missing=['exact class lineage, CDO config binding and display name',
                'Boss-specific live grants, natural finish, cancellation and effects',
                'movement, input/camera restoration, disposal and measured performance'],
            variant_blocker=None if unambiguous else
                'Multiple or missing class/config resources; do not pair main bodies, summons or stage props by folder.'))
    ready=[a['id'] for a in adapters if a['identity_requests']]
    batches=[ready[i:i+3] for i in range(0,len(ready),3)]
    # The generic batch selector enforces the same boundary used by the builder.
    work=[candidate_work(indexed[a['id']]) for a in adapters]
    for batch in batches:
        select_batch(work,batch)
    return dict(schema_version=1,target_build_sha256=BUILD,adapters=adapters,
        next_identity_batches=batches,game_started=False,installed=False,
        complete_mod=False,runtime_acceptance_current=False,new_playable_bosses=0,
        architecture=dict(discovery='observed catalog with source hashes',
            planning='per-Boss adapter manifests and bounded missing-evidence jobs',
            runtime='shared native lifecycle plus separately reviewed Boss terrain policy',
            promotion='independent identity, grants and runtime acceptance; never folder-name inference'))


def build(root=ROOT,catalog_path=None):
    root=Path(root).resolve()
    catalog_path=Path(catalog_path) if catalog_path else root/'research/boss-adaptation/catalog.json'
    catalog=read(catalog_path);queue=read(root/QUEUE)
    assert queue['schema_version']==1 and queue['target_build_sha256']==BUILD
    for row in catalog['sources']:
        assert row['path'].startswith('evidence/'),'Historical evidence path required'
        assert sha(safe(root,row['path']))==row['sha256'],'Historical source changed: '+row['path']
    registry=plan(catalog,queue['candidate_ids'])
    sources={name:sha(safe(root,name)) for name in SOURCES}
    identity=dict(registry=registry,catalog_sha256=sha(catalog_path),sources=sources)
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:20]
    target=root/'runtime/boss-expansion'/fingerprint
    target.mkdir(parents=True,exist_ok=True)
    batches=[]
    for identifiers in registry['next_identity_batches']:
        batch=freeze(catalog_path,target/'batches',root,identifiers=identifiers)
        script=build_probe(batch)
        batches.append(dict(directory=batch.relative_to(root).as_posix(),candidate_ids=identifiers,
            manifest_sha256=sha(batch/'manifest.json'),probe_manifest_sha256=sha(batch/'identity-probe-manifest.json'),
            script_sha256=sha(script),requests=len(read(batch/'identity-probe-manifest.json')['requests']),
            deployed=False,game_started=False))
    for adapter in registry['adapters']:
        write_json(target/'adapters'/(adapter['id']+'.json'),adapter)
    write_json(target/'registry.json',registry)
    report=dict(schema_version=1,status='offline-adapter-preparation',passed=True,
        fingerprint=fingerprint,directory=target.relative_to(root).as_posix(),
        catalog=catalog_path.relative_to(root).as_posix(),catalog_sha256=sha(catalog_path),
        source_files=sources,registry=registry,registry_sha256=sha(target/'registry.json'),
        adapter_files={p.relative_to(target).as_posix():sha(p) for p in sorted((target/'adapters').glob('*.json'))},
        batches=batches,game_started=False,installed=False,new_playable_bosses=0,
        complete_mod=False,runtime_acceptance_current=False)
    output=root/'evidence/adaptation/boss-adapter-expansion.json'
    write_json(output,report)
    verify(output,root)
    return output


def verify(report_path=None,root=ROOT):
    root=Path(root).resolve()
    report=read(report_path or root/'evidence/adaptation/boss-adapter-expansion.json')
    assert report['schema_version']==1 and report['status']=='offline-adapter-preparation' and report['passed'] is True
    for key in ('game_started','installed','complete_mod','runtime_acceptance_current'):
        assert report[key] is False,key
    assert report['new_playable_bosses']==0
    assert report['source_files']=={name:sha(safe(root,name)) for name in SOURCES}
    catalog_path=safe(root,report['catalog']);catalog=read(catalog_path)
    assert sha(catalog_path)==report['catalog_sha256']
    for row in catalog['sources']:
        assert row['path'].startswith('evidence/') and sha(safe(root,row['path']))==row['sha256']
    expected=plan(catalog,read(root/QUEUE)['candidate_ids'])
    assert report['registry']==expected
    identity=dict(registry=expected,catalog_sha256=report['catalog_sha256'],sources=report['source_files'])
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:20]
    assert report['fingerprint']==fingerprint and report['directory']=='runtime/boss-expansion/'+fingerprint
    target=safe(root,report['directory'])
    assert sha(target/'registry.json')==report['registry_sha256'] and read(target/'registry.json')==expected
    files={'adapters/'+a['id']+'.json' for a in expected['adapters']}
    assert set(report['adapter_files'])==files
    assert {p.relative_to(target).as_posix() for p in (target/'adapters').glob('*')}==files
    for adapter in expected['adapters']:
        name='adapters/'+adapter['id']+'.json';path=safe(target,name)
        assert sha(path)==report['adapter_files'][name] and read(path)==adapter
    assert [b['candidate_ids'] for b in report['batches']]==expected['next_identity_batches']
    for batch in report['batches']:
        directory=safe(root,batch['directory'])
        assert directory.is_relative_to(target/'batches')
        manifest=read(directory/'manifest.json');probe=read(directory/'identity-probe-manifest.json')
        for name,digest in manifest['source_files'].items():
            assert sha(safe(root,name))==digest,'Frozen metadata source changed: '+name
        assert sha(directory/'manifest.json')==batch['manifest_sha256']==probe['batch_manifest_sha256']
        assert sha(directory/'identity-probe-manifest.json')==batch['probe_manifest_sha256']
        assert sha(directory/'identity-probe.lua')==batch['script_sha256']==probe['script_sha256']
        assert manifest['target_build_sha256']==probe['target_build_sha256']==BUILD
        assert manifest['next_batch']['candidate_ids']==batch['candidate_ids']
        expected_requests=[]
        for identifier in batch['candidate_ids']:
            relative='candidates/'+identifier+'.json';path=safe(directory,relative)
            assert sha(path)==manifest['candidate_files'][relative]
            work=candidate_work(next(c for c in catalog['candidates'] if c['id']==identifier))
            assert read(path)==work
            expected_requests.extend(requests(work))
        assert probe['requests']==expected_requests and len(expected_requests)==batch['requests']<=6
        assert (directory/'identity-probe.lua').read_bytes()==render(expected_requests).encode('utf-8')
        assert probe['auto_deploy'] is False and probe['runtime_verified'] is False
        assert batch['deployed'] is False and batch['game_started'] is False
    return dict(passed=True,adapters=len(expected['adapters']),metadata_ready=sum(bool(a['identity_requests']) for a in expected['adapters']),
        variant_blocked=sum(not a['identity_requests'] for a in expected['adapters']),
        metadata_requests=sum(b['requests'] for b in report['batches']),game_started=False,new_playable_bosses=0)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    if not args.verify:
        build()
    print(json.dumps(verify(),ensure_ascii=False))
