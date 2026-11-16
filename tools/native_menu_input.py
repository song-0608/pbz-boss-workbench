"""Bounded native-menu input variant; preserve all original isolation and restoration gates."""
import argparse
import hashlib
import json
from pathlib import Path
import types
from boss_adaptation_workflow import ROOT

FROZEN='23bce61f4175c8160d3c9e2c99bfd2adf592ec3bc996deef020c22ae54cfe751'


def variant():
    path=ROOT/'tools/research_game_menu.py';data=path.read_bytes()
    assert hashlib.sha256(data).hexdigest()==FROZEN
    source=data.decode('utf-8')
    old='u.keybd_event(key,0,0,0);time.sleep(.08);u.keybd_event(key,0,2,0)'
    assert source.count(old)==1
    source=source.replace(old,'u.keybd_event(key,0,0,0);time.sleep(.35);u.keybd_event(key,0,2,0)')
    module=types.ModuleType('bounded_native_menu_variant');module.__file__=str(path)
    exec(compile(source,str(path),'exec'),module.__dict__)
    return module


def click(purpose):
    assert purpose in('observe_pause','control_menu_pause')
    result=variant().click(0,0,2560,1600,purpose)
    import official_validation as v
    state=json.loads(v.state_path().read_text(encoding='utf-8'))
    path=Path(state['work'])/'native-menu-input-actions.json'
    actions=json.loads(path.read_text(encoding='utf-8'))if path.exists()else[]
    actions.append({'at':v.utc8(),'state_file':state['state_file'],'purpose':purpose,
        'key':'ESC','seconds':.35,'original_source_sha256':FROZEN,'result':result})
    v.save(path,actions);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('purpose',choices=('observe_pause','control_menu_pause'));a=p.parse_args()
    print(json.dumps(click(a.purpose),ensure_ascii=False))
