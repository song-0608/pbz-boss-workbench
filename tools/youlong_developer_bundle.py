"""Freeze an independent YouLong native-grant candidate from closed metadata receipts."""
import argparse
import hashlib
import json
from pathlib import Path
from boss_adaptation_workflow import ROOT,BUILD,sha,write_json
from build_boss_profile_candidate import lua
from mod_installation import active_mod_root,unlinked_path,assert_closed

ID='056_youlong'
IDENTITY='research/boss-adaptation/identity-receipts/20261116-051216.json'
METADATA='research/boss-adaptation/ability-metadata-receipts/youlong-20261116-061722.json'
DOSSIER='research/boss-adaptation/dossiers/056_youlong.json'
SOURCES=('tools/youlong_developer_bundle.py','tools/boss_developer_candidate.lua',
         'tools/build_boss_profile_candidate.py','tests/test_youlong_developer_bundle.py',
         'tests/test_youlong_developer_candidate.lua')
PRIORITY=('GA_YouLong_MiddleAttack_01_C','GA_YouLong_HeavyAttack_01_C',
          'GA_YouLong_SpecialAttack_01_Normal_C','GA_YouLong_DodgeAttack_L_C',
          'GA_YouLong_DodgeAttack_R_C','GA_YouLong_MiddleAttack_02_C',
          'GA_YouLong_HeavyAttack_02_C','GA_YouLong_Dodge_F_C')


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def verify_sources(receipt,root):
    for name,expected in receipt['sources'].items():
        path=(root/name).resolve()
        assert path.is_relative_to(root.resolve())and sha(path)==expected,'Evidence changed: '+name


def definition(root=ROOT):
    identity=read(root/IDENTITY);metadata=read(root/METADATA);dossier=read(root/DOSSIER)
    for receipt in (identity,metadata):
        assert receipt['target_build_sha256']==BUILD and receipt['metadata_only']and receipt['playable']is False
        verify_sources(receipt,root)
    assert metadata['id']==ID and not metadata['live_grants_verified']and not metadata['activation_verified']
    rows=[r for r in identity['candidates']if r['id']==ID and r['identity_verified']]
    assert len(rows)==1;entry=rows[0];record=dossier['metadata_identity']
    assert entry['class_path']=='/PBZCombatAsset/ActorData/Mobs/056_YouLong/BP_Monster_YouLong_Harpoon.BP_Monster_YouLong_Harpoon_C'
    assert entry['config_path']=='/PBZCombatAsset/ActorData/Mobs/056_YouLong/ActorData/ActorC_YouLong_Harpoon.ActorC_YouLong_Harpoon'
    assert entry['display_name']=='发狂的水行帮主：游龙'
    assert all(entry[k]==record[k]for k in ('id','class_path','config_path','display_name'))
    assert record['identity_verified']and record['receipt_sha256']==sha(root/IDENTITY)
    observed={}
    for row in metadata['ability_metadata']:
        path=row['class_path'];assert path not in observed and row['id']==ID
        assert not row['playable']and not row['activation_verified']and not row['live_grant_verified']
        observed[path]=row
    pool=[]
    for name in PRIORITY:
        rows=[p for p,r in observed.items()if p.rsplit('.',1)[-1]==name
              and r['metadata_verified']is True and r['ability_kind']=='leaf']
        assert len(rows)==1,'Exact verified leaf required: '+name
        path=rows[0]
        assert path.startswith('/PBZCombatAsset/ActorData/Mobs/056_YouLong/Ability/Abilities/')
        pool.append(path)
    value={k:entry[k]for k in ('id','class_path','config_path','display_name')}
    value.update(identity_receipt_sha256=sha(root/IDENTITY),ability_metadata_receipt_sha256=sha(root/METADATA),
        ability_pool=pool,blocked_scene_abilities=sorted(set(observed)-set(pool)),max_local_displacement_cm=3000)
    return value,{n:sha(root/n)for n in (IDENTITY,METADATA,DOSSIER)}


def render(value,root=ROOT):
    return ('local definition='+lua(value)+'\n').encode('utf-8')+(root/'tools/boss_developer_candidate.lua').read_bytes()


def build(root=ROOT):
    assert_closed(root);value,evidence=definition(root);base=active_mod_root(root)
    module=render(value,root)
    manifest={'schema_version':1,'id':ID,'target_build_sha256':BUILD,
        'developer_only':True,'playable':False,'auto_deploy':False,'definition':value,'evidence':evidence,
        'source_files':{n:sha(root/n)for n in SOURCES},
        'base_mod_files':{p.relative_to(base).as_posix():sha(p)for p in sorted(base.rglob('*.lua'))},
        'overrides':{'Scripts/boss_candidate.lua':hashlib.sha256(module).hexdigest()},
        'scope':'Exact Harpoon identity; native unique idle leaf grants only; no manual grants or playable registration.'}
    fingerprint=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:16]
    target=root/'research/boss-adaptation/developer-bundles'/(ID+'-'+fingerprint)
    if not target.exists():
        target.mkdir(parents=True);(target/'boss_candidate.lua').write_bytes(module);write_json(target/'manifest.json',manifest)
    validate(ID,target,base,root)
    return target


def validate(identifier,bundle,base=None,root=ROOT):
    assert identifier==ID,'Explicit YouLong developer candidate required'
    bundle=unlinked_path(bundle)
    assert bundle.parent==(root/'research/boss-adaptation/developer-bundles').resolve()
    assert {p.name for p in bundle.iterdir()}=={'manifest.json','boss_candidate.lua'}
    manifest=read(unlinked_path(bundle/'manifest.json'));module=unlinked_path(bundle/'boss_candidate.lua')
    fingerprint=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:16]
    assert bundle.name==ID+'-'+fingerprint
    assert manifest['schema_version']==1 and manifest['id']==ID and manifest['target_build_sha256']==BUILD
    assert manifest['developer_only']is True and manifest['playable']is False and manifest['auto_deploy']is False
    value,evidence=definition(root)
    assert manifest['definition']==value and manifest['evidence']==evidence
    assert manifest['source_files']=={n:sha(root/n)for n in SOURCES}
    base=base or active_mod_root(root)
    assert manifest['base_mod_files']=={p.relative_to(base).as_posix():sha(p)for p in sorted(base.rglob('*.lua'))}
    assert manifest['overrides']=={'Scripts/boss_candidate.lua':sha(module)}and module.read_bytes()==render(value,root)
    return {'boss_candidate':ID,'identity_receipt_sha256':value['identity_receipt_sha256'],
        'ability_metadata_receipt_sha256':value['ability_metadata_receipt_sha256'],
        'developer_max_displacement_cm':value['max_local_displacement_cm'],'developer_bundle_sha256':sha(bundle/'manifest.json')}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify',type=Path)
    args=parser.parse_args();bundle=args.verify or build()
    print(json.dumps({'bundle':str(bundle),'grant':validate(ID,bundle),'game_started':False,'playable':False},ensure_ascii=False))
