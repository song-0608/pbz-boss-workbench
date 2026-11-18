"""Keep a private game-authored research checkpoint outside the disposable box."""
import argparse
import json
from pathlib import Path
import shutil
import time
import uuid
import official_validation as v
import ahua_practice as practice
from mod_installation import unlinked_path
from stage_phantom_boss_pair import save_snapshot,copy_snapshot

LABEL='悲泣溪谷—斧老大斩落处'


def storage():
    config=practice.read(v.ROOT/'runtime/research-storage.json')
    return unlinked_path(Path(config['project_storage'])/'研究场景存档')


def capture():
    owner,state=practice.owned_session()
    assert owner['phase']=='game_launched', 'Capture before Mod assembly'
    assert 'SPAWN_ATTEMPT=' not in practice.log_path(state).read_text(encoding='utf-8',errors='replace')
    assert v.c.baseline.formal_files()==state['formal_before']
    v.c.isolation.select_box('PBZSteamLab');dll=v.c.isolation.api()
    v.c.isolation.check_policy(dll,allow_offline_validation=True)
    container=unlinked_path(v.c.isolation.get_root(dll))
    source=unlinked_path(v.c.isolation.virtual_file(container,v.c.baseline.GAME/'ProjectPBZ/Saved'))
    assert source.is_relative_to(container)
    snapshot=save_snapshot(source);time.sleep(1);assert save_snapshot(source)==snapshot
    root=storage();root.mkdir(parents=True,exist_ok=True)
    target=root/('斧老大斩落处-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    copy_snapshot(source,target,snapshot)
    record=dict(schema=1,label=LABEL,directory=str(target),files=snapshot,state_file=state['state_file'],
        captured_at=v.utc8(),game_authored=True,formal_files_modified=False,reload_verified=False)
    v.save(target/'checkpoint.json',record);v.save(root/'当前研究场景.json',record)
    assert v.c.baseline.formal_files()==state['formal_before']
    print(json.dumps(dict(saved=str(target),label=LABEL,files=len(snapshot)),ensure_ascii=False))


def apply():
    owner,state=practice.owned_session()
    assert owner['phase']=='prepared' and not state.get('ue4ss_deployed')
    assert not v.c.preflight.games_running(), 'Apply only before game launch'
    assert v.c.baseline.formal_files()==state['formal_before']
    root=storage();pointer=root/'当前研究场景.json'
    if not pointer.exists():return
    record=practice.read(pointer);source=unlinked_path(record['directory'])
    assert source.parent==root and record['schema']==1 and record['label']==LABEL
    assert practice.read(source/'checkpoint.json')==record and save_snapshot(source)==record['files']
    v.c.isolation.select_box('PBZSteamLab');dll=v.c.isolation.api()
    v.c.isolation.check_policy(dll,allow_offline_validation=True)
    container=unlinked_path(v.c.isolation.get_root(dll))
    target=unlinked_path(v.c.isolation.virtual_file(container,v.c.baseline.GAME/'ProjectPBZ/Saved'))
    assert target.is_relative_to(container)
    backup=Path(state['work'])/'before-research-checkpoint'
    before=save_snapshot(target);copy_snapshot(target,backup,before)
    for name in record['files']:
        destination=unlinked_path(target/name);assert destination.is_relative_to(target)
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/name,destination)
    actual=save_snapshot(target)
    assert all(actual.get(name)==row for name,row in record['files'].items())
    assert v.c.baseline.formal_files()==state['formal_before']
    v.save(Path(state['work'])/'research-checkpoint-applied.json',dict(checkpoint=record,
        previous_research_backup=str(backup),formal_files_modified=False))
    print('已装载研究起点：'+LABEL,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('capture','apply','prepare'))
    parser.add_argument('--acceptance',action='store_true')
    parser.add_argument('--observed-ui',action='store_true',help='Prepare without legacy UI control; complete via prepare_research_ui.py')
    args=parser.parse_args()
    if args.action=='capture':capture()
    elif args.action=='apply':apply()
    else:
        if args.observed_ui:
            from prepare_research_ui import prepare
            print(json.dumps(prepare(args.acceptance),ensure_ascii=False,indent=2))
        elif args.acceptance:
            from prepare_offline_acceptance import prepare
            prepare()
            apply()
        else:
            practice.prepare()
            apply()
