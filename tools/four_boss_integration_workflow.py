"""Version ordinary test entry points without changing historical evidence sources."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
from boss_adaptation_workflow import ROOT,sha,write_json
from mod_installation import MANIFEST,validate_package,unlinked_path
from selection_skill_reuse import verify as previous_skills

CANDIDATE='ahua-boss-workbench-v2-dev-c5149d9c33223138'
MANIFEST_SHA='7c581fe517e7c73dd7d4132ab5e32884b997e385bc7cca77fa7cc39d49314a52'
FROZEN={'test_player_skill_batch.py':'0deb9e3d3485e569dbb0d81828f7f784b55b8e336434a7d0a22345d0b35a6430',
        'player_settings.py':'d4c4be18d92e30deeb89dbafb10399dba5cbd1c055b5d122629fbfbeda68f247'}
SOURCES=('tools/four_boss_integration_workflow.py','tools/test_four_boss_integration.py',
    'tools/collect_four_boss_integration.py','tests/test_four_boss_integration_workflow.py')


def modules(manifest):
    return {n.removeprefix('PBZBossControl/Scripts/'):d for n,d in manifest['files'].items()
        if n.startswith('PBZBossControl/Scripts/')and n!='PBZBossControl/Scripts/main.lua'}


def verify_current(current,root=ROOT):
    target=root/'runtime/release-candidates'/CANDIDATE
    manifest=validate_package(target);assert sha(target/MANIFEST)==MANIFEST_SHA
    assert current==modules(manifest),'Exact four-Boss deployment required'
    for n,d in manifest['four_boss_sources'].items():assert sha(root/n)==d
    base=root/'runtime/release-candidates'/manifest['previous_four_boss_candidate']
    prior=validate_package(base);assert sha(base/MANIFEST)==manifest['previous_four_boss_manifest_sha256']
    old=modules(prior);changes={n for n,d in old.items()if current.get(n)!=d}
    assert changes=={'boss_catalog.lua'}
    assert set(current)-set(old)=={'profiles/youlong.lua','profiles/youlong_bindings.lua'}
    before=(base/'PBZBossControl/Scripts/boss_catalog.lua').read_bytes()
    after=(target/'PBZBossControl/Scripts/boss_catalog.lua').read_bytes()
    addition=b"    {id='056_youlong',name="
    lines=after.splitlines(keepends=True);added=[l for l in lines if l.startswith(addition)]
    assert len(added)==1 and after.replace(added[0],b'')==before
    proofs,sources=previous_skills(old,root)
    receipt=root/manifest['youlong_attempt_receipt']
    assert sha(receipt)==manifest['youlong_attempt_receipt_sha256']
    accepted=json.loads(receipt.read_text(encoding='utf-8'))
    assert accepted['base_control_accepted']and accepted['formal_postcheck_passed']and not accepted['playable']
    for n,d in accepted['sources'].items():assert sha(root/n)==d
    return proofs,dict(sources,**{receipt.relative_to(root).as_posix():sha(receipt)})


def render(root=ROOT):
    header='import sys\nsys.dont_write_bytecode=True\nfrom pathlib import Path\nsys.path.append('+repr(str(root/'tools'))+')\n'
    files={}
    for name,d in FROZEN.items():
        path=root/'tools'/name;assert sha(path)==d,'Frozen ordinary source changed: '+name
        source=path.read_bytes().decode('utf-8')
        if name=='player_settings.py':
            anchor='ROOT=Path(__file__).resolve().parents[1]';assert source.count(anchor)==1
            source=source.replace(anchor,'from boss_adaptation_workflow import ROOT')
            anchor="'073_yanqiansui':'琴女烟千岁'}";assert source.count(anchor)==1
            source=source.replace(anchor,"'073_yanqiansui':'琴女烟千岁','056_youlong':'发狂的水行帮主：游龙'}")
            anchor="    import player_keymap\n    return {slot:LABELS[slot]for slot in player_keymap.read()['skills']}"
            assert source.count(anchor)==1
            source=source.replace(anchor,"    if boss_id=='056_youlong':\n        return {'slot1':'游龙中攻击01','heavy_01':'游龙重攻击01','skill_02':'游龙左闪攻击','dash':'游龙右闪攻击'}\n"+anchor)
        files[name]=(header+source).encode('utf-8');ast.parse(files[name].decode('utf-8'))
    return files


def expected(root=ROOT):
    files=render(root)
    candidate=root/'runtime/release-candidates'/CANDIDATE
    verify_current(modules(validate_package(candidate)),root)
    manifest={'candidate':CANDIDATE,'candidate_manifest_sha256':MANIFEST_SHA,
        'source_files':{n:sha(root/n)for n in SOURCES},'frozen_sources':FROZEN,
        'files':{n:hashlib.sha256(v).hexdigest()for n,v in files.items()},
        'ordinary_switching_accepted':False,'game_started':False}
    fingerprint=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:16]
    return manifest,files,fingerprint


def build(root=ROOT):
    manifest,files,fingerprint=expected(root)
    target=root/'runtime/integration-workflows'/('four-boss-'+fingerprint)
    if not target.exists():
        target.mkdir(parents=True)
        for n,b in files.items():(target/n).write_bytes(b)
        write_json(target/'manifest.json',manifest)
    verify(target,root);return target


def verify(target,root=ROOT):
    target=unlinked_path(target)
    assert target.parent==(root/'runtime/integration-workflows').resolve()
    manifest,files,fingerprint=expected(root)
    assert target.name=='four-boss-'+fingerprint
    assert json.loads((target/'manifest.json').read_text(encoding='utf-8'))==manifest
    assert {p.name for p in target.iterdir()}==set(files)|{'manifest.json'}
    for n,b in files.items():assert (target/n).read_bytes()==b
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--verify',type=Path);args=p.parse_args()
    target=args.verify or build();verify(target)
    print(json.dumps({'workflow':str(target),'installed':False,'game_started':False},ensure_ascii=False))
