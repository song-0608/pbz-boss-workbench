"""Versioned expansion workflow; historical sources and runtime gates stay frozen."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

from boss_adaptation_workflow import ROOT,sha,write_json
from mod_installation import unlinked_path
import youlong_developer_workflow as previous
import expanded_boss_developer_bundle as bundle

SOURCES=('tools/expanded_boss_developer_workflow.py','tests/test_expanded_boss_developer.py',
         'tools/youlong_developer_workflow.py','tests/test_youlong_developer_workflow.py')


def render(root=ROOT):
    files=previous.render(root)
    for name,data in list(files.items()):
        text=data.decode('utf-8')
        if name in ('ahua_practice.py','run_control_lifecycle_probe.py'):
            text=previous.replace_once(text,"choices=('056_youlong',)",'choices='+repr(tuple(bundle.REVIEWS)))
        elif name=='test_player_skill_batch.py':
            text=previous.replace_once(text,
                "        dossier=practice.read(practice.ROOT/'research/boss-adaptation/dossiers'/(identifier+'.json'))\n        boss_name=dossier['metadata_identity']['display_name']",
                "        from expanded_boss_developer_bundle import definition\n        boss_name=definition(identifier)[0]['display_name']")
        elif name=='run_boss_candidate_milestone.py':
            text=previous.replace_once(text,
                "boss_name=practice.read(practice.ROOT/'research/boss-adaptation/dossiers'/(identifier+'.json'))['metadata_identity']['display_name']",
                "boss_name=__import__('expanded_boss_developer_bundle').definition(identifier)[0]['display_name']")
        elif name=='collect_boss_candidate_acceptance.py':
            text=previous.replace_once(text,'from youlong_developer_bundle import validate','from expanded_boss_developer_bundle import validate')
            text=previous.replace_once(text,
                "    metadata_path=ROOT/'research/boss-adaptation/dossiers'/(identifier+'.json')\n    metadata=json.loads(metadata_path.read_text(encoding='utf-8'))['metadata_identity']",
                "    from expanded_boss_developer_bundle import definition\n    metadata=definition(identifier)[0]")
        files[name]=text.encode('utf-8')
    header='import sys\nsys.dont_write_bytecode=True\nsys.path.append('+repr(str(root/'tools'))+')\n'
    files['boss_candidate_gate.py']=(header+'''
from boss_adaptation_workflow import ROOT
def validate(identifier,root=ROOT,bundle=None):
    from expanded_boss_developer_bundle import REVIEWS,validate as verify
    if identifier not in REVIEWS or bundle is None:
        raise RuntimeError('Explicit reviewed and frozen expansion bundle required')
    return verify(identifier,bundle,root=root)
''').encode('utf-8')
    for name,data in files.items():ast.parse(data.decode('utf-8'),filename=name)
    return files


def expected(bundle_path,root=ROOT):
    identifier=bundle.read(bundle_path/'manifest.json')['id'];grant=bundle.validate(identifier,bundle_path,root=root)
    files=render(root)
    manifest=dict(schema=1,id=identifier,bundle=str(bundle_path),bundle_manifest_sha256=sha(bundle_path/'manifest.json'),
        candidate_grant=grant,source_files={n:sha(root/n)for n in SOURCES},historical_source_sha256=previous.FROZEN,
        files={n:hashlib.sha256(v).hexdigest()for n,v in files.items()},developer_only=True,
        playable=False,game_started=False,runtime_acceptance_current=False)
    key=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:16]
    return manifest,files,'expanded-'+identifier+'-'+key


def build(bundle_path,root=ROOT):
    bundle_path=unlinked_path(bundle_path);manifest,files,name=expected(bundle_path,root)
    target=root/'runtime/developer-workflows'/name
    if not target.exists():
        target.mkdir(parents=True)
        for name,data in files.items():(target/name).write_bytes(data)
        write_json(target/'manifest.json',manifest)
    verify(target,root);return target


def verify(target,root=ROOT):
    target=unlinked_path(target);assert target.parent==(root/'runtime/developer-workflows').resolve()
    recorded=bundle.read(target/'manifest.json');manifest,files,name=expected(Path(recorded['bundle']),root)
    assert target.name==name and recorded==manifest
    assert {p.name for p in target.iterdir()}==set(files)|{'manifest.json'}
    assert all(unlinked_path(target/n).read_bytes()==data for n,data in files.items())
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);a=p.parse_args()
    print(json.dumps(dict(workflow=str(build(a.bundle.resolve())),game_started=False,playable=False),ensure_ascii=False))
