"""Freeze ordinary player entry points for the evidence-gated skill candidate."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

import build_boss_skill_workbench as candidate
import four_boss_integration_workflow as ordinary
import youlong_developer_workflow as historical
from boss_adaptation_workflow import ROOT, sha, write_json
from mod_installation import MANIFEST, unlinked_path

SOURCES=('tools/boss_skill_player_workflow.py','tests/test_boss_skill_player_workflow.py')


def render(root=ROOT):
    header=('import sys\nsys.dont_write_bytecode=True\nfrom pathlib import Path\n'
            'sys.path.append('+repr(str(root/'tools'))+')\n')
    files=ordinary.render(root)
    for name in ('ahua_practice.py','run_control_lifecycle_probe.py'):
        path=root/'tools'/name
        assert sha(path)==historical.FROZEN[name], 'Historical player entry changed'
        source=path.read_bytes().decode('utf-8')
        if name=='ahua_practice.py':
            source=historical.replace_once(source,'ROOT = Path(__file__).resolve().parents[1]',
                'from boss_adaptation_workflow import ROOT')
            source=historical.replace_once(source,"str(ROOT / 'tools' / name)",
                "str(Path(__file__).with_name(name) if Path(__file__).with_name(name).is_file() else ROOT / 'tools' / name)")
        files[name]=(header+source).encode('utf-8')
    for name,data in files.items():ast.parse(data.decode('utf-8'),filename=name)
    return files


def expected(package,root=ROOT):
    manifest=candidate.verify(package,root);files=render(root)
    receipt=dict(schema=1,candidate=str(package.resolve()),candidate_manifest_sha256=sha(package/MANIFEST),
        sources={name:sha(root/name) for name in SOURCES},
        files={name:hashlib.sha256(data).hexdigest() for name,data in files.items()},
        developer_only=True,game_started=False,playable=False)
    fingerprint=hashlib.sha256(json.dumps(receipt,sort_keys=True).encode()).hexdigest()[:16]
    return receipt,files,'skills-player-'+fingerprint


def build(package,root=ROOT):
    receipt,files,name=expected(package,root);target=root/'runtime/integration-workflows'/name
    if not target.exists():
        target.mkdir(parents=True)
        for name,data in files.items():(target/name).write_bytes(data)
        write_json(target/'manifest.json',receipt)
    verify(target,root);return target


def verify(target,root=ROOT):
    target=unlinked_path(target)
    assert target.parent==(root/'runtime/integration-workflows').resolve()
    recorded=json.loads((target/'manifest.json').read_text(encoding='utf-8'))
    receipt,files,name=expected(Path(recorded['candidate']),root)
    assert target.name==name and recorded==receipt
    assert {p.name for p in target.iterdir()}==set(files)|{'manifest.json'}
    for name,data in files.items():assert (target/name).read_bytes()==data
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate',type=Path);args=parser.parse_args()
    print(json.dumps(dict(workflow=str(build(args.candidate.resolve())),game_started=False)))
