"""用途：只读核对原主角保护所需的字段与函数声明，不修改健康或存档。"""
import json
from pathlib import Path
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields,functions
import official_validation as v


def collect():
    with GameRead()as g:
        rows=[]
        for row in g.find_native({'CharacterMovementComponent','Actor'}):
            if row['path']not in('/Script/Engine.CharacterMovementComponent','/Script/Engine.Actor'):continue
            a=int(row['address'],16)
            rows.append({'path':row['path'],'properties':[p for p in fields(g,a,512)if p['name']in('MovementMode','CustomMovementMode','bHidden','bCanBeDamaged')],
                'functions':[f for f in functions(g,a)if f['name']in('GetActorEnableCollision','SetActorEnableCollision','SetActorHiddenInGame','DisableMovement','SetMovementMode')]})
        fs={f['name']:f['parameter_bytes']for c in rows for f in c['functions']}
        expected={'DisableMovement':0,'SetMovementMode':2,'GetActorEnableCollision':1,'SetActorEnableCollision':1,'SetActorHiddenInGame':1}
        result={'at':v.utc8(),'pid':g.pid,'passed':all(fs.get(k)==n for k,n in expected.items()),'classes':rows}
        v.save(Path(g.state['work'])/'player-protection-contract.json',result)
    print(json.dumps({'passed':result['passed'],'scope':'declarations only'}));return result


if __name__=='__main__':collect()
