"""用途：一次只读读取遥控和AI焦点接口声明，另保存NPC目标查询的虚表证据。"""
import json
import struct
import sys
from pathlib import Path
import official_validation as v
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields,functions

FUNCTIONS={
 '/Script/Engine.Actor.SetActorTickEnabled','/Script/Engine.Actor.IsActorTickEnabled',
 '/Script/Engine.ActorComponent.SetComponentTickEnabled','/Script/Engine.ActorComponent.IsComponentTickEnabled',
 '/Script/Engine.Controller.SetIgnoreMoveInput','/Script/Engine.Controller.SetIgnoreLookInput',
 '/Script/Engine.Controller.IsMoveInputIgnored','/Script/Engine.Controller.IsLookInputIgnored',
 '/Script/Engine.Controller.GetControlRotation','/Script/Engine.Controller.SetControlRotation',
 '/Script/Engine.Actor.DisableInput','/Script/Engine.Actor.EnableInput',
 '/Script/AIModule.AIController.K2_SetFocus','/Script/AIModule.AIController.K2_ClearFocus',
 '/Script/AIModule.AIController.GetFocusActor','/Script/AIModule.AIController.GetFocalPoint',
}

def collect():
    declarations=[]
    with GameRead()as g:
        ai_class=None
        for row in g.find_native({p.rsplit('.',1)[1]for p in FUNCTIONS}|{'SGameAIComponent'}):
            if row['path']=='/Script/SGameAI.SGameAIComponent':
                a=int(row['address'],16);ai_class={'path':row['path'],'fields':fields(g,a),'functions':functions(g,a)}
            if row['path']not in FUNCTIONS:continue
            a=int(row['address'],16)
            declarations.append({'path':row['path'],'parameter_bytes':struct.unpack('<H',g.read(a+0x106,2))[0],
                'parameters':[p for p in fields(g,a,32)if int(p['property_flags'],16)&0x80]})
        missing=sorted(FUNCTIONS-{f['path']for f in declarations})
        result={'at':v.utc8(),'pid':g.pid,'passed':not missing and ai_class is not None,'missing':missing,'functions':declarations,'ai_class':ai_class}
        target=Path(g.state['work'])/'remote-native-contract.json';v.save(target,result)
    print(json.dumps({'report':str(target),'missing':missing,'functions':[{'path':f['path'],'size':f['parameter_bytes'],'parameters':[(p['name'],p['type'],p['offset'])for p in f['parameters']]}for f in declarations]},ensure_ascii=False))

if __name__=='__main__':collect()
