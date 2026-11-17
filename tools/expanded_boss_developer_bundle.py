"""Freeze explicitly reviewed expansion identities and bounded native-leaf pools."""
import argparse
import hashlib
import json
from pathlib import Path

from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from build_boss_profile_candidate import lua
from collect_boss_metadata_jobs import verify_receipt
from mod_installation import active_mod_root, unlinked_path, assert_closed

RECEIPTS=tuple('research/boss-adaptation/adapter-metadata-receipts/20261117-182116-'+key+'.json'
    for key in ('8e2bb30e7158df46abec','360daae591e51f1dfd37','12306a27f634e63420ae'))
PREFIX='/PBZCombatAsset/ActorData/Mobs/'
# Reviewed against closed CDO observations. No variant is selected by array order.
REVIEWS={
    '071_xianzhe':dict(folder='071_XianZhe',actor='BP_Monster_XianZhe',
        config='ActorConfig/ActorC_XianZhe',display_name='弦儿',
        priority=('GA_XianZhe_Skill_05_C','GA_XianZhe_Skill_06_C','GA_XianZhe_Skill_07_C',
                  'GA_XianZhe_Dodge_B_C','GA_XianZhe_Dodge_L_C')),
    '058_maddoctor':dict(folder='058_MadDoctor',actor='BP_Monster_Maddoctor_Elite',
        config='ActorData/ActorC_MadDoctor_Elite',display_name='神医：谢秋冬',
        priority=('GA_MadDoctor_LightAttack_01_C','GA_MadDoctor_HeavyAttack_01_C',
                  'GA_MadDoctor_Skill_03_C','GA_MadDoctor_Dodge_F_C','GA_MadDoctor_Dodge_B_C')),
    '067_motian':dict(folder='067_MoTian',actor='BP_Monster_MoTian',
        config='ActorConfig/ActorC_MoTian',display_name='暗魔天堡之主：魔渊',
        priority=('GA_MoTian_LightAttack_01_C','GA_MoTian_HeavyAttack_01_C','GA_MoTian_Skill_02_C',
                  'GA_MoTian_Dodge_R_C','GA_MoTian_Skill_03_C','GA_MoTian_Skill_07_C')),
}
SOURCES=('tools/expanded_boss_developer_bundle.py','tools/boss_developer_candidate.lua',
         'tools/collect_boss_metadata_jobs.py','tools/boss_metadata_jobs.py',
         'tests/test_expanded_boss_developer.py','tests/test_expanded_boss_candidate.lua')


def read(path):return json.loads(path.read_bytes())


def definition(identifier,root=ROOT):
    assert identifier in REVIEWS,'Explicit reviewed expansion identifier required'
    review=REVIEWS[identifier];base=PREFIX+review['folder']+'/'
    actor=base+review['actor']+'.'+review['actor']+'_C'
    config=base+review['config']+'.'+review['config'].rsplit('/',1)[-1]
    observations=[];evidence={}
    for name in RECEIPTS:
        receipt=verify_receipt(root/name,root)
        relevant=[row for row in receipt['outcomes']if row['id']==identifier]
        if relevant:
            evidence[name]=sha(root/name)
            observations.extend((row,name)for row in relevant)
    identities=[(row,name)for row,name in observations if row['role']=='character'and row['class_path']==actor]
    assert len(identities)==1,'One exact closed character observation required'
    identity,identity_source=identities[0]
    assert identity['metadata_verified']is True and identity['config_in_observed_candidates']is True
    assert identity['observed_config']==config and identity['display_name']==review['display_name']
    assert identity['display_name']not in ('None','NA','N/A','')
    assert identity['lineage'][0]==actor and '/Script/ProjectPBZ.PBZCharacter_NPC'in identity['lineage']
    abilities=[(row,name)for row,name in observations if row['role']=='ability']
    assert len({row['class_path']for row,_ in abilities})==len(abilities),'Conflicting/repeated metadata needs review'
    pool=[];skill_sources=set()
    for short in review['priority']:
        found=[(row,name)for row,name in abilities if row['class_path'].rsplit('.',1)[-1]==short]
        assert len(found)==1,'Exact reviewed ability observation required: '+short
        row,name=found[0]
        assert row['metadata_verified']is True and row['ability_kind']=='leaf'
        assert row['class_path'].startswith(base+'Ability/')and '/BulletData/'not in row['class_path']
        assert not any(row[k]for k in ('identity_verified','live_grant_verified','activation_verified','playable'))
        pool.append(row['class_path']);skill_sources.add(name)
    # A single immutable receipt anchors the bounded pool; never hash an unverified latest report.
    assert len(skill_sources)==1
    value=dict(id=identifier,class_path=actor,config_path=config,display_name=review['display_name'],
        identity_receipt_sha256=evidence[identity_source],
        ability_metadata_receipt_sha256=evidence[next(iter(skill_sources))],ability_pool=pool,
        blocked_scene_abilities=sorted(row['class_path']for row,_ in abilities if row['class_path']not in pool),
        max_local_displacement_cm=3000)
    return value,evidence


def render(value,root=ROOT):
    return ('local definition='+lua(value)+'\n').encode('utf-8')+(root/'tools/boss_developer_candidate.lua').read_bytes()


def expected(identifier,root=ROOT,base=None):
    value,evidence=definition(identifier,root);base=base or active_mod_root(root);module=render(value,root)
    manifest=dict(schema_version=1,id=identifier,target_build_sha256=BUILD,developer_only=True,playable=False,
        auto_deploy=False,definition=value,evidence=evidence,source_files={n:sha(root/n)for n in SOURCES},
        base_mod_files={p.relative_to(base).as_posix():sha(p)for p in sorted(base.rglob('*.lua'))},
        overrides={'Scripts/boss_candidate.lua':hashlib.sha256(module).hexdigest()},
        scope='Reviewed exact CDO identity; unique idle native grants; no player promotion or manual grants.')
    key=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:16]
    return manifest,module,identifier+'-'+key


def build(identifier,root=ROOT):
    assert_closed(root);manifest,module,name=expected(identifier,root)
    target=root/'research/boss-adaptation/developer-bundles'/name
    if not target.exists():
        target.mkdir(parents=True);(target/'boss_candidate.lua').write_bytes(module);write_json(target/'manifest.json',manifest)
    validate(identifier,target,root=root);return target


def validate(identifier,bundle,base=None,root=ROOT):
    assert identifier in REVIEWS,'Only an explicitly reviewed candidate is allowed'
    target=unlinked_path(bundle)
    assert target.parent==(root/'research/boss-adaptation/developer-bundles').resolve()
    manifest,module,name=expected(identifier,root,base)
    assert target.name==name and {p.name for p in target.iterdir()}=={'manifest.json','boss_candidate.lua'}
    assert read(target/'manifest.json')==manifest and unlinked_path(target/'boss_candidate.lua').read_bytes()==module
    definition=manifest['definition']
    return dict(boss_candidate=identifier,identity_receipt_sha256=definition['identity_receipt_sha256'],
        ability_metadata_receipt_sha256=definition['ability_metadata_receipt_sha256'],
        developer_max_displacement_cm=definition['max_local_displacement_cm'],developer_bundle_sha256=sha(target/'manifest.json'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('identifier',choices=REVIEWS);p.add_argument('--verify',type=Path)
    a=p.parse_args();target=a.verify.resolve()if a.verify else build(a.identifier)
    print(json.dumps(dict(bundle=str(target),grant=validate(a.identifier,target),game_started=False,playable=False),ensure_ascii=False))
