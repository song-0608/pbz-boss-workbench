"""Generate an integration candidate only from independently accepted, closed Boss evidence."""
import argparse
import json
from pathlib import Path
import re
import shutil
from boss_adaptation_workflow import ROOT,BUILD,sha,write_json
from boss_candidate_gate import validate as validate_identity

SLOTS=[('slot1','skill_01','F1','重锤攻击'),('heavy_01','heavy_01','F2','左闪攻击'),
       ('skill_02','skill_02','F3','右闪攻击'),('dash','dash','F4','左侧攻击')]


def lua(value):
    if value is True:return 'true'
    if value is False:return 'false'
    if value is None:return 'nil'
    if isinstance(value,(int,float)):return str(value)
    if isinstance(value,str):return json.dumps(value,ensure_ascii=False)
    if isinstance(value,list):return '{'+','.join(lua(v)for v in value)+'}'
    if isinstance(value,dict):return '{'+','.join('['+lua(k)+']='+lua(v)for k,v in value.items())+'}'
    raise TypeError(type(value))


def build(session,stage=False):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    identifier='057_wanjun';validate_identity(identifier)
    report_path=ROOT/'evidence/official-validation'/session/'boss-candidate-acceptance.json'
    report=json.loads(report_path.read_text(encoding='utf-8'))
    assert report['id']==identifier and report['target_build_sha256']==BUILD
    assert report['base_control_accepted'] is True and report['playable'] is False
    for name,expected in report['sources'].items():assert sha(ROOT/name)==expected,'candidate source changed: '+name
    scripts=ROOT/'mod/PBZBossControl/Scripts'
    for name,expected in report['module_source_sha256'].items():
        assert sha(scripts/name)==expected,'runtime module changed since independent acceptance: '+name
    source=(scripts/'boss_candidate.lua').read_text(encoding='utf-8')
    camera_source=re.search(r'camera=\{([^{}]+)\}',source).group(1)
    camera={}
    for item in camera_source.split(','):
        key,value=item.strip().split('=',1)
        assert re.fullmatch(r'[a-z_]+',key)
        camera[key]=False if value=='false' else True if value=='true' else float(value) if '.' in value else int(value)
    camera['binding_verified']=True
    metadata=report['metadata_identity'];evidence=str(report_path.relative_to(ROOT)).replace('\\','/')
    profile={'id':identifier,'display_name':metadata['display_name'],'exe_sha256':BUILD,
        'identity_verified':True,'class_path':metadata['class_path'],'config_path':metadata['config_path'],
        'identity_evidence':metadata['receipt'],'control_verified':True,'skill_timeout_seconds':30,
        'remote_target_verified':True,'possession_roundtrip_verified':True,
        'movement_position_changed_verified':True,'training_target_profile':'profiles.ahua',
        'candidate_acceptance_evidence':evidence,'candidate_acceptance_sha256':sha(report_path),
        'requires_ordinary_switching_acceptance':True,'camera':camera,
        'input':{'input_verified':True,'mouse_scale':0.1},'skills':{}}
    bindings=[]
    for slot,skill,key,name in SLOTS:
        accepted=report['accepted_skills'].get(skill)
        if not accepted:continue
        assert accepted['natural_completion_verified'] and accepted['cancellation_runtime_verified']
        assert accepted['gameplay_verified'] or accepted['movement_runtime_verified']
        profile['skills'][skill]={'name':'万钧'+name,'class_path':accepted['class_path'],
            'binding_verified':True,'active_count_field':'ActiveCount','requires_target':True,
            'cancel_binding_verified':True,'cancel_function':'K2_CancelAbility',
            'activation_runtime_verified':True,'natural_completion_verified':True,
            'cancellation_runtime_verified':True,'gameplay_verified':accepted['gameplay_verified'],
            'movement_runtime_verified':accepted['movement_runtime_verified'],
            'evidence':evidence,'cancellation_evidence':evidence}
        bindings.append({'slot':slot,'id':skill,'key':key,'requires_cancel':True})
    assert bindings and bindings[0]['id']=='skill_01','an accepted primary leaf is required'
    target=ROOT/'runtime/staged-boss-profiles'/('wanjun-'+sha(report_path)[:16])
    target.mkdir(parents=True,exist_ok=True)
    contents={'wanjun.lua':'-- Independent base control accepted; player releases also require ordinary switching evidence.\nreturn '+lua(profile)+'\n',
              'wanjun_bindings.lua':'-- Only independently accepted WanJun abilities; never inherits Ahua bindings.\nreturn '+lua(bindings)+'\n'}
    for name,text in contents.items():
        path=target/name
        if path.exists():assert path.read_text(encoding='utf-8')==text,'preserve existing staged profile'
        else:path.write_text(text,encoding='utf-8')
    receipt={'id':identifier,'base_control_accepted':True,'ordinary_switching_accepted':False,
        'evidence':evidence,'evidence_sha256':sha(report_path),'files':{n:sha(target/n)for n in contents}}
    write_json(target/'profile-candidate.json',receipt)
    if stage:
        from mod_installation import assert_closed
        assert_closed()
        for name in contents:
            destination=scripts/'profiles'/name
            if destination.exists():assert sha(destination)==sha(target/name),'preserve different existing profile'
            else:shutil.copy2(target/name,destination)
    print(json.dumps({'staged_directory':str(target),'copied_to_development_source':stage,
        'skills':[r['id']for r in bindings],'player_registry_modified':False},ensure_ascii=False))
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('session');parser.add_argument('--stage',action='store_true')
    args=parser.parse_args();build(args.session,args.stage)
