"""用途：只读筛选已加载的Boss相关UE类；类存在不代表已经解锁或有可用实例。"""
import json
from pathlib import Path
import re
import struct
import sys
import official_validation as v
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields,functions


def collect():
    results=[];failures=[]
    with GameRead() as g:
        for index in range(g.count):
            try:
                obj=g.object(index)
                if not obj:continue
                raw=g.read(obj,40);comp,num=struct.unpack_from('<II',raw,24);name=g.name(comp,num)
                if not re.search(r'boss|leader|elite',name,re.I):continue
                cls=struct.unpack_from('<Q',raw,16)[0]
                if g.header(cls)['name'] not in ('Class','BlueprintGeneratedClass'):continue
                path=g.path(obj)
                if not path.startswith(('/Game/','/PBZCombatAsset/','/Script/ProjectPBZ.','/Script/SGame')):continue
                results.append({'path':path,'index':index,'super':g.path(g.u64(obj+0x40)),
                    'properties':fields(g,obj),'functions':functions(g,obj)[:96]})
                if len(results)>=60:break
            except (OSError,ValueError,UnicodeError) as error:
                if len(failures)<12:failures.append({'index':index,'type':type(error).__name__})
        report={'at':v.utc8(),'pid':g.pid,'classes':results,'errors':failures,
            'scope':'Loaded class declarations only; no spawning or game function calls','unlocked_boss_verified':False}
        target=Path(g.state['work'])/'loaded-boss-class-catalog.json';v.save(target,report)
        return {'report':str(target),'class_count':len(results),'classes':[r['path'] for r in results]}


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');print(json.dumps(collect(),ensure_ascii=False,indent=2))
