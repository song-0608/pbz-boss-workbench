"""Build a four-Boss player candidate only from independently replayed skill receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import boss_skill_expansion as expansion
from build_boss_profile_candidate import lua
from collect_boss_skill_campaign import save_campaign
from boss_adaptation_workflow import ROOT,sha,write_json
from mod_installation import MANIFEST,assert_closed,validate_package

PROFILES={'057_wanjun':'wanjun','073_yanqiansui':'yanqiansui','056_youlong':'youlong'}
BASE='ahua-boss-workbench-v3-f7034432a74d819b'
SOURCES=('tools/build_boss_skill_workbench.py','tests/test_boss_skill_workbench.py',
         'tools/collect_boss_skill_campaign.py','tests/test_boss_skill_campaign.py')
SOURCES=(*SOURCES,'tools/collect_boss_skill_retry_session.py','tests/test_boss_skill_retry_session.py')


def additions(actions,accepted,evidence):
    assert len(actions)==4 and set(accepted)=={a['test_id'] for a in actions}
    skills={};bindings=[];keys=set()
    for action in actions:
        proof=accepted[action['test_id']];slot=action['player_slot']
        assert proof['class_path']==action['class_path']
        assert all(proof[k] is True for k in ('activation_runtime_verified','natural_completion_verified',
            'cancellation_runtime_verified'))
        assert proof['gameplay_verified'] is True or proof['movement_runtime_verified'] is True
        assert expansion.PLAYER_SLOTS[action['key']]==slot and slot not in skills and action['key'] not in keys
        skills[slot]=dict(proof,name=action['name'],binding_verified=True,active_count_field='ActiveCount',
            requires_target=True,cancel_binding_verified=True,cancel_function='K2_CancelAbility',
            evidence=evidence,cancellation_evidence=evidence)
        bindings.append(dict(slot=slot,id=slot,key=action['key'],requires_cancel=True));keys.add(action['key'])
    return skills,bindings


def patch_profile(base,skills):
    assert base.lstrip().startswith(b'--') or base.lstrip().startswith(b'return ')
    tail='\nlocal profile=(function()\n'
    result=tail.encode()+base+b'\nend)()\n'
    for slot,definition in skills.items():
        result+=('assert(profile.skills['+lua(slot)+']==nil,"Duplicate expanded skill")\n'
                 +'profile.skills['+lua(slot)+']='+lua(definition)+'\n').encode('utf-8')
    return result+b'return profile\n'


def patch_bindings(base,bindings):
    result=b'local bindings=(function()\n'+base+b'\nend)()\n'
    result+=('local extra='+lua(bindings)+'\n').encode('utf-8')
    result+=b'''local slots,keys={},{}
for _,row in ipairs(bindings)do slots[row.slot]=true;keys[row.key]=true end
for _,row in ipairs(extra)do
 assert(not slots[row.slot] and not keys[row.key],'Duplicate expanded binding')
 slots[row.slot]=true;keys[row.key]=true;bindings[#bindings+1]=row
end
return bindings
'''
    return result


def expected(sessions,root=ROOT):
    receipt_path,receipt=save_campaign(sessions,root,verify=True)
    assert expansion.read(receipt_path)==receipt and receipt['all_twelve_accepted'] is True
    source=root/'releases'/BASE;base=validate_package(source)
    assert base['status']=='release' and base['complete_mod'] and base['runtime_acceptance_current']
    assert base['release_id']==BASE
    payload={n:(source/n).read_bytes() for n in base['files']}
    catalog_name='PBZBossControl/Scripts/boss_catalog.lua';catalog=payload[catalog_name].decode('utf-8')
    reports={r['id']:r for r in receipt['bosses']};assert set(reports)==set(PROFILES)
    evidence=receipt_path.relative_to(root).as_posix()
    for identifier,name in PROFILES.items():
        row=reports[identifier];assert row['all_four_accepted']
        bundle=expansion.read(Path(row['bundle'])/'manifest.json')
        skills,bindings=additions(bundle['skill_expansion']['actions'],row['accepted_skills'],row['evidence'])
        profile='PBZBossControl/Scripts/profiles/'+name+'.lua'
        binding='PBZBossControl/Scripts/profiles/'+name+'_bindings.lua'
        payload[profile]=patch_profile(payload[profile],skills)
        payload[binding]=patch_bindings(payload[binding],bindings)
        pattern=r"(\{id='"+re.escape(identifier)+r"',name=[^\r\n]*,abilities=)4(,bindings_count=)4(\},)"
        catalog,count=re.subn(pattern,lambda m:m[1]+'8'+m[2]+'8'+m[3],catalog)
        assert count==1,'Exact base Boss catalog row required'
    payload[catalog_name]=catalog.encode('utf-8')
    payload['PBZBossControl/README.md']+=(
        '\n技能扩展开发候选：万钧、烟千岁、游龙各新增四项已独立验收的原生技能。'
        'F5、F8、F9、Q对应各角色新增招式；阿花维持原有键位。'
        '共52项能力、53个绑定。普通玩家键位、切换和切图尚待本候选实机验收，不能作为正式发布版交付。\n'
    ).encode('utf-8')
    files={n:hashlib.sha256(data).hexdigest() for n,data in payload.items()}
    manifest=dict(base,status='development',complete_mod=False,runtime_acceptance_current=False,
        accepted_candidate=None,files=files,previous_release=base['release_id'],
        previous_release_manifest_sha256=sha(source/MANIFEST),ability_count=52,skill_binding_count=53,
        skill_session=evidence,skill_session_sha256=sha(receipt_path),
        skill_expansion_sources={n:sha(root/n) for n in SOURCES},
        pending=['Ordinary player keys, Boss switching, scene-cycle and shared runtime acceptance'],
        bosses=[dict(row,abilities=8,bindings=8) if row['id'] in PROFILES else row for row in base['bosses']])
    for name in ('acceptance_report','acceptance_report_sha256','local_checks_sha256'):
        manifest.pop(name,None)
    fingerprint=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:16]
    identifier='ahua-boss-workbench-v4-dev-'+fingerprint;manifest['release_id']=identifier
    return manifest,payload,identifier


def verify(target,root=ROOT):
    manifest=validate_package(target)
    campaign=expansion.read(root/manifest['skill_session'])
    current,payload,identifier=expected(campaign['sessions'],root)
    assert Path(target).resolve()==(root/'runtime/release-candidates'/identifier).resolve()
    assert manifest==current,'Skill workbench differs from independently replayed inputs'
    for name,data in payload.items():assert (target/name).read_bytes()==data
    return manifest


def build(sessions,root=ROOT):
    assert_closed(root);save_campaign(sessions,root)
    manifest,payload,identifier=expected(sessions,root)
    target=root/'runtime/release-candidates'/identifier
    if target.exists():
        assert validate_package(target)==manifest
    else:
        target.mkdir(parents=True)
        for name,data in payload.items():
            path=target/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        write_json(target/MANIFEST,manifest)
    assert verify(target,root)==manifest
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sessions',nargs='+');args=parser.parse_args()
    print(json.dumps(dict(candidate=str(build(args.sessions)),playable=False,installed=False,game_started=False),ensure_ascii=False))
