"""Reparse closed ordinary skills; allow only the exact initialization clearance patch."""
import hashlib
import json

from boss_adaptation_workflow import ROOT, BUILD, sha
from collect_multi_boss_switching import exact_role_proof
from candidate_effect_scope import local_effect
from build_yanqiansui_profile import validate_report
from build_clearance_candidate import patched

SESSION='20261116-061722'
RECEIPT='research/boss-adaptation/developer-attempt-receipts/'+SESSION+'.json'


def verify(current,root=ROOT):
    path=root/RECEIPT
    receipt=json.loads(path.read_text(encoding='utf-8'))
    assert receipt['session']==SESSION and receipt['id']=='073_yanqiansui'
    assert receipt['target_build_sha256']==BUILD and receipt['ordinary_skills_verified'] is True
    assert receipt['playable'] is False and receipt['formal_postcheck_passed'] is True
    for name,digest in receipt['sources'].items():
        source=(root/name).resolve()
        assert source.is_relative_to(root.resolve()) and sha(source)==digest,'Prior skill source changed: '+name
    old=receipt['module_source_sha256'];changed={n for n,v in old.items()if current.get(n)!=v}
    assert changed=={'owned_arena.lua'} and set(current)-set(old)=={'yanqiansui_arena_clearance.lua'}
    base=root/'runtime/release-candidates/ahua-boss-workbench-v2-dev-fc170a5ecd820768/PBZBossControl/Scripts/owned_arena.lua'
    assert sha(base)==old['owned_arena.lua']
    assert hashlib.sha256(patched(base.read_bytes().decode('utf-8')).encode('utf-8')).hexdigest()==current['owned_arena.lua']
    assert sha(root/'tools/yanqiansui_arena_clearance.lua')==current['yanqiansui_arena_clearance.lua']
    base_report=json.loads((root/'evidence/official-validation/20261116-055334/boss-candidate-acceptance.json').read_text(encoding='utf-8'))
    classes=validate_report(base_report)
    work=root/'evidence/official-validation'/SESSION
    raw=(work/'UE4SS.log').read_text(encoding='utf-8',errors='replace')
    actions=json.loads((work/'player-extra-skill-actions.json').read_text(encoding='utf-8'))
    verified=[]
    for row in actions:
        if not row['passed']:continue
        a,b=row['log_offset'],row['log_end']
        assert row['lines']==raw[a:b].splitlines()
        proof=local_effect(exact_role_proof(raw,row,'073_yanqiansui',classes[row['skill']]['class_path']),raw[a:b],3000)
        assert proof['active_cancel_and_restoration'] if row['interrupt'] else proof['natural_completion'] and proof['restoration']['passed']
        assert proof['local_displacement_verified']
        proof.update(skill=row['skill'],interrupt=row['interrupt'],log_offset=a,log_end=b)
        verified.append(proof)
    assert verified==receipt['actions']
    assert {(p['skill'],p['interrupt'])for p in verified}=={(s,i)for s in classes for i in (False,True)}
    return verified,{RECEIPT:sha(path)}
