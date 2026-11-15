"""Run a frozen metadata batch only on an idle, owned, protected research carrier."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import ahua_practice as practice
import official_validation as v
import research_game_menu as menu
from boss_adaptation_workflow import OUT, BUILD


def main(batch):
    owner,state=practice.owned_session()
    if owner.get('phase')!='game_launched' or state.get('boss_lifecycle_experiment'):
        raise RuntimeError('Idle research launch required; never overwrite a live control assembly')
    if not state.get('readonly_ai_experiment')or time.time()>state['deadline_unix']-120:
        raise RuntimeError('Bounded idle read-only carrier required')
    manifest=json.loads((batch/'identity-probe-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('ability_requests'):
        from build_boss_followup_batch import verify
        verify(batch)
    raw=(batch/'identity-probe.lua').read_bytes()
    if manifest['target_build_sha256']!=BUILD or hashlib.sha256(raw).hexdigest()!=manifest['script_sha256']:
        raise RuntimeError('Frozen identity probe differs from source receipt')
    v.verify_build(state['ue4ss_loader_manifest'])
    if v.c.baseline.formal_files()!=state['formal_before']:
        raise RuntimeError('Formal file changes preserved; no probe deployed')
    row=next(r for r in state['ue4ss_loader_manifest']if r['physical_path'].replace('\\','/').endswith('/PBZObserveAI/Scripts/main.lua'))
    target=Path(row['physical_path']);work=Path(state['work'])
    (work/'before-multi-boss-identity.lua').write_bytes(target.read_bytes())
    (work/'multi-boss-identity.lua').write_bytes(raw)
    log=practice.log_path(state);offset=len(log.read_text(encoding='utf-8',errors='replace'))
    row['sha256']=hashlib.sha256(raw).hexdigest();v.save(v.state_path(),state)
    target.write_bytes(raw);v.verify_build(state['ue4ss_loader_manifest'])
    menu.click(0,0,2560,1600,'observe_reload')
    text=practice.wait_tokens(log,['PBZ_MULTI_ID:END='],timeout=100,offset=offset)
    lines=[line for line in text.splitlines()if 'PBZ_MULTI_ID:'in line or (
        manifest.get('ability_requests') and 'PBZ_BOSS_META:'in line)]
    result={'at':v.utc8(),'state_file':str(v.state_path()),'script_sha256':row['sha256'],
        'batch_manifest_sha256':manifest['batch_manifest_sha256'],'lines':lines,
        'metadata_only':True,'boss_control_verified':False,
        'all_metadata_requests_passed':not any('PBZ_MULTI_ID:REJECTED='in line for line in lines)}
    v.save(work/'multi-boss-identity-results.json',result)
    v.save(v.ROOT/'evidence/adaptation/multi-boss-identity-results.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--batch',type=Path)
    args=parser.parse_args()
    batch=args.batch or Path(json.loads((OUT/'batches/latest.json').read_text(encoding='utf-8'))['directory'])
    main(batch)
