"""Independent single-player skill expansions from closed native-grant evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT,BUILD,sha,write_json
from build_boss_profile_candidate import lua
from collect_boss_candidate_acceptance import candidate_interval
from mod_installation import active_mod_root,assert_closed,unlinked_path

QUEUE='research/boss-adaptation/skill-expansion-queue.json'
SOURCES=('tools/boss_skill_expansion.py','tools/boss_skill_candidate.lua',QUEUE,
    'tests/test_boss_skill_expansion.py','tests/test_boss_skill_candidate.lua')
TEMP_IDS=('skill_01','heavy_01','skill_02','dash')
PLAYER_SLOTS={'F5':'skill_06','F8':'skill_08','F9':'skill_07','Q':'teleport_left'}

def read(path):return json.loads(Path(path).read_bytes())
def digest(data):return hashlib.sha256(data).hexdigest()

def checked(root,name,expected):
    path=(root/name).resolve()
    assert path.is_relative_to(root.resolve()) and sha(path)==expected,'Evidence changed: '+name
    return path

def definition(identifier,root=ROOT):
    queue=read(root/QUEUE);assert queue['schema']==1
    selected=[row for row in queue['bosses'] if row['id']==identifier]
    assert len(selected)==1,'Unregistered skill expansion'
    row=selected[0];session=row['baseline_session']
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    report_path=root/'evidence/official-validation'/session/'boss-candidate-acceptance.json'
    report=read(report_path)
    assert report['id']==identifier and report['target_build_sha256']==BUILD
    assert report['base_control_accepted'] is True and report['playable'] is False
    for name,expected in report['sources'].items():checked(root,name,expected)
    identity=report['metadata_identity']
    assert identity['identity_verified'] and identity['id']==identifier
    identity_path=checked(root,identity['receipt'],identity['receipt_sha256'])
    identity_receipt=read(identity_path)
    assert identity_receipt['target_build_sha256']==BUILD and identity_receipt['metadata_only'] is True
    assert any(item['id']==identifier and item['identity_verified'] and all(item[k]==identity[k]
        for k in ('class_path','config_path','display_name')) for item in identity_receipt['candidates'])
    for name,expected in identity_receipt['sources'].items():checked(root,name,expected)
    log_path=report_path.parent/'UE4SS.log'
    assert log_path.relative_to(root).as_posix() in {n.replace('\\','/') for n in report['sources']}
    raw=log_path.read_text(encoding='utf-8',errors='replace');begin,_=candidate_interval(raw,identifier)
    granted=set(re.findall(r'GRANTED_ABILITY=[^ ]+ ([^\r\n]+)',raw[begin:]))
    accepted={entry['class_path'] for entry in report['accepted_skills'].values()}
    assert len(row['actions'])==4
    paths=[];actions=[];seen_ids=set();seen_keys=set()
    prefix=identity['class_path'].split('/BP_',1)[0]+'/'
    for index,action in enumerate(row['actions']):
        short=action['class_short']
        assert short not in queue['blocked_class_shorts'],'Scene/passive expansion action blocked'
        assert re.fullmatch(r'[A-Za-z0-9_]+_C',short)
        matches=[path for path in granted if path.rsplit('.',1)[-1]==short and path.startswith(prefix)]
        assert len(matches)==1,'One exact historical native grant required: '+short
        path=matches[0]
        assert path not in accepted and path not in paths,'Already accepted or duplicate expansion action'
        assert action['id'] not in seen_ids and action['key'] not in seen_keys
        assert re.fullmatch(r'extra_[a-z0-9_]{1,40}',action['id']) and action['key'] in ('F5','F8','F9','Q')
        assert action['player_slot']==PLAYER_SLOTS[action['key']]
        assert isinstance(action['name'],str) and 1<=len(action['name'])<=40
        paths.append(path);seen_ids.add(action['id']);seen_keys.add(action['key'])
        actions.append(dict(action,class_path=path,test_id=TEMP_IDS[index],
            historical_native_grant_observed=True,current_leaf_verified=False,current_live_grant_verified=False,
            activation_verified=False,natural_completion_verified=False,cancellation_verified=False,
            effect_verified=False,playable=False))
    evidence={p.relative_to(root).as_posix():sha(p) for p in (report_path,log_path,identity_path)}
    projection=dict(id=identifier,target_build_sha256=BUILD,metadata_only=True,playable=False,
        actions=actions,sources=evidence,current_leaf_verified=False,current_live_grants_verified=False)
    metadata_digest=digest(json.dumps(projection,sort_keys=True).encode())
    value={k:identity[k] for k in ('id','class_path','config_path','display_name')}
    value.update(exe_sha256=BUILD,identity_receipt_sha256=sha(identity_path),
        ability_metadata_receipt_sha256=metadata_digest,ability_pool=paths,
        action_names={a['test_id']:a['name'] for a in actions},
        blocked_scene_abilities=queue['blocked_class_shorts'],max_local_displacement_cm=3000)
    return value,projection

def render(value,root=ROOT):
    return ('local definition='+lua(value)+'\n').encode('utf-8')+(root/'tools/boss_skill_candidate.lua').read_bytes()

def build(identifier,root=ROOT):
    assert_closed(root);value,projection=definition(identifier,root)
    base=active_mod_root(root);module=render(value,root)
    manifest=dict(schema_version=1,id=identifier,target_build_sha256=BUILD,developer_only=True,playable=False,
        auto_deploy=False,definition=value,skill_expansion=projection,
        source_files={name:sha(root/name) for name in SOURCES},
        base_mod_files={p.relative_to(base).as_posix():sha(p) for p in sorted(base.rglob('*.lua'))},
        overrides={'Scripts/boss_candidate.lua':digest(module)})
    fingerprint=digest(json.dumps(manifest,sort_keys=True).encode())[:16]
    target=root/'research/boss-adaptation/skill-bundles'/(identifier+'-'+fingerprint)
    if not target.exists():
        target.mkdir(parents=True);(target/'boss_candidate.lua').write_bytes(module);write_json(target/'manifest.json',manifest)
    validate(identifier,target,root=root)
    return target

def validate(identifier,bundle,base=None,root=ROOT):
    bundle=unlinked_path(bundle)
    assert bundle.parent==(root/'research/boss-adaptation/skill-bundles').resolve()
    assert {p.name for p in bundle.iterdir()}=={'manifest.json','boss_candidate.lua'}
    manifest=read(bundle/'manifest.json');value,projection=definition(identifier,root)
    assert bundle.name==identifier+'-'+digest(json.dumps(manifest,sort_keys=True).encode())[:16]
    assert manifest['id']==identifier and manifest['schema_version']==1 and manifest['target_build_sha256']==BUILD
    assert manifest['developer_only'] is True and manifest['playable'] is False and manifest['auto_deploy'] is False
    assert manifest['definition']==value and manifest['skill_expansion']==projection
    assert manifest['source_files']=={name:sha(root/name) for name in SOURCES}
    base=base or active_mod_root(root)
    assert manifest['base_mod_files']=={p.relative_to(base).as_posix():sha(p) for p in sorted(base.rglob('*.lua'))}
    module=bundle/'boss_candidate.lua'
    assert module.read_bytes()==render(value,root)
    assert manifest['overrides']=={'Scripts/boss_candidate.lua':sha(module)}
    return dict(boss_candidate=identifier,identity_receipt_sha256=value['identity_receipt_sha256'],
        ability_metadata_receipt_sha256=value['ability_metadata_receipt_sha256'],
        developer_max_displacement_cm=3000,developer_bundle_sha256=sha(bundle/'manifest.json'))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('identifier');parser.add_argument('--verify',type=Path)
    args=parser.parse_args();target=args.verify or build(args.identifier)
    print(json.dumps(dict(bundle=str(target),grant=validate(args.identifier,target),game_started=False,playable=False),ensure_ascii=False))
