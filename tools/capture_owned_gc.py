"""只读跟踪本轮相机对象的UObject数组槽；引擎失效与真正释放分别记录。"""
import argparse
import json
from pathlib import Path
import re
import time
import ahua_practice as practice
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('capture','check'));args=parser.parse_args()
    owner,state=practice.owned_session();target=Path(state['work'])/'owned-camera-gc.json'
    with GameRead() as game:
        if args.action=='capture':
            text=practice.log_path(state).read_text(encoding='utf-8',errors='replace')[owner['log_offset']:]
            refs=re.findall(r'CONTROL_PARTICIPANT=boss\|([^|\r\n]+)\|address=(\d+)\|class=([^\r\n]+)',text)
            assert refs,'successful current assembly required'
            boss=int(refs[-1][1])
            scene=next(r for r in game.find_native({'SceneComponent'}) if r['path']=='/Script/Engine.SceneComponent')
            prop=next(p for p in fields(game,int(scene['address'],16),512) if p['name']=='AttachParent')
            attach_offset=int(prop['offset'],16)
            candidates=[];booms=set()
            for index in range(game.count):
                try:
                    obj=game.object(index)
                    if not obj:continue
                    header=game.header(obj)
                    if header['flags'] & 0x10:continue
                    cls=game.path(header['class'])
                    if cls=='/Script/Engine.SpringArmComponent' and header['outer']==boss:
                        booms.add(obj);candidates.append(obj)
                    elif cls=='/Script/Engine.CameraComponent':candidates.append(obj)
                except(OSError,ValueError,UnicodeError):continue
            assert booms,'owned spring arm required'
            selected=set(booms)
            for obj in candidates:
                h=game.header(obj)
                if obj not in booms and game.u64(obj+attach_offset) in booms:
                    selected.add(obj);selected.add(h['outer'])
            rows=[{'path':game.path(obj),'class':game.path(game.header(obj)['class']),
                'address':obj,'index':game.header(obj)['index']} for obj in selected]
            assert len(rows)==3 and {r['class'] for r in rows}=={
                '/Script/Engine.CameraActor','/Script/Engine.CameraComponent','/Script/Engine.SpringArmComponent'}
            data={'state_file':state['state_file'],'pid':game.pid,'captured_at':time.time(),'objects':rows,'checks':[]}
        else:
            data=json.loads(target.read_text(encoding='utf-8'))
            assert data['state_file']==state['state_file'] and data['pid']==game.pid
            results=[]
            for row in data['objects']:
                pointer=game.object(row['index'])
                released=pointer!=row['address']
                if not released:
                    released=game.path(pointer)!=row['path'] or game.path(game.header(pointer)['class'])!=row['class']
                results.append({'path':row['path'],'array_slot_released_or_reused':released,'current_pointer':hex(pointer)})
            data['checks'].append({'at':time.time(),'objects':results,'all_released':all(r['array_slot_released_or_reused'] for r in results)})
        target.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'report':str(target),'captured':len(data['objects']),'latest':data['checks'][-1] if data['checks'] else None},ensure_ascii=False))


if __name__=='__main__':main()
