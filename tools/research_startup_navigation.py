"""Native shrine/position inputs after a fully cleaned pre-spawn clearance refusal."""
import argparse
import hashlib
from pathlib import Path
import types
import research_game_menu as original
from mod_installation import active_mod_root

MENU_SHA='23bce61f4175c8160d3c9e2c99bfd2adf592ec3bc996deef020c22ae54cfe751'


def cleaned_clearance(owner,state,text):
    try:
        original.validate_startup_positioning(owner,state,text)
        return
    except RuntimeError:
        pass
    assert owner.get('phase')=='game_launched' and owner.get('state_file')==state.get('state_file')
    assert state.get('offline_validation') and not state.get('network_active')
    assert state.get('ue4ss_deployed') and not state.get('restored')
    assert 'PBZ_PRACTICE:WAITING=load your isolated scene then enable practice' in text
    attempts=text.split('PBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT=')[1:]
    assert len(attempts)==3
    for part in attempts:
        assert 'no verified 9m same-level movement clearance within 192 navigation queries' in part
        assert all('OWNED_DESTROY_VERIFIED='+n+'|engine_unusable=true' in part
                   for n in ('boss','boss_controller','target','target_controller'))
        assert not any(t in part for t in ('enter success=true','INTERACTIVE_READY=',
            'PLAYER_ENTRY_READY=','state=FAULTED','ISSUE_','DESTROY_SKIPPED'))
    assert 'PREREQUISITE_RETRY_SAFE=true' in attempts[-1]
    assert 'END=initialization rejected before takeover; original player restoration verified' in attempts[-1]
    # This exact refusal occurs before the additional target allocation in this release.
    source=active_mod_root()/'Scripts/owned_arena.lua'
    baseline=original.v.ROOT/'releases/ahua-boss-workbench-v3-f7034432a74d819b/PBZBossControl/Scripts/owned_arena.lua'
    assert source.read_bytes()==baseline.read_bytes()
    code=source.read_text(encoding='utf-8')
    assert code.index('if not layout then construction_rejected=true;error(reason)end') < code.index('if index==2 then extra_targets')


def dispatch(action):
    path=Path(original.__file__);data=path.read_bytes()
    assert hashlib.sha256(data).hexdigest()==MENU_SHA
    old="'practice_position_back':83}.get(purpose)"
    source=data.decode('utf-8');assert source.count(old)==1
    source=source.replace(old,"'practice_position_back':83,'practice_shrine_interact':69}.get(purpose)")
    module=types.ModuleType('bounded_startup_navigation');module.__file__=str(path)
    exec(compile(source,str(path)+':startup_navigation','exec'),module.__dict__)
    module.validate_startup_positioning=cleaned_clearance
    purpose={'interact':'practice_shrine_interact','back':'practice_position_back',
             'left':'practice_position_left','forward':'practice_position_forward'}[action]
    return module.click(0,0,2560,1600,purpose)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('interact','back','left','forward'));args=parser.parse_args()
    print(dispatch(args.action))
