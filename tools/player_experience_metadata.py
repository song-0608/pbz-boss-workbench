"""Stage or collect an immutable metadata batch; UI reload is a separate action."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import ahua_practice as practice
import official_validation as v
from boss_metadata_jobs import verify_batch, analyze
from collect_boss_metadata_jobs import batch_lines


def context(batch):
    owner,state=practice.owned_session()
    assert owner['phase']=='game_launched' and not state.get('boss_lifecycle_experiment')
    assert state.get('readonly_ai_experiment') and state.get('readonly_hot_reload_enabled')
    assert state['deadline_unix']-time.time()>120
    manifest=verify_batch(batch)
    assert v.c.baseline.formal_files()==state['formal_before']
    v.verify_build(state['ue4ss_loader_manifest'])
    return state,manifest


def main(action,batch):
    state,manifest=context(batch);work=Path(state['work'])
    stem=manifest['batch_fingerprint']+'-adapter-metadata'
    pending=work/(stem+'-pending.json')
    captured=work/(stem+'.lua');result_path=work/(stem+'-results.json')
    path=practice.log_path(state)
    if action=='stage':
        assert not any(p.exists()for p in (pending,captured,result_path)), 'Preserve every metadata attempt'
        row=next(r for r in state['ue4ss_loader_manifest']
            if r['physical_path'].replace('\\','/').endswith('/PBZObserveAI/Scripts/main.lua'))
        target=Path(row['physical_path']);raw=(batch/'metadata-probe.lua').read_bytes()
        (work/('before-'+stem+'.lua')).write_bytes(target.read_bytes());captured.write_bytes(raw)
        v.save(pending,dict(state_file=state['state_file'],batch=str(batch),
            log_offset=len(path.read_text(encoding='utf-8',errors='replace')),
            manifest_sha256=hashlib.sha256((batch/'metadata-probe-manifest.json').read_bytes()).hexdigest()))
        row['sha256']=hashlib.sha256(raw).hexdigest();v.save(v.state_path(),state)
        target.write_bytes(raw);v.verify_build(state['ue4ss_loader_manifest'])
        print(json.dumps(dict(staged=True,input_sent=False,reload_key='Control_L+r',
            fingerprint=manifest['batch_fingerprint']),ensure_ascii=False))
    else:
        assert not result_path.exists(), 'Preserve existing metadata result'
        staged=practice.read(pending)
        assert staged['state_file']==state['state_file'] and staged['batch']==str(batch)
        raw=path.read_text(encoding='utf-8',errors='replace')[staged['log_offset']:]
        lines=batch_lines(raw,manifest['batch_fingerprint']);outcomes=analyze(lines,manifest)
        result=dict(at=v.utc8(),state_file=state['state_file'],script_sha256=manifest['script_sha256'],
            batch_manifest_sha256=staged['manifest_sha256'],lines=lines,metadata_only=True,
            boss_control_verified=False,all_metadata_requests_passed=all(r['metadata_verified']for r in outcomes),
            metadata_kind='adapter_metadata_jobs',batch_fingerprint=manifest['batch_fingerprint'])
        assert hashlib.sha256(captured.read_bytes()).hexdigest()==manifest['script_sha256']
        v.save(result_path,result)
        print(json.dumps(dict(result=str(result_path),requests=len(outcomes),
            verified=sum(r['metadata_verified']for r in outcomes),
            characters=[r for r in outcomes if r['role']=='character'],
            rejected=[r for r in outcomes if not r['metadata_verified']]),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('stage','collect'));parser.add_argument('batch',type=Path)
    args=parser.parse_args();main(args.action,args.batch.resolve())
