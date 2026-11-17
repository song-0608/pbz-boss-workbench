"""Collect closed research-session metadata, preserving each batch independently."""
import argparse
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, OUT, BUILD, sha, write_json
from boss_metadata_jobs import verify_batch, analyze


def collect(session,batch):
    assert re.fullmatch(r'\d{8}-\d{6}',session),'Exact closed session identifier required'
    batch=Path(batch).resolve();manifest=verify_batch(batch)
    fingerprint=manifest['batch_fingerprint']
    state_path=ROOT/'runtime'/('official-validation-'+session)/'state.json'
    state=json.loads(state_path.read_bytes());work=ROOT/'evidence/official-validation'/session
    assert state.get('restored') is True and Path(state['work']).resolve()==work.resolve()
    post_path=work/'postcheck.json';post=json.loads(post_path.read_bytes())
    assert post['validation_state']==str(state_path)
    for key in ('research_box_empty','research_loader_removed','host_registry_unchanged'):
        assert post[key] is True,key
    assert not post['formal_files_changed'] and not post['host_config_files_changed']
    action_path=work/(fingerprint+'-adapter-metadata-results.json')
    action=json.loads(action_path.read_bytes())
    assert action['state_file']==str(state_path) and action['metadata_only'] is True
    assert action['metadata_kind']=='adapter_metadata_jobs' and action['batch_fingerprint']==fingerprint
    assert action['script_sha256']==manifest['script_sha256']
    manifest_path=batch/'metadata-probe-manifest.json'
    assert action['batch_manifest_sha256']==sha(manifest_path)
    script=work/(fingerprint+'-adapter-metadata.lua')
    assert sha(script)==manifest['script_sha256'],'Retain the exact script used by this batch'
    raw_path=work/'UE4SS.log';raw=raw_path.read_text(encoding='utf-8',errors='replace')
    cursor=0
    for line in action['lines']:
        cursor=raw.index(line,cursor)+len(line)
    outcomes=analyze(action['lines'],manifest)
    sources=[state_path,post_path,action_path,raw_path,script,manifest_path,batch/'metadata-probe.lua']
    receipt=dict(schema_version=1,session=session,batch_fingerprint=fingerprint,
        target_build_sha256=BUILD,metadata_only=True,playable=False,control_verified=False,
        runtime_acceptance_current=False,outcomes=outcomes,
        sources={p.relative_to(ROOT).as_posix():sha(p) for p in sources})
    target=OUT/'adapter-metadata-receipts'/(session+'-'+fingerprint+'.json')
    if target.exists():
        assert json.loads(target.read_bytes())==receipt,'Preserve the existing closed metadata receipt'
    else:
        write_json(target,receipt)
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session');parser.add_argument('batch',type=Path)
    args=parser.parse_args()
    print(json.dumps(dict(receipt=str(collect(args.session,args.batch)),playable_bosses_added=0),ensure_ascii=False))
