"""用途：一批核对阵营、战斗目标和销毁状态的真实声明；只读，不改主角、剧情或存档。"""
import json
from pathlib import Path
import re
import struct
import sys
import official_validation as v
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields, functions


def collect():
    classes=[];native=[];errors=0
    wanted=re.compile(r'faction|targeting|hatred|PBZCharacter|SGameAIController',re.I)
    status={'IsActorBeingDestroyed','K2_DestroyActor','IsComponentBeingDestroyed','IsRegistered','GetOwner','K2_DestroyComponent'}
    with GameRead()as g:
        for index in range(g.count):
            try:
                address=g.object(index)
                if not address:continue
                raw=g.read(address,40)
                name=g.name(*struct.unpack_from('<II',raw,24))
                if not wanted.search(name) and name not in status:continue
                kind=g.header(struct.unpack_from('<Q',raw,16)[0])['name']
                if kind not in ('Class','BlueprintGeneratedClass','Function'):continue
                path=g.path(address)
                if kind=='Function':
                    if name not in status or not path.startswith('/Script/Engine.'):continue
                    native.append({'path':path,'parameter_bytes':struct.unpack('<H',g.read(address+0x106,2))[0],
                        'parameters':[p for p in fields(g,address,32)if int(p['property_flags'],16)&0x80]})
                elif len(classes)<80:
                    ps=fields(g,address,256);fs=functions(g,address)
                    all_faction='faction'in name.lower()or'targeting'in name.lower()or'hatred'in name.lower()
                    classes.append({'path':path,'super':g.path(g.u64(address+0x40)),
                        'properties':ps if all_faction else [p for p in ps if re.search(r'faction|team|target|health|damage',p['name'],re.I)],
                        'functions':fs if all_faction else [f for f in fs if re.search(r'faction|team|target|health|damage',f['name'],re.I)]})
            except (OSError,ValueError,UnicodeError):errors+=1
        report={'at':v.utc8(),'pid':g.pid,'classes':classes,'native_status_functions':native,
            'invalid_or_unreadable_candidates':errors,'scope':'Specific combat identity/target declarations and destruction queries only; no gameplay calls or writes'}
        target=Path(g.state['work'])/'combat-native-contract.json'
        v.save(target,report);v.save(v.ROOT/'evidence/adaptation/latest-combat-native-contract.json',report)
    print(json.dumps({'report':str(target),'classes':[{'path':row['path'],'properties':[p['name']for p in row['properties']],
        'functions':[f['name']for f in row['functions']]}for row in classes],
        'native_status_functions':[f['path']for f in native]},ensure_ascii=False,indent=2))


if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');collect()
