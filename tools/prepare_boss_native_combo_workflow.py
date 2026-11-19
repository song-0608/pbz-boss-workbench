"""Prepare the protected native-combo workflow offline; staging and input stay separate."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

from boss_adaptation_workflow import ROOT,sha,write_json
from build_player_experience_candidate import replace
from mod_installation import unlinked_path
import prepare_boss_inventory_workflow as inventory_workflow
import boss_native_combo_candidate as bundle

SOURCES=('tools/prepare_boss_native_combo_workflow.py','tests/test_boss_native_combo_workflow.py')


def render(root=ROOT):
    original=inventory_workflow.render(root)
    result={}
    for name,raw in original.items():
        source=raw.decode('utf-8')
        source=source.replace('inventory_ui_controller','combo_ui_controller')
        source=source.replace('boss_inventory_bundle','boss_native_combo_candidate')
        source=source.replace('prepare_boss_inventory_workflow','prepare_boss_native_combo_workflow')
        source=source.replace('inventory_skill_ui_stage','native_combo_ui_stage')
        source=source.replace('inventory-skill-ui','native-combo-ui')
        if name=='stage_candidate.py':
            source=replace(source,'choices='+repr(inventory_workflow.bundle.candidate_ids(root)),
                           'choices='+repr(bundle.candidate_ids(root)))
            source=replace(source,'            from boss_inventory_spawn_repair import overrides\n'
                           '            module_overrides.update(overrides())',
                           '            from boss_native_combo_candidate import overrides\n'
                           '            module_overrides.update(overrides(args.boss_candidate_bundle))')
            source=source.replace('unique leaf grants','unique subtree parent grant')
        ast.parse(source,filename=name)
        result[name.replace('inventory_ui_controller','combo_ui_controller')
                   .replace('inventory_skill_gate','combo_skill_gate')]=source.encode('utf-8')
    return result


def source_hashes(root=ROOT):
    sources=inventory_workflow.source_hashes(root)
    sources.update({name:sha(root/name) for name in (*SOURCES,*bundle.SOURCES)})
    return sources


def expected(target,root=ROOT):
    identifier=bundle.read(target/'manifest.json')['definition']['id']
    return dict(id=identifier,candidate_grant=bundle.validate(identifier,target,root=root),
        generator_sha256=sha(root/'tools/prepare_boss_native_combo_workflow.py'),
        validator_sha256=sha(root/'tools/boss_native_combo_candidate.py')),None,None


def expected_modules(record,root=ROOT):
    release=bundle.read(root/'releases'/bundle.spawn.BASE/'pbz-release.json')
    prefix='PBZBossControl/Scripts/'
    modules={n.removeprefix(prefix):h for n,h in release['files'].items()
             if n.startswith(prefix) and n.endswith('.lua') and n!=prefix+'main.lua'}
    current=bundle.modules(record['definition'],root)
    assert set(current)<=set(modules),'historical deployer can only override existing modules'
    hashes={name:hashlib.sha256(raw).hexdigest() for name,raw in current.items()}
    assert record['overrides']==hashes and record['module_sha256']==hashes['boss_candidate.lua']
    modules.update(hashes)
    return modules


def build(target,root=ROOT):
    target=unlinked_path(target)
    parent,_,_=expected(target,root)
    files=render(root)
    record=dict(schema=1,kind='native_combo_ui_stage',id=parent['id'],bundle=str(target),
        bundle_manifest_sha256=sha(target/'manifest.json'),parent_workflow_manifest=parent,
        source_files=source_hashes(root),files={n:hashlib.sha256(raw).hexdigest() for n,raw in files.items()},
        developer_only=True,playable=False,game_started=False,ui_input_sent=False)
    key=hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest()[:16]
    output=root/'runtime/developer-workflows'/('native-combo-ui-'+parent['id']+'-'+key)
    output.mkdir(parents=True,exist_ok=True)
    for name,raw in {**files,'manifest.json':(json.dumps(record,ensure_ascii=False,indent=2)+'\n').encode('utf-8')}.items():
        path=output/name
        if path.exists():assert path.read_bytes()==raw,'preserve frozen native combo workflow'
        else:path.write_bytes(raw)
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('candidate',type=Path)
    args=parser.parse_args()
    print(json.dumps(dict(workflow=str(build(args.candidate.resolve())),game_started=False,playable=False),ensure_ascii=False,indent=2))
