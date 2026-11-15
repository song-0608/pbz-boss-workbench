"""全部基础玩法、独立角色及工作台门槛通过后，发布固定本机离线双Boss包。"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
from collect_release_readiness import collect
from mod_installation import ROOT,MANIFEST,assert_closed,digest,validate_package


def validate_common_runtime(current,base,recovery=None):
    if current==base:
        return  # A complete independent 600-second Boss baseline was collected on these exact modules.
    allowed={'boss_catalog.lua','workbench_catalog.lua','boss_workbench.lua','ue_input.lua'}
    if current.get('ue_combat.lua')!=base.get('ue_combat.lua'):
        assert recovery and recovery.get('passed') and recovery.get('module_source_sha256')==current, \
            'changed target adapter requires current-source dead-target restoration acceptance'
        assert recovery.get('dead_target_clear_restorations') and recovery.get('requires_real_dead_target_status') \
            and recovery.get('requires_native_clear_readback_and_full_restoration')
        assert all(row.get('restoration',{}).get('passed') for row in recovery['dead_target_clear_restorations'])
        allowed.add('ue_combat.lua')
    for name,expected in base.items():
        if name not in allowed:assert current.get(name)==expected,'independent Boss adapter changed: '+name
    assert set(current)-set(base)=={'profiles/wanjun.lua','profiles/wanjun_bindings.lua'}


def release(candidate,integration_session,workbench_session,recovery_session=None,wanjun_session='20261115-100319'):
    assert_closed()
    candidate=Path(candidate).resolve();manifest=validate_package(candidate)
    readiness=collect(candidate)
    assert readiness['ready_for_release'],'all current-source Ahua gates must pass before release'
    def receipt(session,name):
        path=ROOT/'evidence/official-validation'/session/name
        result=json.loads(path.read_text(encoding='utf-8'))
        assert result['passed'] and result['module_source_sha256']==readiness['module_source_sha256']
        for relative,expected in result['sources'].items():assert digest(ROOT/relative)==expected,'receipt source changed: '+relative
        return path,result
    integration_path,integration=receipt(integration_session,'multi-boss-switching-acceptance.json')
    workbench_path,workbench=receipt(workbench_session,'boss-workbench-acceptance.json')
    assert integration['ordinary_roundtrip_verified'] and integration['input_layers_recovered']
    import re
    assert re.fullmatch(r'\d{8}-\d{6}',wanjun_session)
    base_path=ROOT/'evidence/official-validation'/wanjun_session/'boss-candidate-acceptance.json'
    base=json.loads(base_path.read_text(encoding='utf-8'))
    assert base['id']=='057_wanjun'
    assert base['base_control_accepted'] and base['stability']['passed'] and all(base['cleanup'].values())
    assert set(base['accepted_skills'])=={'skill_01','heavy_01','skill_02','dash'}
    for relative,expected in base['sources'].items():assert digest(ROOT/relative)==expected
    # Common adapters retain the independent base; the narrow lock-cleanup change
    # additionally needs a real dead-target regression and all current-source gates.
    current=readiness['module_source_sha256']
    recovery_path,recovery=(receipt(recovery_session,'workbench-recovery-acceptance.json')
        if recovery_session else (None,None))
    if recovery_path:
        from collect_workbench_recovery import proof as recovery_proof
        assert recovery_proof((recovery_path.parent/'UE4SS.log').read_text(encoding='utf-8',errors='replace'))['passed']
    legacy=json.loads((ROOT/'evidence/official-validation/20261115-100319/boss-candidate-acceptance.json').read_text(encoding='utf-8'))
    if current.get('ue_combat.lua')!=legacy['module_source_sha256'].get('ue_combat.lua'):
        assert recovery and recovery.get('passed'),'changed target adapter still requires real dead-target recovery'
    validate_common_runtime(current,base['module_source_sha256'],recovery)
    loader=(ROOT/'tools/pbz_ue4ss_baseline.py').read_text(encoding='utf-8')
    assert "'bUseUObjectArrayCache':'true' if readonly_ai else 'false'"in loader
    fingerprint=hashlib.sha256(json.dumps(current,sort_keys=True).encode()).hexdigest()
    release_id='ahua-boss-workbench-v1-'+fingerprint[:16]
    target=ROOT/'releases'/release_id
    assert not target.exists(),'preserve existing immutable release'
    report={'release_id':release_id,'at':datetime.now().astimezone().isoformat(),'passed':True,
        'scope':'current fixed PBZ build, local protected offline launcher',
        'module_source_sha256':current,'ahua_current_source':readiness,
        'wanjun_independent_base':{'path':str(base_path.relative_to(ROOT)),'sha256':digest(base_path)},
        'ordinary_switching':{'path':str(integration_path.relative_to(ROOT)),'sha256':digest(integration_path)},
        'workbench':{'path':str(workbench_path.relative_to(ROOT)),'sha256':digest(workbench_path)},
        'dead_target_recovery':({'path':str(recovery_path.relative_to(ROOT)),'sha256':digest(recovery_path)}
            if recovery_path else None),
        'performance':'native UObject cache enabled; four input FNames cached; no GPU FPS claim',
        'bosses':[{'id':'ahua_guitoudao','name':'新娘阿花','abilities':28,'bindings':29},
                  {'id':'057_wanjun','name':'巨锤客：万钧','abilities':4,'bindings':4}]}
    acceptance=ROOT/'evidence/releases'/(release_id+'-acceptance.json')
    assert not acceptance.exists()
    acceptance.parent.mkdir(parents=True,exist_ok=True)
    acceptance.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    target.mkdir(parents=True)
    for name in manifest['files']:
        destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(candidate/name,destination)
    manifest.update(release_id=release_id,status='release',complete_mod=True,
        at=report['at'],runtime_acceptance_current=True,ability_count=32,skill_binding_count=33,
        bosses=report['bosses'],accepted_candidate=readiness['release_id'],
        acceptance_report=acceptance.relative_to(ROOT).as_posix(),acceptance_report_sha256=digest(acceptance),
        local_checks_sha256=digest(ROOT/'evidence/adaptation/ahua-delivery-local-checks.json'))
    (target/MANIFEST).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    validate_package(target)
    print(json.dumps({'release':str(target),'release_id':release_id,'complete_mod':True,'bosses':2},ensure_ascii=False))
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('candidate');parser.add_argument('integration_session')
    parser.add_argument('workbench_session');parser.add_argument('--recovery-session')
    parser.add_argument('--wanjun-session',default='20261115-100319');args=parser.parse_args()
    release(args.candidate,args.integration_session,args.workbench_session,args.recovery_session,args.wanjun_session)
