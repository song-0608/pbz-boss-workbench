"""Freeze the experience trial entry points without installing or changing the accepted v4."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

import boss_skill_player_workflow as previous
import build_player_experience_candidate as candidate
from boss_adaptation_workflow import ROOT, sha, write_json
from mod_installation import MANIFEST, unlinked_path

SOURCES=('tools/player_experience_workflow.py','tests/test_player_experience_workflow.py')


def candidate_mod_root(directory):
    directory=unlinked_path(directory)
    candidate.verify(directory)
    return directory/'PBZBossControl'


def render(directory,root=ROOT):
    files=previous.render(root)
    source=files['run_control_lifecycle_probe.py'].decode('utf-8')
    source=candidate.replace(source,'from mod_installation import active_mod_root',
        'from player_experience_workflow import candidate_mod_root\n'
        'def active_mod_root():\n    return candidate_mod_root(Path('+repr(str(directory))+'))')
    files['run_control_lifecycle_probe.py']=source.encode('utf-8')
    # A new optional control is defaulted in this version only; keep historical keymap sources immutable.
    source=(root/'tools/player_keymap.py').read_text(encoding='utf-8')
    source=candidate.replace(source,'ROOT=Path(__file__).resolve().parents[1]',
                             'from boss_adaptation_workflow import ROOT')
    source=candidate.replace(source,"CONTROLS={'enter','exit','cycle_target'}",
                             "CONTROLS={'enter','exit','cycle_target','lock_target'}")
    normalize=('def with_lock_default(data):\n'
        "    if isinstance(data,dict) and isinstance(data.get('controls'),dict):\n"
        "        return dict(data,controls={'lock_target':'MIDDLE_MOUSE_BUTTON',**data['controls']})\n"
        '    return data\n\n\n')
    source=candidate.replace(source,'def validate(data):\n',normalize+'def validate(data):\n    data=with_lock_default(data)\n')
    source=candidate.replace(source,'    validate(data)\n', '    data=with_lock_default(data)\n    validate(data)\n')
    files['player_keymap.py']=('import sys\nsys.dont_write_bytecode=True\n'+source).encode('utf-8')
    for name,data in files.items():ast.parse(data.decode('utf-8'),filename=name)
    return files


def expected(directory,root=ROOT):
    candidate.verify(directory,root);files=render(directory,root)
    manifest=dict(schema=1,candidate=str(directory),candidate_manifest_sha256=sha(directory/MANIFEST),
        sources={name:sha(root/name) for name in SOURCES},
        files={name:hashlib.sha256(data).hexdigest() for name,data in files.items()},
        installed=False,game_started=False,developer_only=True,runtime_verified=False)
    fingerprint=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:16]
    return manifest,files,'player-experience-'+fingerprint


def build(directory,root=ROOT):
    manifest,files,name=expected(directory,root);target=root/'runtime/integration-workflows'/name
    if not target.exists():
        target.mkdir(parents=True)
        for name,data in files.items():(target/name).write_bytes(data)
        write_json(target/'manifest.json',manifest)
    verify(target,root);return target


def verify(target,root=ROOT):
    target=unlinked_path(target)
    assert target.parent==(root/'runtime/integration-workflows').resolve()
    recorded=json.loads((target/'manifest.json').read_bytes())
    manifest,files,name=expected(Path(recorded['candidate']),root)
    assert target.name==name and recorded==manifest
    assert {p.name for p in target.iterdir()}==set(files)|{'manifest.json'}
    assert all((target/name).read_bytes()==data for name,data in files.items())
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('candidate',type=Path);args=parser.parse_args()
    target=build(args.candidate.resolve())
    print(json.dumps(dict(workflow=str(target),game_started=False,installed=False),ensure_ascii=False))
