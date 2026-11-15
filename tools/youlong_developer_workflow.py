"""Generate an isolated workflow revision without editing source-matched historical tools."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
from boss_adaptation_workflow import ROOT,sha,write_json
from mod_installation import unlinked_path
import youlong_developer_bundle as bundle

FROZEN={
    'ahua_practice.py':'d77ab6485eea48e11c09aac8e42a2cb57eedaf1ce01a8ed3a34c58971673a431',
    'run_control_lifecycle_probe.py':'816672ec788f7872a37a29a3567cb4261f5fe8c5483e60e1fb2f8a3328c147f2',
    'test_player_skill_batch.py':'0deb9e3d3485e569dbb0d81828f7f784b55b8e336434a7d0a22345d0b35a6430',
    'run_boss_candidate_milestone.py':'311b7483af00d56024d426d968be68a2eb09a62df1659cee778d1ecc6552e524',
    'collect_boss_candidate_acceptance.py':'cca1dd53e47d69d75e005c535056daf0638d17c070aa3f0b9ab8863dbf5e12cb'}
SOURCES=('tools/youlong_developer_workflow.py','tests/test_youlong_developer_workflow.py')


def replace_once(text,old,new):
    assert text.count(old)==1,'Frozen workflow anchor changed: '+old
    return text.replace(old,new)


def render(root=ROOT):
    header=('import sys\nsys.dont_write_bytecode=True\nfrom pathlib import Path\nsys.path.append('+repr(str(root/'tools'))+')\n').encode('utf-8')
    files={}
    for name,digest in FROZEN.items():
        path=root/'tools'/name;assert sha(path)==digest,'Historical workflow changed: '+name
        text=path.read_bytes().decode('utf-8')
        if name in ('ahua_practice.py','run_control_lifecycle_probe.py'):
            text=replace_once(text,"choices=('057_wanjun','073_yanqiansui')","choices=('056_youlong',)")
        if name=='ahua_practice.py':
            text=replace_once(text,'ROOT = Path(__file__).resolve().parents[1]','from boss_adaptation_workflow import ROOT')
            text=replace_once(text,"str(ROOT / 'tools' / name)",
                "str(Path(__file__).with_name(name) if Path(__file__).with_name(name).is_file() else ROOT / 'tools' / name)")
        elif name=='run_boss_candidate_milestone.py':
            text=replace_once(text,"str(practice.ROOT/'tools/test_player_skill_batch.py')",
                "str(Path(__file__).with_name('test_player_skill_batch.py'))")
        elif name=='collect_boss_candidate_acceptance.py':
            text=replace_once(text,'from build_boss_developer_bundle import validate','from youlong_developer_bundle import validate')
            text=replace_once(text,'output=work/\'boss-candidate-acceptance.json\';write_json(output,result)',
                "output=work/'boss-candidate-acceptance.json';assert not output.exists(),'Preserve collected attempt';write_json(output,result)")
        files[name]=header+text.encode('utf-8')
    files['boss_candidate_gate.py']=header+b'''
from boss_adaptation_workflow import ROOT
def validate(identifier,root=ROOT,bundle=None):
    if identifier!='056_youlong' or bundle is None:
        raise RuntimeError('Explicit frozen YouLong developer bundle required; no player promotion')
    from youlong_developer_bundle import validate as verify
    return verify(identifier,bundle,root=root)
'''
    for name,data in files.items():ast.parse(data.decode('utf-8'),filename=name)
    return files


def expected(bundle_path,root=ROOT):
    grant=bundle.validate(bundle.ID,bundle_path,root=root)
    files=render(root)
    manifest={'schema':1,'id':bundle.ID,'developer_only':True,'playable':False,'game_started':False,
        'bundle':str(bundle_path.resolve()),'bundle_manifest_sha256':sha(bundle_path/'manifest.json'),
        'candidate_grant':grant,'historical_source_sha256':FROZEN,
        'source_files':{n:sha(root/n)for n in SOURCES},
        'files':{n:hashlib.sha256(v).hexdigest()for n,v in files.items()},
        'scope':'Versioned Python entry points only; existing isolation, expiry and cleanup gates unchanged.'}
    fingerprint=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:16]
    return manifest,files,fingerprint


def build(bundle_path=None,root=ROOT):
    bundle_path=bundle_path or bundle.build(root)
    manifest,files,fingerprint=expected(bundle_path,root)
    target=root/'runtime/developer-workflows'/('youlong-'+fingerprint)
    if not target.exists():
        target.mkdir(parents=True)
        for name,data in files.items():(target/name).write_bytes(data)
        write_json(target/'manifest.json',manifest)
    verify(target,root)
    return target


def verify(target,root=ROOT):
    target=unlinked_path(target)
    assert target.parent==(root/'runtime/developer-workflows').resolve()
    manifest=bundle.read(unlinked_path(target/'manifest.json'))
    bundle_path=unlinked_path(Path(manifest['bundle']))
    expected_manifest,files,fingerprint=expected(bundle_path,root)
    assert target.name=='youlong-'+fingerprint and manifest==expected_manifest
    assert {p.name for p in target.iterdir()}==set(files)|{'manifest.json'}
    for name,data in files.items():assert unlinked_path(target/name).read_bytes()==data
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=Path);parser.add_argument('--verify',type=Path)
    args=parser.parse_args();target=args.verify or build(args.bundle)
    verify(target)
    print(json.dumps({'workflow':str(target),'game_started':False,'playable':False},ensure_ascii=False))
