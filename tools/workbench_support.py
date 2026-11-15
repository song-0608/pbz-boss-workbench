"""Exact deployed workbench capability receipt; never enables an unverified Boss."""
import json
from pathlib import Path
import re

MODULES=('boss_workbench.lua','workbench_input.lua','workbench_catalog.lua','runtime.lua','owned_arena.lua','ue_host.lua')
READY='v2|toggle=INS|up=UP_ARROW|down=DOWN_ARROW|confirm=RETURN|close=ESCAPE'
ACTIONS={'control_workbench_toggle':45,'control_workbench_up':38,'control_workbench_down':40,
         'control_workbench_confirm':13,'control_workbench_close':27}


def capability(sources,player_entry):
    if not player_entry or any(name not in sources for name in MODULES):return None
    hashes={name:sources[name]for name in MODULES}
    if any(not isinstance(value,str)or not re.fullmatch('[0-9a-f]{64}',value)for value in hashes.values()):
        raise RuntimeError('Workbench source receipt malformed')
    return {'schema':1,'ready_token':READY,'modules':hashes}


def validate_dispatch(root,state_path,owner):
    if (owner.get('phase')!='armed'or owner.get('state_file')!=str(state_path)
            or not owner.get('player_entry')or owner.get('skill_lab')or owner.get('expanded')):
        raise RuntimeError('Current ordinary player workbench required')
    state=json.loads(Path(state_path).read_text(encoding='utf-8'))
    deployment=json.loads((Path(state['work'])/'control-lifecycle-deployment.json').read_text(encoding='utf-8'))
    expected=capability(deployment.get('module_source_sha256',{}),deployment.get('player_entry'))
    if not expected or owner.get('workbench')!=expected or deployment.get('workbench')!=expected:
        raise RuntimeError('Current deployed workbench readiness receipt required')
    manifest=state.get('ue4ss_loader_manifest',[])
    for name,digest in expected['modules'].items():
        suffix='/PBZObserveAI/Scripts/'+name
        rows=[row for row in manifest if row['physical_path'].replace('\\','/').endswith(suffix)]
        if len(rows)!=1 or rows[0].get('sha256')!=digest:
            raise RuntimeError('Workbench source differs from current declared carrier')
    return expected
