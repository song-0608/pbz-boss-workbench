"""Version frozen single-player research entry points for an exact skill bundle."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
from boss_adaptation_workflow import ROOT,sha,write_json
from mod_installation import unlinked_path
import boss_skill_expansion as expansion
import youlong_developer_workflow as previous

SOURCES=('tools/boss_skill_workflow.py','tools/boss_skill_expansion.py',
    'tools/boss_skill_session.py','tools/collect_boss_skill_session.py','tests/test_boss_skill_session.py',
    'tests/test_boss_skill_expansion.py','tests/test_boss_skill_workflow.py')
def render(root=ROOT):
    files=previous.render(root)
    for name in ('ahua_practice.py','run_control_lifecycle_probe.py'):
        old=b"choices=('056_youlong',)";assert files[name].count(old)==1
        files[name]=files[name].replace(old,b"choices=('057_wanjun','073_yanqiansui','056_youlong')")
    name='ahua_practice.py'
    old=b"        if fatal or ended:\r\n" if b'\r\n' in files[name] else b"        if fatal or ended:\n"
    newline=b'\r\n' if b'\r\n' in files[name] else b'\n'
    assert files[name].count(old)==1
    replacement='''        if ended and not fatal:
            from boss_skill_session import complete_assembly
            if complete_assembly(data):
                current.update(phase='game_launched',skill_batch_cleanup_verified=True)
                save_owner(current)
                return
            fatal=True
        if fatal or ended:
'''.replace('\n',newline.decode()).encode()
    files[name]=files[name].replace(old,replacement)
    name='run_boss_candidate_milestone.py'
    old=b"work/'boss-candidate-milestone.json'";assert files[name].count(old)==1
    files[name]=files[name].replace(old,b"work/('boss-skill-milestone-'+identifier+'.json')")
    name='collect_boss_candidate_acceptance.py'
    old=b'from youlong_developer_bundle import validate';assert files[name].count(old)==1
    files[name]=files[name].replace(old,b'from boss_skill_expansion import validate')
    header='import sys\nsys.dont_write_bytecode=True\nsys.path.append('+repr(str(root/'tools'))+')\n'
    files['boss_candidate_gate.py']=(header+'''from boss_adaptation_workflow import ROOT
def validate(identifier,root=ROOT,bundle=None):
    if bundle is None:raise RuntimeError('Exact single-player skill expansion bundle required')
    from boss_skill_expansion import validate as verify
    return verify(identifier,bundle,root=root)
''').encode('utf-8')
    for name,data in files.items():ast.parse(data.decode('utf-8'),filename=name)
    return files
def expected(bundle,root=ROOT):
    bundle=unlinked_path(bundle);manifest=expansion.read(bundle/'manifest.json');identifier=manifest['id']
    grant=expansion.validate(identifier,bundle,root=root);files=render(root)
    receipt=dict(schema=1,id=identifier,bundle=str(bundle),bundle_manifest_sha256=sha(bundle/'manifest.json'),
        candidate_grant=grant,developer_only=True,playable=False,game_started=False,
        source_files={name:sha(root/name) for name in SOURCES},
        files={name:hashlib.sha256(data).hexdigest() for name,data in files.items()})
    fingerprint=hashlib.sha256(json.dumps(receipt,sort_keys=True).encode()).hexdigest()[:16]
    return receipt,files,'skills-'+identifier+'-'+fingerprint

def build(bundle,root=ROOT):
    receipt,files,name=expected(bundle,root)
    target=root/'runtime/developer-workflows'/name
    if not target.exists():
        target.mkdir(parents=True)
        for name,data in files.items():(target/name).write_bytes(data)
        write_json(target/'manifest.json',receipt)
    verify(target,root)
    return target

def verify(target,root=ROOT):
    target=unlinked_path(target)
    assert target.parent==(root/'runtime/developer-workflows').resolve()
    receipt=expansion.read(unlinked_path(target/'manifest.json'))
    expected_receipt,files,name=expected(Path(receipt['bundle']),root)
    assert target.name==name and receipt==expected_receipt,'Skill workflow manifest changed'
    assert {p.name for p in target.iterdir()}==set(files)|{'manifest.json'}
    for name,data in files.items():
        assert unlinked_path(target/name).read_bytes()==data,'Skill workflow file changed: '+name
    return receipt

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--bundle',type=Path);source.add_argument('--verify',type=Path)
    args=parser.parse_args();target=args.verify or build(args.bundle);verify(target)
    print(json.dumps(dict(workflow=str(target),game_started=False,playable=False),ensure_ascii=False))
