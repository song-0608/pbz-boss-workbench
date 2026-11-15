"""Stage exact accepted YouLong native actions; ordinary workbench acceptance stays separate."""
import argparse
import json
import re
from boss_adaptation_workflow import ROOT,BUILD,sha,write_json
from build_boss_profile_candidate import lua
from build_yanqiansui_profile import checked,camera_from
import youlong_developer_bundle as bundle

SLOTS=(('slot1','skill_01','F1','中攻击01','MiddleAttack_01'),
       ('heavy_01','heavy_01','F2','重攻击01','HeavyAttack_01'),
       ('skill_02','skill_02','F3','左闪攻击','DodgeAttack_L'),
       ('dash','dash','F4','右闪攻击','DodgeAttack_R'))


def validate_report(report):
    assert report['id']==bundle.ID and report['target_build_sha256']==BUILD
    assert report['base_control_accepted']is True and report['playable']is False
    assert report['stability']['passed']is True
    assert set(report['cleanup'])=={'boss','boss_controller','target','target_controller','extra_target','extra_target_controller'}
    assert all(v is True for v in report['cleanup'].values())
    assert all(report['movement_camera'][k]is True for k in('movement_verified','camera_rotation_verified','milestone_passed'))
    accepted=report['accepted_skills'];assert set(accepted)=={r[1]for r in SLOTS}
    for _,skill,_,_,native in SLOTS:
        row=accepted[skill]
        path='/PBZCombatAsset/ActorData/Mobs/056_YouLong/Ability/Abilities/GA_YouLong_'+native+'.GA_YouLong_'+native+'_C'
        assert row['class_path']==path and row['natural_completion_verified']is True
        assert row['cancellation_runtime_verified']is True
        assert row['gameplay_verified']is True or row['movement_runtime_verified']is True
    return accepted


def build(session,root=ROOT):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    receipt_path=root/'research/boss-adaptation/developer-attempt-receipts'/('youlong-'+session+'.json')
    receipt=bundle.read(receipt_path)
    assert receipt['id']==bundle.ID and receipt['target_build_sha256']==BUILD
    assert receipt['base_control_accepted']and receipt['formal_postcheck_passed']and receipt['live_grants_verified']
    assert receipt['playable']is False and receipt['ordinary_switching_accepted']is False and receipt['world_cycle_verified']is False
    sources={n:checked(root,n,d)for n,d in receipt['sources'].items()}
    state=root/'runtime'/('official-validation-'+session)/'state.json'
    assert state.resolve()in sources.values()and bundle.read(state)['restored']
    work=root/'evidence/official-validation'/session
    post=work/'postcheck.json';assert post.resolve()in sources.values()
    p=bundle.read(post)
    assert p['validation_state']==str(state)and p['research_box_empty']and p['research_loader_removed']and p['host_registry_unchanged']
    assert not p['formal_files_changed']and not p['host_config_files_changed']
    path=work/'boss-candidate-acceptance.json';assert path.resolve()in sources.values()
    report=bundle.read(path);accepted=validate_report(report)
    assert report['module_source_sha256']==receipt['module_source_sha256']
    assert all(receipt['bindings'][s]==r['class_path']for s,r in accepted.items())
    manifests=[p for p in sources.values()if p.name=='manifest.json'and p.parent.parent.name=='developer-bundles']
    assert len(manifests)==1
    manifest=bundle.read(manifests[0]);definition=manifest['definition']
    assert manifest['id']==bundle.ID and manifest['target_build_sha256']==BUILD and manifest['developer_only']and not manifest['playable']
    module=manifests[0].parent/'boss_candidate.lua'
    assert module.resolve()in sources.values()and sha(module)==report['module_source_sha256']['boss_candidate.lua']
    identity=report['metadata_identity']
    assert identity['identity_verified']and all(identity[k]==definition[k]for k in('id','class_path','config_path','display_name'))
    checked(root,identity['receipt'],identity['receipt_sha256'])
    evidence=path.relative_to(root).as_posix()
    profile={k:definition[k]for k in('id','class_path','config_path','display_name')}
    profile.update(exe_sha256=BUILD,identity_verified=True,identity_evidence=identity['receipt'],
        control_verified=True,skill_timeout_seconds=30,remote_target_verified=True,possession_roundtrip_verified=True,
        movement_position_changed_verified=True,training_target_profile='profiles.ahua',
        candidate_acceptance_evidence=evidence,candidate_acceptance_sha256=sha(path),
        requires_ordinary_switching_acceptance=True,camera=camera_from(module.read_text(encoding='utf-8')),
        input={'input_verified':True,'mouse_scale':0.1},skills={})
    bindings=[]
    for slot,skill,key,label,_ in SLOTS:
        profile['skills'][skill]=dict(accepted[skill],name='游龙'+label,binding_verified=True,active_count_field='ActiveCount',
            requires_target=True,cancel_binding_verified=True,cancel_function='K2_CancelAbility',
            activation_runtime_verified=True,evidence=evidence,cancellation_evidence=evidence)
        bindings.append({'slot':slot,'id':skill,'key':key,'requires_cancel':True})
    contents={'youlong.lua':'-- Independent base accepted; ordinary switching remains required.\nreturn '+lua(profile)+'\n',
        'youlong_bindings.lua':'-- Four independently accepted native actions only.\nreturn '+lua(bindings)+'\n'}
    target=root/'runtime/staged-boss-profiles'/('youlong-'+sha(path)[:16]);target.mkdir(parents=True,exist_ok=True)
    for name,content in contents.items():
        output=target/name;payload=content.encode('utf-8')
        if output.exists():assert output.read_bytes()==payload,'Preserve staged profile'
        else:output.write_bytes(payload)
    value={'id':bundle.ID,'base_control_accepted':True,'ordinary_switching_accepted':False,'playable':False,
        'player_registry_modified':False,'evidence':evidence,'evidence_sha256':sha(path),
        'attempt_receipt':receipt_path.relative_to(root).as_posix(),'attempt_receipt_sha256':sha(receipt_path),
        'generator_sha256':sha(root/'tools/build_youlong_profile.py'),'files':{n:sha(target/n)for n in contents}}
    manifest_path=target/'profile-candidate.json'
    if manifest_path.exists():assert bundle.read(manifest_path)==value
    else:write_json(manifest_path,value)
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('session');args=parser.parse_args()
    print(json.dumps({'staged_directory':str(build(args.session)),'player_registry_modified':False,'playable':False},ensure_ascii=False))
