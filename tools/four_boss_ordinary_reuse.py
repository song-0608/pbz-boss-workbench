"""Only exact already-closed ordinary deployment may skip the accepted eight actions."""
import json
from boss_adaptation_workflow import ROOT,sha
from four_boss_integration_workflow import verify_current
from collect_multi_boss_switching import exact_role_proof
from candidate_effect_scope import local_effect

RECEIPT='research/boss-adaptation/developer-attempt-receipts/four-boss-youlong-20261116-080111.json'


def verify(current,root=ROOT):
    verify_current(current,root)
    path=root/RECEIPT;receipt=json.loads(path.read_text(encoding='utf-8'))
    assert receipt['ordinary_skills_verified']and receipt['ordinary_roundtrip_verified']and receipt['formal_postcheck_passed']
    assert not receipt['native_player_menu_verified']and not receipt['new_profile_world_cycle_verified']and not receipt['playable']
    assert receipt['module_source_sha256']==current,'Changed execution cannot reuse ordinary skill proof'
    for n,d in receipt['sources'].items():assert sha(root/n)==d
    raw=(root/'evidence/official-validation/20261116-080111/UE4SS.log').read_text(encoding='utf-8',errors='replace')
    actions=json.loads((root/'evidence/official-validation/20261116-080111/player-extra-skill-actions.json').read_text(encoding='utf-8'))
    accepted=[p for p in receipt['actions']if p['boss']=='056_youlong'][:8]
    assert [(p['skill'],p['interrupt'])for p in accepted]==[(s,i)for i in(False,True)for s in('skill_01','heavy_01','skill_02','dash')]
    for p in accepted:
        rows=[r for r in actions if r['log_offset']==p['log_offset']and r['log_end']==p['log_end']];assert len(rows)==1
        row=rows[0];a,b=row['log_offset'],row['log_end']
        assert row['passed']and row['cast_dispatched']and row['lines']==raw[a:b].splitlines()
        proof=local_effect(exact_role_proof(raw,row,'056_youlong',p['exact_granted_class']),raw[a:b],3000)
        assert proof['local_displacement_verified']
        assert proof['active_cancel_and_restoration']if row['interrupt']else proof['natural_completion']and proof['restoration']['passed']
        assert dict(proof,boss='056_youlong',skill=row['skill'],interrupt=row['interrupt'],log_offset=a,log_end=b)==p
    return accepted,{RECEIPT:sha(path)}
