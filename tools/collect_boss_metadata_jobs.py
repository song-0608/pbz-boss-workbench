"""Collect closed research-session metadata, preserving each batch independently."""
import argparse
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from boss_metadata_jobs import verify_batch, analyze


def repository_path(root,relative):
    assert isinstance(relative,str) and relative and not any(c in relative for c in ('\\',':'))
    assert all(part not in ('','.','..') for part in relative.split('/')),'Canonical repository path required'
    target=(root/relative).resolve()
    assert target.is_relative_to(root.resolve()),'Evidence path escaped repository'
    return target


def batch_lines(raw,fingerprint):
    """Extract the exact complete attempt, including rejected or unexpected events."""
    selected=[];active=None;attempts=0;selected_keys=set();orphan_keys=set()
    for line in raw.splitlines():
        match=re.search(r'PBZ_ADAPTER_META:([A-Z_]+)=(.*)',line)
        if not match:
            continue
        event,payload=match.groups();payload=payload.strip()
        if event=='START':
            assert active!=fingerprint,'Interleaved metadata attempt'
            active=payload
            if payload==fingerprint:
                attempts+=1
                assert attempts==1,'Repeated metadata attempt in the raw log'
        if active==fingerprint:
            selected.append(line)
            if event in ('OUTCOME','REJECTED'):
                selected_keys.add(payload.split('|',1)[0])
        elif active is None and event in ('OUTCOME','REJECTED'):
            orphan_keys.add(payload.split('|',1)[0])
        if event=='END':
            assert payload!=fingerprint or active==fingerprint,'Unmatched batch end'
            active=None
    assert attempts==1 and active!=fingerprint,'Complete raw metadata attempt required'
    assert not selected_keys&orphan_keys,'Metadata outcome for this batch outside a complete attempt'
    return selected


def closed_evidence(session,batch,root):
    assert re.fullmatch(r'\d{8}-\d{6}',session),'Exact closed session identifier required'
    batch=Path(batch).resolve()
    relative=batch.relative_to(root).as_posix()
    assert repository_path(root,relative)==batch
    manifest=verify_batch(batch,root=root)
    fingerprint=manifest['batch_fingerprint']
    state_path=repository_path(root,'runtime/official-validation-'+session+'/state.json')
    state=json.loads(state_path.read_bytes());work=repository_path(root,'evidence/official-validation/'+session)
    assert state.get('restored') is True and Path(state['work']).resolve()==work.resolve()
    post_path=work/'postcheck.json';post=json.loads(post_path.read_bytes())
    assert post['validation_state']==str(state_path)
    for key in ('research_box_empty','research_loader_removed','host_registry_unchanged'):
        assert post[key] is True,key
    assert not post['formal_files_changed'] and not post['host_config_files_changed']
    action_path=work/(fingerprint+'-adapter-metadata-results.json')
    action=json.loads(action_path.read_bytes())
    assert action['state_file']==str(state_path) and action['metadata_only'] is True
    assert action['boss_control_verified'] is False
    assert action['metadata_kind']=='adapter_metadata_jobs' and action['batch_fingerprint']==fingerprint
    assert action['script_sha256']==manifest['script_sha256']
    manifest_path=batch/'metadata-probe-manifest.json'
    assert action['batch_manifest_sha256']==sha(manifest_path)
    script=work/(fingerprint+'-adapter-metadata.lua')
    assert sha(script)==manifest['script_sha256'],'Retain the exact script used by this batch'
    raw_path=work/'UE4SS.log';raw=raw_path.read_text(encoding='utf-8',errors='replace')
    lines=batch_lines(raw,fingerprint)
    assert action['lines']==lines,'Action results must contain every raw batch line in exact order'
    outcomes=analyze(lines,manifest)
    assert action['all_metadata_requests_passed'] is all(row['metadata_verified'] for row in outcomes)
    sources=[state_path,post_path,action_path,raw_path,script,manifest_path,batch/'metadata-probe.lua']
    assert all(p.resolve().is_relative_to(root) for p in sources),'Closed evidence source escaped repository'
    return dict(schema_version=2,session=session,batch_fingerprint=fingerprint,batch_directory=relative,
        target_build_sha256=BUILD,metadata_only=True,playable=False,control_verified=False,
        runtime_acceptance_current=False,outcomes=outcomes,
        sources={p.relative_to(root).as_posix():sha(p) for p in sources})


def verify_receipt(target,root=None):
    """Replay closed sources; stored flags and outcomes never grant authority."""
    root=Path(root or ROOT).resolve();target=Path(target).resolve()
    receipt=json.loads(target.read_bytes())
    assert receipt['schema_version']==2 and re.fullmatch(r'[0-9a-f]{20}',receipt['batch_fingerprint'])
    expected=repository_path(root,'research/boss-adaptation/adapter-metadata-receipts/'
        +receipt['session']+'-'+receipt['batch_fingerprint']+'.json')
    assert target==expected,'Canonical closed receipt location required'
    batch=repository_path(root,receipt['batch_directory'])
    assert receipt==closed_evidence(receipt['session'],batch,root),'Closed metadata receipt drift'
    return receipt


def collect(session,batch,root=None):
    root=Path(root or ROOT).resolve()
    receipt=closed_evidence(session,batch,root)
    target=root/'research/boss-adaptation/adapter-metadata-receipts'/(session+'-'+receipt['batch_fingerprint']+'.json')
    if target.exists():
        assert json.loads(target.read_bytes())==receipt,'Preserve the existing closed metadata receipt'
    else:
        write_json(target,receipt)
    verify_receipt(target,root)
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session',nargs='?');parser.add_argument('batch',nargs='?',type=Path)
    parser.add_argument('--verify',type=Path,metavar='RECEIPT')
    args=parser.parse_args()
    if args.verify:
        assert args.session is None and args.batch is None
        verified=verify_receipt(args.verify)
        print(json.dumps(dict(verified=True,batch_fingerprint=verified['batch_fingerprint'],playable_bosses_added=0)))
    else:
        assert args.session and args.batch,'Session and batch required for collection'
        print(json.dumps(dict(receipt=str(collect(args.session,args.batch)),playable_bosses_added=0),ensure_ascii=False))
